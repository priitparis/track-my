"""
Fetches a ship's current position, status, trip, and weather details by
scraping its MyShipTracking.com vessel page (by MMSI), and appends a row
to the "Scraper" Google Sheet tab. Intended to run as a short-lived
GitHub Actions job on a cron schedule.
"""

import os
import re
import sys
from datetime import datetime, timezone

import requests
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

PAGE_URL_TEMPLATE = "https://www.myshiptracking.com/vessels/mmsi-{mmsi}"
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# The vessel page embeds its own coordinates in a JS AJAX call, e.g.:
#   url: "/requests/contributorMap.php?lat=52.83194&lng=4.54917&data=full",
POSITION_PATTERN = re.compile(r"lat=([\d.\-]+)&lng=([\d.\-]+)")

# The page is split into clearly id'd sections; scoping field lookups to
# a section avoids matching a same-named field (e.g. "Draught",
# "Position Received") that appears in more than one table.
SECTION_PATTERN = {
    "info": re.compile(r'<div id="ft-info" class="container">(.*?)<div id="ft-trip"', re.DOTALL),
    "trip": re.compile(r'<div id="ft-trip".*?(?=<div id="ft-position")', re.DOTALL),
    "position": re.compile(r'<div id="ft-position".*?(?=<div id="ft-info-mob")', re.DOTALL),
    "weather": re.compile(r'<div id="ft-weather".*?(?=<div id="ft-portcalls")', re.DOTALL),
}


def field_pattern(label):
    return re.compile(r"<th>" + re.escape(label) + r"</th>\s*<td>(.*?)</td>", re.DOTALL)


TAG_STRIP_PATTERN = re.compile(r"<[^>]+>")


def _clean(raw):
    """Strip HTML tags and collapse whitespace from a <td> cell's inner
    content (fields like Flag wrap their value in a nested <div>/<img>)."""
    text = TAG_STRIP_PATTERN.sub(" ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _field(section_text, label):
    match = field_pattern(label).search(section_text)
    if not match:
        return ""
    value = _clean(match.group(1))
    return "" if value == "---" else value


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


def fetch_position(mmsi):
    """Fetch the vessel page and extract everything available: current
    position/status, static vessel info, current trip, and weather.
    Returns None if even the core (lat, lon) can't be found — every
    other field is best-effort and left blank if missing."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    html = response.text

    position_match = POSITION_PATTERN.search(html)
    if not position_match:
        return None
    lat, lon = float(position_match.group(1)), float(position_match.group(2))

    sections = {}
    for name, pattern in SECTION_PATTERN.items():
        match = pattern.search(html)
        sections[name] = match.group(1) if (match and match.groups()) else (match.group(0) if match else "")

    info = sections.get("info", "")
    trip = sections.get("trip", "")
    position = sections.get("position", "")
    weather = sections.get("weather", "")

    return {
        "lat": lat,
        "lon": lon,
        # Current position / status (from the "Current Position" table)
        "speed": _field(position, "Speed"),
        "course": _field(position, "Course"),
        "area": _field(position, "Area"),
        "status": _field(position, "Status"),
        "draught": _field(position, "Draught") or _field(trip, "Draught"),
        # Static vessel info
        "imo": _field(info, "IMO"),
        "flag": _field(info, "Flag"),
        "call_sign": _field(info, "Call Sign"),
        "size": _field(info, "Size"),
        "gt": _field(info, "GT"),
        "dwt": _field(info, "DWT"),
        "build": _field(info, "Build"),
        # Current trip
        "distance_travelled": _field(trip, "Distance Travelled"),
        "remaining_distance": _field(trip, "Remaining Distance"),
        "avg_speed": _field(trip, "AVG Speed"),
        "max_speed": _field(trip, "MAX Speed"),
        "time_travelled": _field(trip, "Time Travelled"),
        # Weather at the ship's current position
        "temperature": _field(weather, "Temperature"),
        "wind_speed": _field(weather, "Wind Speed"),
        "wind_direction": _field(weather, "Direction"),
        "pressure": _field(weather, "Pressure"),
        "humidity": _field(weather, "Humidity"),
        "cloud_coverage": _field(weather, "Cloud Coverage"),
    }


SHEET_COLUMNS = [
    "lat", "lon", "time",
    "speed", "course", "area", "status", "draught",
    "imo", "flag", "call_sign", "size", "gt", "dwt", "build",
    "distance_travelled", "remaining_distance", "avg_speed", "max_speed", "time_travelled",
    "temperature", "wind_speed", "wind_direction", "pressure", "humidity", "cloud_coverage",
]


def append_to_sheet(sa_key_path, sheet_id, tab, row_data):
    creds = Credentials.from_service_account_file(
        sa_key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_id).worksheet(tab)
    sheet.append_row([row_data[col] for col in SHEET_COLUMNS])


def main():
    cfg = load_config()

    try:
        result = fetch_position(cfg["mmsi"])
    except requests.RequestException as e:
        print(f"Failed to fetch vessel page: {e}")
        sys.exit(0)

    if result is None:
        # Unlike a stale-but-present position (e.g. the ship out of AIS
        # coverage), finding no position pattern at all on the page means
        # the page's HTML structure has likely changed underneath us —
        # fail loudly (nonzero exit) so GitHub Actions marks the run
        # failed and emails a notification, rather than silently
        # skipping forever.
        sys.exit(
            f"No position found on the vessel page for MMSI {cfg['mmsi']}; "
            "the page structure may have changed."
        )

    result["time"] = datetime.now(timezone.utc).isoformat()
    append_to_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["tab"], result)
    print(
        f"Wrote position for MMSI {cfg['mmsi']}: {result['lat']}, {result['lon']} "
        f"at {result['time']} (speed={result['speed'] or '?'}, area={result['area'] or '?'})"
    )


if __name__ == "__main__":
    main()
