"""
MarineRadar.com position source.

The vessel page is a Next.js app that streams its server-rendered data
into the served HTML as `self.__next_f.push([...])` chunks. Concatenating
those chunks and pulling out the embedded `"ship": { ... }` object gives
a clean structured record — position, AIS timestamp, speed/course/
heading, navigation status, plus static vessel details (call sign, IMO,
dimensions, tonnage, year built) when MarineRadar has them. This is more
complete and more stable than scraping the page's styled HTML cards.

Weather isn't in that payload — the page fetches it client-side from
MarineRadar's own `GET /api/weather?lat=&lon=` endpoint (an Open-Meteo
passthrough), which this module calls directly as a second request.
"""

import json
import re

import requests

from ._common import USER_AGENT, blank_row

SOURCE = "marineradar"

PAGE_URL_TEMPLATE = "https://www.marineradar.com/vessel/mmsi-{mmsi}"
WEATHER_URL = "https://www.marineradar.com/api/weather"

# Next.js flushes server data as: self.__next_f.push([1,"<json-string>"])
_NEXT_F_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[.,("(?:[^"\\]|\\.)*")\]\)', re.DOTALL
)

# AIS "heading" sentinel meaning "not available".
_HEADING_NOT_AVAILABLE = 511


def _rsc_blob(html):
    """Concatenate the decoded payloads of every __next_f.push chunk."""
    parts = []
    for raw in _NEXT_F_PATTERN.findall(html):
        try:
            parts.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _extract_ship(blob):
    """Pull the `"ship": { ... }` object out of the concatenated RSC
    blob by brace-matching. Returns the parsed dict, or None."""
    marker = blob.find('"ship":{')
    if marker == -1:
        return None
    start = marker + len('"ship":')
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
    """'' for None/blank, else str(value), optionally with a unit
    appended ('5.7' -> '5.7 knots') to match how the other source labels
    the same sheet column."""
    if value in (None, ""):
        return ""
    return f"{value} {unit}" if unit else str(value)


def _dimensions_size(ship):
    """MarineRadar stores AIS reference-point offsets a/b (bow/stern) and
    c/d (port/starboard). length = a+b, beam = c+d. Returns '' if both
    come out zero (i.e. not reported)."""
    length = (ship.get("dimension_a") or 0) + (ship.get("dimension_b") or 0)
    beam = (ship.get("dimension_c") or 0) + (ship.get("dimension_d") or 0)
    if not length and not beam:
        return ""
    return f"{length} x {beam} m"


def _fetch_weather(session, lat, lon, timeout):
    """Best-effort current weather from MarineRadar's Open-Meteo
    passthrough. Returns a dict of sheet fields (possibly empty); never
    raises."""
    fields = {}
    try:
        resp = session.get(
            WEATHER_URL, params={"lat": lat, "lon": lon}, timeout=timeout
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
    except (requests.RequestException, ValueError):
        return fields

    def put(key, value, unit):
        if value not in (None, ""):
            fields[key] = f"{value} {unit}"

    put("temperature", current.get("temperature_2m"), "°C")
    put("humidity", current.get("relative_humidity_2m"), "%")
    put("pressure", current.get("pressure_msl"), "hPa")
    put("wind_speed", current.get("wind_speed_10m"), "km/h")
    put("wind_direction", current.get("wind_direction_10m"), "°")
    # No cloud-cover value in this response (only a WMO weather_code),
    # so `cloud_coverage` stays blank.
    return fields


def _normalize_iso_utc(value):
    """'2026-08-28T06:51:58Z' -> '2026-08-28T06:51:58+00:00'; '' for
    falsy input."""
    if not value:
        return ""
    return value[:-1] + "+00:00" if value.endswith("Z") else value


def fetch(mmsi, timeout):
    """Fetch the vessel page, parse its embedded `ship` record, and add
    current weather from /api/weather. Returns None if the page yields no
    ship object or no coordinates."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    url = PAGE_URL_TEMPLATE.format(mmsi=mmsi)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()

    ship = _extract_ship(_rsc_blob(response.text))
    if not ship:
        return None
    coords = (ship.get("location") or {}).get("coordinates") or []
    if len(coords) < 2 or coords[0] is None or coords[1] is None:
        return None
    lon, lat = float(coords[0]), float(coords[1])

    row = blank_row(SOURCE)
    row.update(
        lat=lat,
        lon=lon,
        reported_at=_normalize_iso_utc(ship.get("last_position")),
        speed=_num(ship.get("speed"), "knots"),
        course=_num(ship.get("course"), "°"),
        status=_num(ship.get("navigation_status")),
        imo=_num(ship.get("imo_number")),
        flag=_num(ship.get("country")),
        call_sign=_num(ship.get("call_sign")),
        size=_dimensions_size(ship),
        gt=_num(ship.get("gross_tonnage")),
        dwt=_num(ship.get("dead_weight")),
        build=_num(ship.get("year_built")),
        draught=_num(ship.get("current_draught") or ship.get("maximum_static_draught")),
    )
    row.update(_fetch_weather(session, lat, lon, timeout))
    return row
