"""
AISVesselTracker.com (Voyage Radar) position source.

The vessel page (by MMSI, at a slug URL like
`/vessel/<name>-mmsi-<mmsi>-imo-<imo>`) is a Next.js app that streams its
server-rendered data into the served HTML as `self.__next_f.push([...])`
chunks. Concatenating those chunks and brace-matching the embedded
`"initialData": { ... }` object gives one clean record with everything
this scraper needs: coordinates, `time_utc` (the AIS observation time),
speed/course/navigation-status, static details (call sign, IMO, flag,
dimensions, draught), current-trip figures (avg/max speed, destination),
and a nested `weather` object (temperature, pressure, wind).

Same parsing shape as sources/marineradar.py, which reads its own `ship`
object out of the same kind of Next.js payload.
"""

import json
import re

import requests

from ._common import USER_AGENT, blank_row

SOURCE = "aisvesseltracker"

# The vessel page redirects an MMSI-only path to its canonical slug, so
# hitting the slug form directly (with a throwaway name/imo) avoids the
# redirect; the site ignores the name part and matches on the MMSI.
PAGE_URL_TEMPLATE = "https://aisvesseltracker.com/vessel/ship-mmsi-{mmsi}-imo-0"

# Next.js flushes server data as: self.__next_f.push([1,"<json-string>"])
_NEXT_F_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[.,("(?:[^"\\]|\\.)*")\]\)', re.DOTALL
)


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
    by brace-matching. Returns the parsed dict, or None."""
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
                try:
                    return json.loads(blob[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _num(value, unit=""):
    """'' for None / blank / a zero sentinel (this site uses 0 for
    "unknown" on imo/draught/dimensions), else str(value), optionally
    with a unit appended to match how the other sources label the same
    sheet column."""
    if value in (None, "", 0, 0.0):
        return ""
    return f"{value} {unit}" if unit else str(value)


def _size(ship):
    """'<length> x <beam> m' from the AIS dimensions, or '' if neither
    is reported (both come as 0)."""
    length = ship.get("length") or 0
    beam = ship.get("beam") or 0
    if not length and not beam:
        return ""
    return f"{length} x {beam} m"


def _normalize_iso_utc(value):
    """'2026-09-01T20:02:30Z' -> '2026-09-01T20:02:30+00:00'; '' for
    falsy input."""
    if not value:
        return ""
    return value[:-1] + "+00:00" if value.endswith("Z") else value


def _weather_fields(weather):
    """Map the nested `weather` object to sheet columns. Returns a dict
    of the fields present (possibly empty). No humidity or cloud-cover
    figure in this payload, so those stay blank."""
    if not isinstance(weather, dict):
        return {}
    fields = {}

    def put(key, value, unit):
        if value not in (None, ""):
            fields[key] = f"{round(value, 1)} {unit}"

    put("temperature", weather.get("temperature_c"), "°C")
    put("pressure", weather.get("pressure_hpa"), "hPa")
    put("wind_speed", weather.get("wind_speed_10m_ms"), "m/s")
    put("wind_direction", weather.get("wind_direction_10m_deg"), "°")
    return fields


def fetch(mmsi, timeout):
    """Fetch the vessel page, parse its embedded `initialData` record.
    Returns None if the page yields no such object or no coordinates."""
    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=timeout
    )
    response.raise_for_status()

    ship = _extract_object(_rsc_blob(response.text), "initialData")
    if not ship:
        return None
    lat, lon = ship.get("latitude"), ship.get("longitude")
    if lat is None or lon is None:
        return None

    row = blank_row(SOURCE)
    row.update(
        lat=float(lat),
        lon=float(lon),
        reported_at=_normalize_iso_utc(ship.get("time_utc")),
        speed=_num(ship.get("sog"), "knots"),
        course=_num(ship.get("cog"), "°"),
        area=ship.get("destination") or "",
        status=ship.get("navigationalStatus") or "",
        draught=_num(ship.get("maxDraught")),
        imo=_num(ship.get("imoNumber")),
        flag=ship.get("flag") or ship.get("country") or "",
        call_sign=ship.get("callSign") or "",
        size=_size(ship),
        avg_speed=_num(ship.get("avgSpeed") and round(ship["avgSpeed"], 1), "knots"),
        max_speed=_num(ship.get("maxSpeed"), "knots"),
    )
    row.update(_weather_fields(ship.get("weather")))
    return row
