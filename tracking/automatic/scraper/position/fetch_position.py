"""
Fetches a ship's current position from several public vessel-tracking
sites (see sources/), keeps the one reporting the freshest AIS fix, and
appends a single row to the "Scraper" Google Sheet tab. Intended to run
as a short-lived GitHub Actions job on a cron schedule.

Each appended row carries a `source` column naming the site the winning
position came from. Adding another site is just another module under
sources/ (see sources/__init__.py).
"""

import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from sources import SOURCES

load_dotenv()

# One-time historical base distance, in nautical miles, covering the
# part of the trip this sheet doesn't itself track: Blog rows 38-44
# (Pärnu jahtklubi B-kai -> Visby sadam), then Events rows 2-57 (Visby
# PORT DEPARTURE -> Den Helder STOP Moving), then the connecting leg
# from Events' last point to this tab's own first row. See
# ../../svg-report/README.md for the exact derivation. Computed
# 2026-08-26 from Pallipere.xlsx. This is a frozen snapshot, not a live
# formula — recompute and update it manually if those historical rows
# are ever corrected/backfilled.
BASE_DISTANCE_NM = 847.9773

EARTH_RADIUS_KM = 6371.0088
KM_PER_NM = 1.852

REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))


def haversine_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance between two (lat, lon) points, in nautical miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    km = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
    return km / KM_PER_NM


def load_config():
    required = ["SHIP_MMSI", "GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "mmsi": os.environ["SHIP_MMSI"],
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "tab": os.environ.get("GOOGLE_SHEET_TAB", "Scraper"),
    }


def _fetch_one(source, mmsi, timeout):
    """Run one source's fetch, classifying the outcome. Returns
    ('ok', row) | ('error', message)."""
    try:
        row = source.fetch(mmsi, timeout)
    except requests.RequestException as exc:
        return "error", f"request failed: {exc}"
    except Exception as exc:  # noqa: BLE001 - a broken parser must not sink the run
        return "error", f"parse failed: {exc}"
    if row is None:
        return "error", "no position on page (structure may have changed)"
    return "ok", row


def collect_positions(mmsi, timeout=REQUEST_TIMEOUT_SECONDS):
    """Query every configured source, concurrently. Returns (results,
    errors): results is a list of (source_module, row_dict) for the
    sources that produced a position, in SOURCES order; errors is a list
    of (source_name, message) for the ones that raised or returned
    nothing. Sources are independent HTTP calls, so running them in
    parallel keeps a run's wall time near a single request's timeout
    rather than the sum."""
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        outcomes = list(
            pool.map(lambda src: _fetch_one(src, mmsi, timeout), SOURCES)
        )

    results, errors = [], []
    for source, (status, payload) in zip(SOURCES, outcomes):
        name = getattr(source, "SOURCE", source.__name__)
        if status == "ok":
            results.append((source, payload))
        else:
            errors.append((name, payload))
    return results, errors


def pick_freshest(results):
    """From collect_positions() results, return the row with the newest
    `reported_at`. Rows with a blank `reported_at` sort oldest; ties
    (including all-blank) are broken by SOURCES order, so `results` must
    already be in that order."""
    return max(
        (row for _, row in results),
        key=lambda row: row.get("reported_at") or "",
        default=None,
    )


SHEET_COLUMNS = [
    "lat", "lon", "time",
    "speed", "course", "area", "status", "draught",
    "imo", "flag", "call_sign", "size", "gt", "dwt", "build",
    "distance_travelled", "remaining_distance", "avg_speed", "max_speed", "time_travelled",
    "temperature", "wind_speed", "wind_direction", "pressure", "humidity", "cloud_coverage",
    "full_distance",
    "source",
]

# Coordinates within this many degrees (~10m) of the last written row are
# treated as the same position, to avoid piling up duplicate rows while
# the ship is stationary (e.g. in port or at anchor) and AIS just repeats
# its last known fix on every run. The `source` column is NOT considered
# here — a fresh fix from a different site at the same spot is still a
# duplicate row.
SAME_POSITION_TOLERANCE_DEGREES = 0.0001


def _last_row_lat_lon(values):
    """Returns (lat, lon) of the sheet's last data row, or None if there
    isn't one or its Lat/Lon can't be parsed as numbers."""
    if len(values) < 2:
        return None
    last_row = values[-1]
    try:
        return float(last_row[0]), float(last_row[1])
    except (IndexError, ValueError):
        return None


def is_duplicate_position(values, lat, lon):
    """Compares (lat, lon) against the last row currently in the sheet
    (`values`, as returned by `sheet.get_all_values()`). Returns False
    (not a duplicate) if the sheet has no data rows yet, or if the last
    row's Lat/Lon can't be parsed as numbers."""
    last = _last_row_lat_lon(values)
    if last is None:
        return False
    last_lat, last_lon = last
    return (
        abs(lat - last_lat) <= SAME_POSITION_TOLERANCE_DEGREES
        and abs(lon - last_lon) <= SAME_POSITION_TOLERANCE_DEGREES
    )


def compute_full_distance(values, lat, lon):
    """Cumulative distance-since-departure through this new (lat, lon)
    point, in nautical miles: the historical base distance plus the
    live Haversine sum across every row already in the sheet, plus the
    final leg from the sheet's last row to this new point. If the sheet
    has no data rows yet, this new point is the start of the live sum,
    so the result is just the base distance."""
    last = _last_row_lat_lon(values)
    if last is None:
        return BASE_DISTANCE_NM
    last_lat, last_lon = last
    prior_full_distance = None
    if len(values) >= 2:
        try:
            prior_full_distance = float(values[-1][SHEET_COLUMNS.index("full_distance")])
        except (IndexError, ValueError):
            prior_full_distance = None
    base = prior_full_distance if prior_full_distance is not None else BASE_DISTANCE_NM
    return base + haversine_nm(last_lat, last_lon, lat, lon)


def append_to_sheet(sa_key_path, sheet_id, tab, row_data):
    creds = Credentials.from_service_account_file(
        sa_key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_id).worksheet(tab)
    values = sheet.get_all_values()
    if is_duplicate_position(values, row_data["lat"], row_data["lon"]):
        return False
    row_data["full_distance"] = round(
        compute_full_distance(values, row_data["lat"], row_data["lon"]), 4
    )
    sheet.append_row([row_data.get(col, "") for col in SHEET_COLUMNS])
    return True


def main():
    cfg = load_config()

    results, errors = collect_positions(cfg["mmsi"])
    for name, message in errors:
        print(f"Source {name}: {message}")

    if not results:
        # Every source failed — almost always a page-structure change
        # rather than the ship being out of coverage. Fail loudly
        # (nonzero exit) so GitHub Actions marks the run failed and
        # emails a notification.
        sys.exit(
            f"No source produced a position for MMSI {cfg['mmsi']}; "
            "all sources failed (see messages above)."
        )

    result = pick_freshest(results)

    # Prefer the AIS-reported observation time; fall back to the
    # scraper's own run time if no source exposed one.
    result["time"] = result.get("reported_at") or datetime.now(timezone.utc).isoformat()
    written = append_to_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["tab"], result)
    if not written:
        print(
            f"Skipped MMSI {cfg['mmsi']}: position {result['lat']}, {result['lon']} "
            f"(source {result['source']}) matches the last recorded row; "
            "ship appears stationary."
        )
        return
    print(
        f"Wrote position for MMSI {cfg['mmsi']}: {result['lat']}, {result['lon']} "
        f"at {result['time']} (source={result['source']}, "
        f"speed={result['speed'] or '?'}, full_distance={result['full_distance']} nm)"
    )


if __name__ == "__main__":
    main()
