"""
Generates a status SVG summarizing the ship's current position, last
event, and total distance traveled, reading from the "Scraper" and
"Events" Google Sheet tabs. Intended to run as a short-lived GitHub
Actions job on a cron schedule; the workflow commits the generated SVG
back into the repo so it can be embedded elsewhere (e.g. Substack) via
its raw.githubusercontent.com URL.
"""

import math
import os
import sys

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

# --- Ship identity (hardcoded; not stored in any sheet) ---------------
SHIP_NAME = "Sanuk"
SHIP_TYPE = "Sailing yacht"
SHIP_FLAG = "Estonia"
SHIP_CALL_SIGN = "ES4371"

# One-time historical base distance, in nautical miles, covering the
# part of the trip no single sheet tracks end-to-end: Blog rows 38-44
# (Pärnu jahtklubi B-kai -> Visby sadam), then Events rows 2-57 (Visby
# PORT DEPARTURE -> Den Helder STOP Moving), then the connecting leg
# from Events' last point to the Scraper tab's own first row. See
# README.md for the exact derivation. Computed 2026-08-26 from
# Pallipere.xlsx. This is a frozen snapshot, not a live formula —
# recompute and update it manually if those historical rows are ever
# corrected/backfilled.
BASE_DISTANCE_NM = 847.9773

EARTH_RADIUS_KM = 6371.0088
KM_PER_NM = 1.852


def load_config():
    required = ["GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "scraper_tab": os.environ.get("GOOGLE_SHEET_SCRAPER_TAB", "Scraper"),
        "events_tab": os.environ.get("GOOGLE_SHEET_EVENTS_TAB", "Events"),
        "output_path": os.environ.get("OUTPUT_SVG_PATH", "status/status.svg"),
    }


# --- Distance --------------------------------------------------------------

def haversine_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance between two (lat, lon) points, in nautical miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    km = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
    return km / KM_PER_NM


def total_distance_nm(scraper_positions):
    """Sums Haversine distance across consecutive (lat, lon) pairs in the
    Scraper tab's own rows, then adds the fixed historical base distance."""
    live_nm = sum(
        haversine_nm(a[0], a[1], b[0], b[1])
        for a, b in zip(scraper_positions, scraper_positions[1:])
    )
    return BASE_DISTANCE_NM + live_nm


# --- Sheet reading -----------------------------------------------------------

def open_sheet(sa_key_path, sheet_id, tab):
    creds = Credentials.from_service_account_file(
        sa_key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(sheet_id).worksheet(tab)


def read_scraper_positions(sheet):
    """Returns ([(lat, lon), ...] in sheet order, latest row as a dict)."""
    records = sheet.get_all_records()
    if not records:
        return [], None
    positions = [(float(r["Lat"]), float(r["Lon"])) for r in records]
    return positions, records[-1]


def read_latest_event(sheet):
    records = sheet.get_all_records()
    return records[-1] if records else None


# --- SVG rendering -----------------------------------------------------------

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300" font-family="Helvetica, Arial, sans-serif">
  <rect width="600" height="300" fill="#0b1f33"/>
  <text x="24" y="40" fill="#ffffff" font-size="22" font-weight="bold">{ship_name} ({ship_type})</text>
  <text x="24" y="62" fill="#9fb8cc" font-size="13">Flag: {ship_flag}  Call sign: {ship_call_sign}</text>

  <text x="24" y="100" fill="#9fb8cc" font-size="13">Last position ({position_time})</text>
  <text x="24" y="124" fill="#ffffff" font-size="18">{lat:.4f}, {lon:.4f}</text>

  <text x="24" y="158" fill="#9fb8cc" font-size="13">Speed / Course</text>
  <text x="24" y="182" fill="#ffffff" font-size="18">{speed} kn / {course}&#176;</text>

  <text x="24" y="216" fill="#9fb8cc" font-size="13">Total distance traveled</text>
  <text x="24" y="240" fill="#ffffff" font-size="18">{distance_nm:.1f} nm</text>

  <text x="24" y="274" fill="#9fb8cc" font-size="13">Last event</text>
  <text x="24" y="292" fill="#ffffff" font-size="14">{event_summary}</text>
</svg>
"""


def render_svg(status):
    """`status` is a plain dict with the fields referenced in
    SVG_TEMPLATE — see build_status()."""
    return SVG_TEMPLATE.format(**status)


def build_status(scraper_positions, latest_scraper_row, latest_event_row):
    distance_nm = total_distance_nm(scraper_positions)
    event_summary = "unknown"
    if latest_event_row:
        parts = [
            latest_event_row.get("Event", ""),
            latest_event_row.get("Port", ""),
            latest_event_row.get("Country", ""),
        ]
        event_summary = " - ".join(p for p in parts if p)
    return {
        "ship_name": SHIP_NAME,
        "ship_type": SHIP_TYPE,
        "ship_flag": SHIP_FLAG,
        "ship_call_sign": SHIP_CALL_SIGN,
        "lat": float(latest_scraper_row["Lat"]),
        "lon": float(latest_scraper_row["Lon"]),
        "position_time": latest_scraper_row["Time"],
        "speed": latest_scraper_row.get("speed") or "?",
        "course": latest_scraper_row.get("course") or "?",
        "distance_nm": distance_nm,
        "event_summary": event_summary,
    }


def main():
    cfg = load_config()

    scraper_sheet = open_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["scraper_tab"])
    scraper_positions, latest_scraper_row = read_scraper_positions(scraper_sheet)
    if latest_scraper_row is None:
        sys.exit("Scraper tab has no data rows; nothing to render.")

    events_sheet = open_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["events_tab"])
    latest_event_row = read_latest_event(events_sheet)

    status = build_status(scraper_positions, latest_scraper_row, latest_event_row)
    svg = render_svg(status)

    output_dir = os.path.dirname(cfg["output_path"])
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(cfg["output_path"], "w", encoding="utf-8") as f:
        f.write(svg)

    print(
        f"Wrote {cfg['output_path']} ({status['distance_nm']:.1f} nm, "
        f"last event: {status['event_summary']})"
    )


if __name__ == "__main__":
    main()
