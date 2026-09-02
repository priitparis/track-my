"""
ShipFinder.com position source.

The vessel detail page (by MMSI) is fully server-rendered: the current
AIS fix and the static vessel details sit in a plain `<div class=
"info-value" id="ais-...">value</div>` grid, and the "reported at" time
is in an `id="ais-lastTime"` cell (and repeated in the page's prose
summary). A single HTTP request is enough — no JavaScript rendering.

Coordinates are shown in degrees + decimal-minutes with a hemisphere
letter (e.g. `49-38.752 N`, `1-37.201 W`), so they're converted to
signed decimal degrees here.

ShipFinder shows no weather, tonnage (GT/DWT) or year-built on this
page, so those sheet columns are left blank.
"""

import re

import requests

from ._common import USER_AGENT, blank_row

SOURCE = "shipfinder"

PAGE_URL_TEMPLATE = "https://www.shipfinder.com/ship/detail/mmsi/{mmsi}"

# Each field is a `<div class="info-value" id="ais-<key>">value</div>`.
_FIELD_TEMPLATE = r'id="ais-{key}"[^>]*>(.*?)</div>'

# "49-38.752 N" / "1-37.201 W": whole degrees, decimal minutes, hemisphere.
_COORD_PATTERN = re.compile(r"(\d+)-([\d.]+)\s*([NSEW])")

# The reported-at time sits in the `id="ais-lastTime"` cell, e.g.:
#   <div class="info-value" id="ais-lastTime">2026-09-02 16:01:54</div>
_REPORTED_AT_PATTERN = re.compile(
    r'id="ais-lastTime"[^>]*>\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})'
)

# The flag is only shown as an image; its country code is in the file
# name: <img src=".../flags/EST.png" ... id="ais-flagImg" />.
_FLAG_PATTERN = re.compile(r'/flags/([A-Za-z]+)\.png[^>]*id="ais-flagImg"')


def _field(html, key):
    """Value of the `id="ais-<key>"` info cell, tags stripped and HTML
    entities for common units decoded. ShipFinder's "not available"
    sentinel is a lone '-', normalised to ''."""
    match = re.search(_FIELD_TEMPLATE.format(key=re.escape(key)), html, re.DOTALL)
    if not match:
        return ""
    value = re.sub(r"<[^>]+>", "", match.group(1))
    value = value.replace("&#176;", "°").replace("&deg;", "°")
    value = re.sub(r"\s+", " ", value).strip()
    return "" if value == "-" else value


def _to_decimal_degrees(raw):
    """'49-38.752 N' -> 49.645867; '1-37.201 W' -> -1.620017. Returns
    None if it doesn't parse."""
    match = _COORD_PATTERN.search(raw or "")
    if not match:
        return None
    degrees = int(match.group(1)) + float(match.group(2)) / 60.0
    if match.group(3) in ("S", "W"):
        degrees = -degrees
    return round(degrees, 6)


def _reported_at(html):
    """The 'reported at' time as an ISO-8601 UTC string
    ('2026-09-02T16:01:54+00:00'), or '' if not present. ShipFinder
    shows the time without a zone; like the other sources it's taken
    as UTC."""
    match = _REPORTED_AT_PATTERN.search(html)
    if not match:
        return ""
    return f"{match.group(1)}T{match.group(2)}+00:00"


def _flag(html):
    """Country code from the flag image's file name (e.g. 'EST'), or ''
    if the image isn't present."""
    match = _FLAG_PATTERN.search(html)
    return match.group(1) if match else ""


def _size(html):
    """'<length> x <width> m' from the Length/Width cells (each like
    '14 m'), or '' if neither is present."""
    length = _field(html, "_length").replace(" m", "").strip()
    width = _field(html, "_width").replace(" m", "").strip()
    if not length and not width:
        return ""
    return f"{length} x {width} m"


def fetch(mmsi, timeout):
    """Fetch the vessel detail page and read its AIS fix and static
    vessel details. Returns None if the page yields no coordinates."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=timeout
    )
    response.raise_for_status()
    html = response.text

    lat = _to_decimal_degrees(_field(html, "_lat"))
    lon = _to_decimal_degrees(_field(html, "_lon"))
    if lat is None or lon is None:
        return None

    row = blank_row(SOURCE)
    row.update(
        lat=lat,
        lon=lon,
        reported_at=_reported_at(html),
        speed=_field(html, "_sog"),
        course=_field(html, "course_f"),
        area=_field(html, "dest"),
        status=_field(html, "shipStatus"),
        draught=_field(html, "_draught"),
        imo=_field(html, "imo"),
        flag=_flag(html),
        call_sign=_field(html, "callsign"),
        size=_size(html),
    )
    return row
