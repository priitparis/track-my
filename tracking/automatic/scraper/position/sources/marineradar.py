"""
MarineRadar.com position source.

The vessel page embeds a schema.org JSON-LD block
(`<script type="application/ld+json">`) with a `Boat` node carrying the
live AIS position, the observation timestamp, and speed/course/heading/
navigation-status as `additionalProperty` entries. Parsing that
structured block is more robust than scraping the page's visible HTML
tables.

Only the fields that map onto the existing sheet columns are kept;
MarineRadar-only extras (destination, ETA) are ignored to keep the sheet
schema stable.
"""

import json
import re

import requests

from ._common import USER_AGENT, blank_row

SOURCE = "marineradar"

PAGE_URL_TEMPLATE = "https://www.marineradar.com/vessel/mmsi-{mmsi}"

_LDJSON_PATTERN = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)


def _normalize_iso_utc(value):
    """MarineRadar writes '2026-08-28T06:51:58Z'; normalize the trailing
    'Z' to '+00:00' so it matches the other sources' ISO strings. Returns
    '' for a falsy input."""
    if not value:
        return ""
    return value[:-1] + "+00:00" if value.endswith("Z") else value


def _find_boat_node(html):
    """Return the schema.org 'Boat'/'Vessel' node from the page's JSON-LD
    blocks, or None."""
    for raw in _LDJSON_PATTERN.findall(html):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        for node in data.get("@graph", [data]):
            if isinstance(node, dict) and node.get("@type") in ("Boat", "Vessel"):
                return node
    return None


def _properties(node):
    """additionalProperty list -> {propertyID: (value, unitText)}."""
    out = {}
    for prop in node.get("additionalProperty", []):
        if isinstance(prop, dict) and prop.get("propertyID"):
            out[prop["propertyID"]] = (prop.get("value"), prop.get("unitText"))
    return out


def _measure(props, key):
    """Format a numeric property as 'value unit' (e.g. '5.7 knots'), or
    just the value, or '' if absent."""
    if key not in props:
        return ""
    value, unit = props[key]
    if value in (None, ""):
        return ""
    return f"{value} {unit}" if unit else str(value)


def fetch(mmsi, timeout):
    """Fetch the vessel page and parse its JSON-LD 'Boat' node. Returns
    None if the block or its coordinates are missing."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()

    node = _find_boat_node(response.text)
    if not node:
        return None
    location = node.get("location") or {}
    lat, lon = location.get("latitude"), location.get("longitude")
    if lat is None or lon is None:
        return None

    props = _properties(node)
    row = blank_row(SOURCE)
    row.update(
        lat=float(lat),
        lon=float(lon),
        reported_at=_normalize_iso_utc(location.get("observationDate")),
        speed=_measure(props, "speedOverGround"),
        course=_measure(props, "courseOverGround"),
        status=str(props["navigationStatus"][0]) if "navigationStatus" in props else "",
        flag=(node.get("nationality") or {}).get("name", ""),
    )
    return row
