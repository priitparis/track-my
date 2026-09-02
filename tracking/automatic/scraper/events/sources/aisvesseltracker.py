"""
AISVesselTracker.com (Voyage Radar) event-log source.

The vessel page (by MMSI, at a slug URL like
`/vessel/<name>-mmsi-<mmsi>-imo-<imo>`) is a Next.js app that streams its
server data into the served HTML as `self.__next_f.push([...])` chunks.
Concatenating those chunks and brace-matching the embedded
`"initialEvents": { "data": [ ... ] }` array gives a clean structured
list of the ship's recent events: type, position, speed/course,
water body, and an ISO-8601 UTC timestamp.

Same payload and parsing shape as the position scraper's
sources/aisvesseltracker.py (which reads `initialData` from the same
page).

Free access only exposes the **last 7 days** of events here ("Upgrade to
view more"), narrower than MyShipTracking's ~3-week log — so this source
mainly corroborates recent events and covers short gaps, and its
`lookback_days` argument is effectively capped by the site.

Event-type strings are written through exactly as the site names them
(`port_arrival`, `started_moving`, `waterbody_changed`, ...); the
orchestrator de-duplicates the union of all sources on (Time, Event), so
no cross-source label mapping is done.
"""

import json
import re

import requests

from ._common import USER_AGENT, blank_event

SOURCE = "aisvesseltracker"

# An MMSI-only path redirects to the canonical slug; hitting the slug
# form directly with a throwaway name/imo avoids the redirect (the site
# matches on the MMSI and ignores the name part).
PAGE_URL_TEMPLATE = "https://aisvesseltracker.com/vessel/ship-mmsi-{mmsi}-imo-0"

# Next.js flushes server data as: self.__next_f.push([1,"<json-string>"])
_NEXT_F_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[.,("(?:[^"\\]|\\.)*")\]\)', re.DOTALL
)

# React server components serialise Date values as "$D<iso>" inside the
# payload; strip that marker to get a plain timestamp string.
_RSC_DATE_PREFIX = "$D"


def _rsc_blob(html):
    """Concatenate the decoded payloads of every __next_f.push chunk."""
    parts = []
    for raw in _NEXT_F_PATTERN.findall(html):
        try:
            parts.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _extract_object(blob, key):
    """Pull the `"<key>":{ ... }` object out of the concatenated RSC blob
    by brace-matching. Returns the raw JSON substring, or None."""
    marker = blob.find(f'"{key}":{{')
    if marker == -1:
        return None
    start = marker + len(f'"{key}":')
    depth = 0
    for i in range(start, len(blob)):
        ch = blob[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return blob[start : i + 1]
    return None


def _parse_initial_events(blob):
    """Parse the `initialEvents` object out of the RSC blob and return
    its `data` list (or [] if absent/unparseable). The RSC "$D" Date
    markers on timestamp strings are stripped first so the substring is
    valid JSON."""
    raw = _extract_object(blob, "initialEvents")
    if raw is None:
        return []
    raw = raw.replace(f'"{_RSC_DATE_PREFIX}', '"')
    try:
        return json.loads(raw).get("data", []) or []
    except json.JSONDecodeError:
        return []


def _split_timestamp(value):
    """'2026-09-01T14:35:50.000Z' -> ('2026-09-01', '14:35'), matching
    the (date, time) shape the orchestrator expects. Any leftover "$D"
    marker is tolerated. Returns ('', '') if it doesn't parse."""
    if not value:
        return "", ""
    if value.startswith(_RSC_DATE_PREFIX):
        value = value[len(_RSC_DATE_PREFIX):]
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", value)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _num(value):
    """'' for None/blank, else str(value)."""
    return "" if value in (None, "") else str(value)


def _port_from_event(item):
    """Port slug for the port/berth events (e.g. 'boulognesurmer_fr_bol'
    in `new_value`); '' for events not tied to a port. The site doesn't
    expose a plain port name or country in this payload, so `country`
    stays blank."""
    if "port" in (item.get("event_type") or "") or "berth" in (item.get("event_type") or ""):
        return item.get("new_value") or ""
    return ""


def fetch(mmsi, timeout, lookback_days):
    """Fetch the vessel page and return every event in its embedded
    `initialEvents` list (the site's own ~7-day window; `lookback_days`
    can't widen it). Raises on a transport error; raises RuntimeError if
    the page has no recognisable events payload."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=timeout
    )
    response.raise_for_status()

    blob = _rsc_blob(response.text)
    if '"initialEvents"' not in blob:
        raise RuntimeError(
            "no initialEvents payload on the page (structure may have changed)"
        )

    events = []
    for item in _parse_initial_events(blob):
        date, time = _split_timestamp(item.get("timestamp"))
        if not date:
            continue
        event = blank_event()
        event.update(
            date=date,
            time=time,
            event=item.get("event_type") or "",
            port=_port_from_event(item),
            country="",
            lat=_num(item.get("latitude")),
            lon=_num(item.get("longitude")),
            speed=_num(item.get("sog")),
            course=_num(item.get("cog")),
        )
        events.append(event)
    return events
