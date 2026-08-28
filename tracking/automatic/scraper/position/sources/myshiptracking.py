"""
MyShipTracking.com position source.

Scrapes the ship's public vessel page (by MMSI). The page embeds precise
coordinates in a `<script>` block's AJAX URL string, and its
clearly-sectioned tables (`ft-info`, `ft-trip`, `ft-position`,
`ft-weather`) expose vessel, trip, and weather details, so a plain HTTP
request is enough — no JavaScript rendering.

This has been the primary source (fastest updates, most reliable
coverage found so far).
"""

import re
from datetime import datetime, timezone

import requests

from ._common import USER_AGENT, blank_row, strip_tags

SOURCE = "myshiptracking"

PAGE_URL_TEMPLATE = "https://www.myshiptracking.com/vessels/mmsi-{mmsi}"

# The vessel page embeds its own coordinates in a JS AJAX call, e.g.:
#   url: "/requests/contributorMap.php?lat=52.83194&lng=4.54917&data=full",
POSITION_PATTERN = re.compile(r"lat=([\d.\-]+)&lng=([\d.\-]+)")

# The page's prose summary states when the position was last reported by
# AIS, e.g.:
#   ... as reported on <strong>2026-08-27 09:18</strong> by AIS ...
# This is the actual AIS observation time (UTC, minute precision, no
# seconds or zone shown).
POSITION_REPORTED_PATTERN = re.compile(
    r"reported on\s*<strong>\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*</strong>"
)

# The page is split into clearly id'd sections; scoping field lookups to
# a section avoids matching a same-named field (e.g. "Draught",
# "Position Received") that appears in more than one table.
SECTION_PATTERN = {
    "info": re.compile(r'<div id="ft-info" class="container">(.*?)<div id="ft-trip"', re.DOTALL),
    "trip": re.compile(r'<div id="ft-trip".*?(?=<div id="ft-position")', re.DOTALL),
    "position": re.compile(r'<div id="ft-position".*?(?=<div id="ft-info-mob")', re.DOTALL),
    "weather": re.compile(r'<div id="ft-weather".*?(?=<div id="ft-portcalls")', re.DOTALL),
}


def _field_pattern(label):
    return re.compile(r"<th>" + re.escape(label) + r"</th>\s*<td>(.*?)</td>", re.DOTALL)


def _field(section_text, label):
    match = _field_pattern(label).search(section_text)
    if not match:
        return ""
    value = strip_tags(match.group(1))
    return "" if value == "---" else value


def parse_reported_at(html):
    """Extract the AIS 'reported on' time from the page's prose summary
    and return it as an ISO-8601 UTC string (e.g.
    '2026-08-27T09:18:00+00:00'). Returns '' if the sentence isn't
    present."""
    match = POSITION_REPORTED_PATTERN.search(html)
    if not match:
        return ""
    stamp = datetime.strptime(
        f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc)
    return stamp.isoformat()


def fetch(mmsi, timeout):
    """Fetch the vessel page and extract everything available: current
    position/status, static vessel info, current trip, and weather.
    Returns None if even the core (lat, lon) can't be found — every other
    field is best-effort and left blank if missing."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    html = response.text

    position_match = POSITION_PATTERN.search(html)
    if not position_match:
        return None

    sections = {}
    for name, pattern in SECTION_PATTERN.items():
        match = pattern.search(html)
        sections[name] = (
            match.group(1) if (match and match.groups())
            else (match.group(0) if match else "")
        )
    info = sections.get("info", "")
    trip = sections.get("trip", "")
    position = sections.get("position", "")
    weather = sections.get("weather", "")

    row = blank_row(SOURCE)
    row.update(
        lat=float(position_match.group(1)),
        lon=float(position_match.group(2)),
        reported_at=parse_reported_at(html),
        # Current position / status
        speed=_field(position, "Speed"),
        course=_field(position, "Course"),
        area=_field(position, "Area"),
        status=_field(position, "Status"),
        draught=_field(position, "Draught") or _field(trip, "Draught"),
        # Static vessel info
        imo=_field(info, "IMO"),
        flag=_field(info, "Flag"),
        call_sign=_field(info, "Call Sign"),
        size=_field(info, "Size"),
        gt=_field(info, "GT"),
        dwt=_field(info, "DWT"),
        build=_field(info, "Build"),
        # Current trip
        distance_travelled=_field(trip, "Distance Travelled"),
        remaining_distance=_field(trip, "Remaining Distance"),
        avg_speed=_field(trip, "AVG Speed"),
        max_speed=_field(trip, "MAX Speed"),
        time_travelled=_field(trip, "Time Travelled"),
        # Weather at the ship's current position
        temperature=_field(weather, "Temperature"),
        wind_speed=_field(weather, "Wind Speed"),
        wind_direction=_field(weather, "Direction"),
        pressure=_field(weather, "Pressure"),
        humidity=_field(weather, "Humidity"),
        cloud_coverage=_field(weather, "Cloud Coverage"),
    )
    return row
