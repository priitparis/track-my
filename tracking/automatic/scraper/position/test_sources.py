"""
Unit tests for the individual position source modules (sources/). Run with:
    pytest test_sources.py
(requires pytest, dev-only, not in requirements.txt).

These use small hand-built HTML fixtures rather than network calls; the
orchestrator glue is tested in test_fetch_position.py.
"""

from unittest.mock import MagicMock, patch

from sources import SOURCES, marineradar, myshiptracking
from sources._common import SOURCE_FIELDS, blank_row


# --- shared contract -------------------------------------------------

def test_every_source_declares_name_and_fetch():
    for source in SOURCES:
        assert isinstance(source.SOURCE, str) and source.SOURCE
        assert callable(source.fetch)


def test_blank_row_has_all_fields_and_source():
    row = blank_row("x")
    assert set(row) == set(SOURCE_FIELDS)
    assert row["source"] == "x"
    assert all(v == "" for k, v in row.items() if k != "source")


# --- myshiptracking ------------------------------------------------

MST_HTML = (
    '<script>url: "/requests/contributorMap.php?lat=50.87918&lng=1.53006&data=full",</script>'
    "with coordinates <strong>50.87918° / 1.53006°</strong> as reported on "
    "<strong>2026-08-27 09:18</strong> by AIS to our vessel tracker app."
    '<div id="ft-info" class="container"><table>'
    "<tr><th>Flag</th><td>Estonia</td></tr><tr><th>Call Sign</th><td>ES4371</td></tr>"
    '</table><div id="ft-trip"><table>'
    "<tr><th>Distance Travelled</th><td>35.32 nm</td></tr>"
    '</table><div id="ft-position"><table>'
    "<tr><th>Speed</th><td>5.7 Knots</td></tr><tr><th>Course</th><td>173.8°</td></tr>"
    "<tr><th>Status</th><td>Default</td></tr>"
    '</table><div id="ft-info-mob"><div id="ft-weather"><table>'
    "<tr><th>Temperature</th><td>19.3°C</td></tr>"
    '</table><div id="ft-portcalls">'
)


def _response(text):
    resp = MagicMock()
    resp.text = text
    return resp


def test_myshiptracking_fetch_parses_core_fields():
    with patch("sources.myshiptracking.requests.get", return_value=_response(MST_HTML)):
        row = myshiptracking.fetch("276017710", timeout=5)
    assert row["lat"] == 50.87918 and row["lon"] == 1.53006
    assert row["reported_at"] == "2026-08-27T09:18:00+00:00"
    assert row["speed"] == "5.7 Knots"
    assert row["course"] == "173.8°"
    assert row["status"] == "Default"
    assert row["flag"] == "Estonia"
    assert row["call_sign"] == "ES4371"
    assert row["distance_travelled"] == "35.32 nm"
    assert row["temperature"] == "19.3°C"
    assert row["source"] == "myshiptracking"


def test_myshiptracking_fetch_returns_none_without_coordinates():
    with patch("sources.myshiptracking.requests.get", return_value=_response("<html>no map</html>")):
        assert myshiptracking.fetch("276017710", timeout=5) is None


def test_myshiptracking_parse_reported_at_blank_when_absent():
    assert myshiptracking.parse_reported_at("<p>nothing here</p>") == ""


def test_myshiptracking_dashes_become_blank():
    html = (
        '<script>url: "?lat=1.0&lng=2.0&data=full",</script>'
        '<div id="ft-info" class="container"><table><tr><th>Flag</th><td>---</td></tr>'
        '</table><div id="ft-trip"><div id="ft-position"><div id="ft-info-mob">'
    )
    with patch("sources.myshiptracking.requests.get", return_value=_response(html)):
        row = myshiptracking.fetch("1", timeout=5)
    assert row["flag"] == ""


# --- marineradar --------------------------------------------------

def _next_f_push(obj_json):
    """Wrap a JSON fragment the way Next.js flushes server data into the
    page: self.__next_f.push([1,"<json-string>"])."""
    import json as _json

    return f'<script>self.__next_f.push([1,{_json.dumps(obj_json)}])</script>'


def _mr_html(ship):
    import json as _json

    return (
        "<html><body>"
        + _next_f_push('1:["$","div",null,{}]\n')
        + _next_f_push('2b:["$","$L34",null,{"ship":' + _json.dumps(ship) + ',"x":1}]\n')
        + "</body></html>"
    )


