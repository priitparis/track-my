"""
One-time backfill: computes the "full_distance" column for every
existing row in the Scraper sheet tab that doesn't have it yet (rows
written before that column existed), using the same Haversine +
BASE_DISTANCE_NM logic as
../../tracking/automatic/scraper/position/fetch_position.py
(imported directly from there, not duplicated here).

Not part of the ongoing automation — run manually, once, after adding
the full_distance column to the sheet. Safe to re-run: it always
recomputes every row from scratch and overwrites the column in one
batch update.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "tracking", "automatic", "scraper", "position"),
)

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from fetch_position import BASE_DISTANCE_NM, haversine_nm

load_dotenv()


def load_config():
    required = ["GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "tab": os.environ.get("GOOGLE_SHEET_TAB", "Scraper"),
    }


def compute_backfilled_distances(rows):
    """rows: list of (lat, lon) tuples in sheet order. Returns a list of
    full_distance values (nautical miles), one per row, in the same
    order: the first row gets BASE_DISTANCE_NM, each following row adds
    the Haversine leg from the previous row."""
    distances = []
    running = BASE_DISTANCE_NM
    for i, (lat, lon) in enumerate(rows):
        if i > 0:
            prev_lat, prev_lon = rows[i - 1]
            running += haversine_nm(prev_lat, prev_lon, lat, lon)
        distances.append(round(running, 4))
    return distances


def main():
    cfg = load_config()
    creds = Credentials.from_service_account_file(
        cfg["sa_key_path"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(cfg["sheet_id"]).worksheet(cfg["tab"])

    header = sheet.row_values(1)
    if "full_distance" not in header:
        sys.exit('The "full_distance" column was not found in the sheet header.')
    full_distance_col = header.index("full_distance") + 1  # 1-indexed for gspread

    values = sheet.get_all_values()[1:]  # skip header
    if not values:
        print("No data rows found; nothing to backfill.")
        return

    rows = [(float(r[0]), float(r[1])) for r in values]
    distances = compute_backfilled_distances(rows)

    updates = [
        {"range": gspread.utils.rowcol_to_a1(i + 2, full_distance_col), "values": [[d]]}
        for i, d in enumerate(distances)
    ]
    sheet.batch_update(updates)

    print(f"Backfilled full_distance for {len(distances)} rows.")
    print(f"First row: {distances[0]} nm, last row: {distances[-1]} nm.")


if __name__ == "__main__":
    main()
