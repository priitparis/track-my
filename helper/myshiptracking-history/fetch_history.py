"""
Fetches MyShipTracking's vessel-events pages for a given MMSI and time
window, parses every event row (arrivals, departures, start/stop moving,
coverage changes) with its timestamp, position, and (when present)
speed/course, and writes them all to a CSV file for import into Excel.

This is a manual, one-off historical backfill tool — NOT part of the
ongoing tracking system (see tracking/automatic/). MyShipTracking's
website only serves roughly the last 3 weeks of event history for a
vessel, regardless of how far back the requested time range goes.

Usage:
    python fetch_history.py <mmsi> <start_unix> <end_unix> [output.csv]

Example (find the timestamps from the site's own daterangepicker, or
compute them e.g. with `date -d '2026-08-01' +%s`):
    python fetch_history.py 276017710 1785715200 1787671664 sanuk.csv
"""

import csv
import re
import sys
import time

import requests

BASE_URL = "https://www.myshiptracking.com/vessel-events"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Event type is read directly from the label following the row's <i>
# icon (e.g. "PORT ARRIVAL", "Change Sea Area", "Detected in Sea") rather
# than matched against a fixed list — MyShipTracking has added new event
# types over time, and a fixed list silently drops any row whose type
# isn't in it.
EVENT_TYPE_PATTERN = re.compile(r'<i class="fa [^"]*"[^>]*></i>\s*([A-Za-z ]+?)\s*</td>', re.DOTALL)

DATETIME_PATTERN = re.compile(r'<td>(\d{4}-\d{2}-\d{2}) <b>(\d{2}:\d{2})</b></td>')
LATLON_PATTERN = re.compile(r'<div class="area_txt_1lines">([\d.\-]+) / ([\d.\-]+)</div>')
SPEED_PATTERN = re.compile(r'Speed:\s*([^<]+?)<br>')
COURSE_PATTERN = re.compile(r'Course:\s*([^<]+?)\s*</td>')
PORT_PATTERN = re.compile(r'title="\s*([^"]+)"/>\s*([A-Z0-9 .\'\-]+)</a>')


def fetch_page(mmsi, time_range, page):
    url = f"{BASE_URL}?sort=TIME&page={page}&mmsi={mmsi}&time={time_range}"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
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
            "event": event_match.group(1).strip(),
            "port": port_match.group(2).strip() if port_match else "",
            "country": port_match.group(1).strip() if port_match else "",
            "lat": latlon_match.group(1),
            "lon": latlon_match.group(2),
            "speed": speed_match.group(1).strip() if speed_match else "",
            "course": course_match.group(1).strip() if course_match else "",
        })
    return events


def main():
    if len(sys.argv) < 4:
        sys.exit(f"Usage: python {sys.argv[0]} <mmsi> <start_unix> <end_unix> [output.csv]")

    mmsi = sys.argv[1]
    time_range = f"{sys.argv[2]}_{sys.argv[3]}"
    out_path = sys.argv[4] if len(sys.argv) > 4 else f"{mmsi}_history.csv"

    all_events = []
    page = 1
    while True:
        html = fetch_page(mmsi, time_range, page)
        events = parse_events(html)
        if not events:
            break
        all_events.extend(events)
        print(f"Page {page}: {len(events)} events")

        total_match = re.search(r"Showing (\d+) - (\d+) of (\d+) Results", html)
        if total_match:
            _, end, total = map(int, total_match.groups())
            if end >= total:
                break
        page += 1
        time.sleep(1)

    all_events.sort(key=lambda e: (e["date"], e["time"]))

    fieldnames = ["date", "time", "event", "port", "country", "lat", "lon", "speed", "course"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_events)

    print(f"Wrote {len(all_events)} events to {out_path}")


if __name__ == "__main__":
    main()
