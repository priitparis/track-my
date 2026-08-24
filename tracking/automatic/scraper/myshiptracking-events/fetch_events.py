"""
Fetches the ship's recent event history (port arrivals/departures,
start/stop moving, coverage changes) from MyShipTracking.com's public
event log, and appends any events not already present to the "Events"
Google Sheet tab. Intended to run as a short-lived GitHub Actions job
on a cron schedule.

This is a separate method from ../myshiptracking/ (which scrapes the
ship's current position only, on every run). This one scrapes a
different page — a rolling event log covering roughly the last 3
weeks — so most runs will re-see events already written; duplicates are
avoided by comparing (date, time, event) against what's already in the
sheet before appending.
"""

import os
import re
import sys
import time as time_module
from datetime import datetime, timedelta, timezone

import requests
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

BASE_URL = "https://www.myshiptracking.com/vessel-events"
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

EVENT_TYPES = [
    "PORT ARRIVAL",
    "PORT DEPARTURE",
    "START Moving",
    "STOP Moving",
    "IN Coverage",
    "OUT of Coverage",
]
EVENT_TYPE_PATTERN = re.compile("|".join(re.escape(t) for t in EVENT_TYPES))

DATETIME_PATTERN = re.compile(r'<td>(\d{4}-\d{2}-\d{2}) <b>(\d{2}:\d{2})</b></td>')
LATLON_PATTERN = re.compile(r'<div class="area_txt_1lines">([\d.\-]+) / ([\d.\-]+)</div>')
SPEED_PATTERN = re.compile(r'Speed:\s*([^<]+?)<br>')
COURSE_PATTERN = re.compile(r'Course:\s*([^<]+?)\s*</td>')
PORT_PATTERN = re.compile(r'title="\s*([^"]+)"/>\s*([A-Z0-9 .\'\-]+)</a>')


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


def fetch_page(mmsi, time_range, page):
    url = f"{BASE_URL}?sort=TIME&page={page}&mmsi={mmsi}&time={time_range}"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def parse_events(html):
    body_start = html.find('<tbody class="table-body">')
    body_end = html.find('</tbody>', body_start)
    body = html[body_start:body_end]

    row_blocks = re.findall(r'<tr>(.*?)</tr>', body, re.DOTALL)

    events = []
    for row in row_blocks:
        dt_match = DATETIME_PATTERN.search(row)
        event_match = EVENT_TYPE_PATTERN.search(row)
        latlon_match = LATLON_PATTERN.search(row)
        if not (dt_match and event_match and latlon_match):
            continue

        speed_match = SPEED_PATTERN.search(row)
        course_match = COURSE_PATTERN.search(row)
        port_match = PORT_PATTERN.search(row)

        events.append({
            "date": dt_match.group(1),
            "time": dt_match.group(2),
            "event": event_match.group(0),
            "port": port_match.group(2).strip() if port_match else "",
            "country": port_match.group(1).strip() if port_match else "",
            "lat": latlon_match.group(1),
            "lon": latlon_match.group(2),
            "speed": speed_match.group(1).strip() if speed_match else "",
            "course": course_match.group(1).strip() if course_match else "",
        })
    return events


def fetch_all_events(mmsi, lookback_days):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    time_range = f"{int(start.timestamp())}_{int(end.timestamp())}"

    all_events = []
    page = 1
    while True:
        html = fetch_page(mmsi, time_range, page)
        events = parse_events(html)
        if not events:
            break
        all_events.extend(events)

        total_match = re.search(r"Showing (\d+) - (\d+) of (\d+) Results", html)
        if total_match:
            _, end_idx, total = map(int, total_match.groups())
            if end_idx >= total:
                break
        page += 1
        time_module.sleep(1)

    return all_events


def event_time_iso(e):
    """Combine the source page's separate date/time fields into a single
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
    for e in sorted(events, key=lambda e: (e["date"], e["time"])):
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

    try:
        events = fetch_all_events(cfg["mmsi"], LOOKBACK_DAYS)
    except requests.RequestException as e:
        print(f"Failed to fetch vessel events: {e}")
        sys.exit(0)

    if not events:
        print(f"No events found for MMSI {cfg['mmsi']}; skipping this run.")
        sys.exit(0)

    added = append_new_events(cfg["sa_key_path"], cfg["sheet_id"], cfg["tab"], events)
    print(f"Fetched {len(events)} events, added {added} new row(s) to '{cfg['tab']}'.")


if __name__ == "__main__":
    main()