MR_SHIP = {
    "mmsi": 276017710,
    "country": "EE",
    "call_sign": "ES4371",
    "imo_number": None,
    "current_draught": None,
    "maximum_static_draught": 2.4,
    "dimension_a": 8, "dimension_b": 6, "dimension_c": 2, "dimension_d": 3,
    "gross_tonnage": None,
    "dead_weight": None,
    "year_built": 2015,
    "speed": 5.7,
    "course": 173,
    "heading": 511,
    "navigation_status": "Class B",
    "last_position": "2026-08-28T06:51:58Z",
    "location": {"type": "Point", "coordinates": [1.5996766, 50.724968]},
}

MR_WEATHER = {
    "current": {
        "temperature_2m": 19.6,
        "relative_humidity_2m": 73,
        "pressure_msl": 1007.7,
        "wind_speed_10m": 15,
        "wind_direction_10m": 240,
        "weather_code": 3,
    }
}


class _FakeSession:
    """Stand-in for requests.Session: page GET returns the vessel HTML,
    the /api/weather GET returns MR_WEATHER (override via `weather`)."""

    def __init__(self, html, weather=MR_WEATHER, weather_exc=None):
        self.headers = {}
        self._html = html
        self._weather = weather
        self._weather_exc = weather_exc
        self.weather_calls = []

    def get(self, url, params=None, timeout=None):
        if url.endswith("/api/weather"):
            self.weather_calls.append(params)
            if self._weather_exc:
                raise self._weather_exc
            return _json_response(self._weather)
        return _response(self._html)


def _json_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _patch_session(session):
    return patch("sources.marineradar.requests.Session", return_value=session)


def test_marineradar_fetch_parses_ship_payload_and_weather():
    session = _FakeSession(_mr_html(MR_SHIP))
    with _patch_session(session):
        row = marineradar.fetch("276017710", timeout=5)
    assert row["lat"] == 50.724968 and row["lon"] == 1.5996766
    assert row["reported_at"] == "2026-08-28T06:51:58+00:00"
    assert row["speed"] == "5.7 knots"
    assert row["course"] == "173 °"
    assert row["status"] == "Class B"
    assert row["flag"] == "EE"
    assert row["call_sign"] == "ES4371"
    assert row["size"] == "14 x 5 m"           # (a+b) x (c+d)
    assert row["build"] == "2015"
    assert row["draught"] == "2.4"             # falls back to maximum_static_draught
    assert row["source"] == "marineradar"
    # weather from /api/weather
    assert row["temperature"] == "19.6 °C"
    assert row["humidity"] == "73 %"
    assert row["pressure"] == "1007.7 hPa"
    assert row["wind_speed"] == "15 km/h"
    assert row["wind_direction"] == "240 °"
    assert row["cloud_coverage"] == ""         # no cloud value in the response
    # queried the right coordinates
    assert session.weather_calls == [{"lat": 50.724968, "lon": 1.5996766}]


def test_marineradar_null_static_fields_stay_blank():
    ship = dict(MR_SHIP, call_sign=None, year_built=None,
                dimension_a=0, dimension_b=0, dimension_c=0, dimension_d=0)
    session = _FakeSession(_mr_html(ship))
    with _patch_session(session):
        row = marineradar.fetch("276017710", timeout=5)
    assert row["call_sign"] == "" and row["build"] == "" and row["size"] == ""


def test_marineradar_weather_failure_does_not_sink_position():
    import requests as _requests

    session = _FakeSession(
        _mr_html(MR_SHIP), weather_exc=_requests.ConnectionError("weather down")
    )
    with _patch_session(session):
        row = marineradar.fetch("276017710", timeout=5)
    assert row["lat"] == 50.724968
    assert row["temperature"] == "" and row["humidity"] == ""


def test_marineradar_fetch_returns_none_without_ship_payload():
    session = _FakeSession("<html><body>no data here</body></html>")
    with _patch_session(session):
        assert marineradar.fetch("276017710", timeout=5) is None


def test_marineradar_fetch_returns_none_without_coordinates():
    ship = dict(MR_SHIP, location={"type": "Point", "coordinates": []})
    session = _FakeSession(_mr_html(ship))
    with _patch_session(session):
        assert marineradar.fetch("276017710", timeout=5) is None


def test_marineradar_normalizes_trailing_z():
    assert marineradar._normalize_iso_utc("2026-08-28T06:51:58Z") == "2026-08-28T06:51:58+00:00"
    assert marineradar._normalize_iso_utc("") == ""
