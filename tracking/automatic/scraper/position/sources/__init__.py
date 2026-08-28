"""
Position sources for the unified scraper.

Each source module exposes:
    SOURCE   -- str, the value written to the sheet's `source` column
    fetch(mmsi, timeout) -> dict | None

`fetch` returns a dict shaped like the non-distance part of
fetch_position.SHEET_COLUMNS (keys: lat, lon, reported_at, speed,
course, area, status, draught, imo, flag, ... plus source), or None if
the source couldn't produce at least a (lat, lon). `reported_at` is the
AIS observation time as an ISO-8601 UTC string, or "" if the source
doesn't expose one.

To add a new source: drop a module here with that interface and add it
to SOURCES below. The orchestrator queries every source, then keeps the
row whose `reported_at` is newest.
"""

from . import marineradar, myshiptracking

# Order matters only for tie-breaking: when two sources report the same
# (or an unknown) observation time, the one earlier in this list wins.
# MyShipTracking first, as the established primary source.
SOURCES = [myshiptracking, marineradar]

__all__ = ["SOURCES", "myshiptracking", "marineradar"]
