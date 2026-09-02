"""
Fetches the ship's recent event history (port arrivals/departures,
start/stop moving, coverage/sea-area changes) from several public
vessel-tracking sites (see sources/), takes the union of everything they
report, and appends any events not already present to the "Events"
Google Sheet tab. Intended to run as a short-lived GitHub Actions job on
a cron schedule.

Each source scrapes a rolling event log (MyShipTracking ~3 weeks,
AISVesselTracker ~1 week), so most runs re-see events already written;
duplicates are avoided by comparing (Time, Event) against what's already
in the sheet before appending. Event-type labels are stored exactly as
each site words them — there is no shared vocabulary, and the same
real-world event seen by two sites under different names is kept as two
rows.

Adding another site is just another module under sources/ (see
sources/__init__.py).
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from sources import SOURCES

load_dotenv()

REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))


def load_config():
    required = ["SHIP_MMSI", "GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "mmsi": os.environ["SHIP_MMSI"],
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "tab": os.environ.get("GOOGLE_SHEET_TAB", "Events"),
    }


def _fetch_one(source, mmsi, timeout, lookback_days):
    """Run one source's fetch, classifying the outcome. Returns
    ('ok', events) | ('error', message)."""
    try:
        events = source.fetch(mmsi, timeout, lookback_days)
    except requests.RequestException as exc:
        return "error", f"request failed: {exc}"
    except Exception as exc:  # noqa: BLE001 - a broken parser must not sink the run
        return "error", f"parse failed: {exc}"
    return "ok", events


def collect_events(mmsi, timeout=REQUEST_TIMEOUT_SECONDS, lookback_days=LOOKBACK_DAYS):
    """Query every configured source, concurrently. Returns (events,
    errors): `events` is the flat union of every source's event dicts;
    `errors` is a list of (source_name, message) for the sources that
    raised. Sources are independent HTTP calls, so running them in
    parallel keeps a run's wall time near the slowest single source
    rather than the sum."""
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        outcomes = list(
            pool.map(
                lambda src: _fetch_one(src, mmsi, timeout, lookback_days), SOURCES
            )
        )

    events, errors = [], []
    for source, (status, payload) in zip(SOURCES, outcomes):
        name = getattr(source, "SOURCE", source.__name__)
        if status == "ok":
            events.extend(payload)
        else:
            errors.append((name, payload))
    return events, errors


def event_time_iso(e):
    """Combine a source's separate date/time fields into a single
    ISO-8601 UTC timestamp, matching the Time column convention every
    other tracking method's sheet uses."""
    return f"{e['date']}T{e['time']}:00Z"


def existing_keys(sheet):
    """Read (time, event) from every existing row, to skip re-appending
    events already recorded. Time (column 3) plus Event (column 4)
    together identify an event uniquely, since a ship can't have two
    different events of the same type at the exact same timestamp."""
    rows = sheet.get_all_values()[1:]  # skip header
    return {(row[2], row[3]) for row in rows if len(row) > 3}


def append_new_events(sa_key_path, sheet_id, tab, events):
    creds = Credentials.from_service_account_file(
        sa_key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_id).worksheet(tab)

    seen = existing_keys(sheet)
    new_rows = []
    # Append in chronological order (oldest first, newest last): rows are
    # only ever appended, never re-sorted, so the batch must go in
    # sorted. Sort on the ISO Time string actually written to the sheet
    # (so ordering matches what a reader sees), with Event as a stable
    # tie-breaker for events sharing the same minute.
    for e in sorted(events, key=lambda e: (event_time_iso(e), e["event"])):
        time_iso = event_time_iso(e)
        key = (time_iso, e["event"])
        if key in seen:
            continue
        seen.add(key)
        new_rows.append([
            e["lat"], e["lon"], time_iso, e["event"],
            e["port"], e["country"], e["speed"], e["course"],
        ])

    if new_rows:
        sheet.append_rows(new_rows)
    return len(new_rows)


def main():
    cfg = load_config()

    events, errors = collect_events(cfg["mmsi"])
    for name, message in errors:
        print(f"Source {name}: {message}")

    if not events:
        # Nothing from any source. Either every source's page structure
        # changed at once (their errors are printed above), or a real
        # ship genuinely had zero events (not even a coverage change) in
        # the whole window across every site — far less likely. Fail
        # loudly (nonzero exit) so GitHub Actions marks the run failed
        # and emails a notification.
        sys.exit(
            f"No events found for MMSI {cfg['mmsi']} from any source "
            "(see messages above); page structures may have changed."
        )

    added = append_new_events(cfg["sa_key_path"], cfg["sheet_id"], cfg["tab"], events)
    print(
        f"Fetched {len(events)} events across {len(SOURCES) - len(errors)} "
        f"source(s), added {added} new row(s) to '{cfg['tab']}'."
    )


if __name__ == "__main__":
    main()
