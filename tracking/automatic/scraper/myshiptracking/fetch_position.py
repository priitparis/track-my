"""
Fetches a ship's current position by scraping its MyShipTracking.com
vessel page (by MMSI), and appends it to the "Scraper" Google Sheet tab.
Intended to run as a short-lived GitHub Actions job on a cron schedule.
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
    """Fetch the vessel page and extract (lat, lon), or None if the
    position pattern isn't found on the page."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    match = POSITION_PATTERN.search(response.text)
    if not match:
        return None

    lat, lon = float(match.group(1)), float(match.group(2))
    return lat, lon


def append_to_sheet(sa_key_path, sheet_id, tab, lat, lon, time):
    creds = Credentials.from_service_account_file(
        sa_key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_id).worksheet(tab)
    sheet.append_row([lat, lon, time])


def main():
    cfg = load_config()

    try:
        result = fetch_position(cfg["mmsi"])
    except requests.RequestException as e:
        print(f"Failed to fetch vessel page: {e}")
        sys.exit(0)

    if result is None:
        print(
            f"No position found on the vessel page for MMSI {cfg['mmsi']}; "
            "the page structure may have changed. Skipping this run."
        )
        sys.exit(0)

    lat, lon = result
    time = datetime.now(timezone.utc).isoformat()
    append_to_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["tab"], lat, lon, time)
    print(f"Wrote position for MMSI {cfg['mmsi']}: {lat}, {lon} at {time}")


if __name__ == "__main__":
    main()
