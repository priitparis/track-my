"""
Manual connectivity check for AISStream.io — connects, subscribes for the
configured MMSI, and prints the first PositionReport received, then exits.
Useful for verifying AISSTREAM_API_KEY and SHIP_MMSI without writing to
the sheet.
"""

import asyncio
import json
import os

import websockets
from dotenv import load_dotenv

load_dotenv()

AIS_WS_URL = "wss://stream.aisstream.io/v0/stream"
WAIT_TIMEOUT_SECONDS = int(os.environ.get("CONNECT_TIMEOUT_SECONDS", "60"))
WORLD_BOUNDING_BOX = [[-90.0, -180.0], [90.0, 180.0]]


async def test():
    api_key = os.environ["AISSTREAM_API_KEY"]
    mmsi = os.environ["SHIP_MMSI"]

    async with websockets.connect(AIS_WS_URL) as ws:
        await ws.send(json.dumps({
            "APIKey": api_key,
            "BoundingBoxes": [WORLD_BOUNDING_BOX],
            "FiltersShipMMSI": [mmsi],
            "FilterMessageTypes": ["PositionReport"],
        }))
        print(f"Subscribed for MMSI {mmsi}, waiting up to "
              f"{WAIT_TIMEOUT_SECONDS}s for a PositionReport...")

        async with asyncio.timeout(WAIT_TIMEOUT_SECONDS):
            async for raw in ws:
                msg = json.loads(raw)
                message_type = msg.get("MessageType")

                if message_type == "SubscriptionConfirmation":
                    print("Subscription confirmed, waiting for a position report...")
                    continue

                if message_type == "PositionReport":
                    print(raw)
                    return

                print(f"Ignoring unrelated message type: {message_type}")


if __name__ == "__main__":
    try:
        asyncio.run(test())
    except TimeoutError:
        print(f"No PositionReport received within {WAIT_TIMEOUT_SECONDS}s. "
              "The ship may currently be outside AIS receiver coverage.")
    except (websockets.WebSocketException, OSError) as e:
        print(f"AIS connection failed: {e or type(e).__name__}")
