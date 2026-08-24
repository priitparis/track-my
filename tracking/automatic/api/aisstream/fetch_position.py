"""
Connects to AISStream.io, waits for one PositionReport for a specific
ship (by MMSI), and appends it to the "Auto" Google Sheet tab.
Intended to run as a short-lived GitHub Actions job on a cron schedule.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import websockets
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

AIS_WS_URL = "wss://stream.aisstream.io/v0/stream"
CONNECT_TIMEOUT_SECONDS = int(os.environ.get("CONNECT_TIMEOUT_SECONDS", "180"))
WORLD_BOUNDING_BOX = [[-90.0, -180.0], [90.0, 180.0]]


def load_config():
    required = ["AISSTREAM_API_KEY", "SHIP_MMSI", "GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "api_key": os.environ["AISSTREAM_API_KEY"],
        "mmsi": os.environ["SHIP_MMSI"],
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "tab": os.environ.get("GOOGLE_SHEET_TAB", "Auto"),
    }


async def fetch_position(api_key, mmsi, timeout):
    """Open the AIS stream, subscribe for one MMSI, return the first
    PositionReport as (lat, lon, time) or None on timeout."""
    async with websockets.connect(AIS_WS_URL) as ws:
        await ws.send(json.dumps({
            "APIKey": api_key,
            "BoundingBoxes": [WORLD_BOUNDING_BOX],
            "FiltersShipMMSI": [str(mmsi)],
            "FilterMessageTypes": ["PositionReport"],
        }))
        async with asyncio.timeout(timeout):
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("MessageType") == "PositionReport":
                    report = msg["Message"]["PositionReport"]
                    return (
                        report["Latitude"],
                        report["Longitude"],
                        datetime.now(timezone.utc).isoformat(),
                    )
    return None


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
        result = asyncio.run(
            fetch_position(cfg["api_key"], cfg["mmsi"], CONNECT_TIMEOUT_SECONDS)
        )
    except TimeoutError:
        print(
            f"No PositionReport received for MMSI {cfg['mmsi']} "
            f"within {CONNECT_TIMEOUT_SECONDS}s; skipping this run."
        )
        sys.exit(0)
    except (websockets.WebSocketException, OSError) as e:
        print(f"AIS connection failed: {e or type(e).__name__}")
        sys.exit(0)

    if result is None:
        print(
            f"No PositionReport received for MMSI {cfg['mmsi']} "
            f"within {CONNECT_TIMEOUT_SECONDS}s; skipping this run."
        )
        sys.exit(0)

    lat, lon, time = result
    append_to_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["tab"], lat, lon, time)
    print(f"Wrote position for MMSI {cfg['mmsi']}: {lat}, {lon} at {time}")


if __name__ == "__main__":
    main()
