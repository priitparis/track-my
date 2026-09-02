"""
Event sources for the unified event-log scraper.

Each source module exposes:
    SOURCE   -- str, a short name for the site (for log messages)
    fetch(mmsi, timeout, lookback_days) -> list[dict]

`fetch` returns a list of event dicts shaped like `_common.EVENT_FIELDS`
(keys: date, time, event, port, country, lat, lon, speed, course), one
per event the source reports in the lookback window. It returns [] if
the source has no events; it raises on a transport error or a page whose
structure it no longer recognises, so the orchestrator can decide
whether an all-sources failure is fatal.

Event-type labels are written through as each site words them (e.g.
MyShipTracking's "PORT ARRIVAL" vs AISVesselTracker's "port_arrival") —
there is no shared vocabulary. The orchestrator takes the union of every
source's events and de-duplicates on (Time, Event).

To add a new source: drop a module here with that interface and add it
to SOURCES below.
"""

from . import aisvesseltracker
from . import myshiptracking

SOURCES = [myshiptracking, aisvesseltracker]

__all__ = ["SOURCES", "myshiptracking", "aisvesseltracker"]
