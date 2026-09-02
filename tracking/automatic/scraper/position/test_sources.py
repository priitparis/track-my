"""
Unit tests for the individual position source modules (sources/). Run with:
    pytest test_sources.py
(requires pytest, dev-only, not in requirements.txt).

These use small hand-built HTML fixtures rather than network calls; the
orchestrator glue is tested in test_fetch_position.py.
"""

from unittest.mock import MagicMock, patch

from sources import (
    SOURCES,
    aisvesseltracker,
    marineradar,
    myshiptracking,
    shipfinder,
)
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


# --- shipfinder -------------------------------------------------------

SF_HTML = (
    '<h1><img src="https://api.shipxy.com/apiresource/flags/EST.png" '
    'class="mr_10" id="ais-flagImg" /><label id="ais-name">SANUK</label></h1>'
    '<div class="status-description">The current position of <strong>SANUK</strong> '
    'is in <span class="highlight">49-38.752 N, 1-37.201 W</span> reported at '
    '<span class="highlight">2026-09-02 16:01:54</span>.</div>'
    '<div class="info-grid">'
    '<div class="info-label">IMO</div><div class="info-value" id="ais-imo">-</div>'
    '<div class="info-label">Call Sign</div>'
    '<div class="info-value" id="ais-callsign">ES4371</div>'
    '<div class="info-label">Length</div>'
    '<div class="info-value" id="ais-_length">14 m</div>'
    '<div class="info-label">Width</div>'
    '<div class="info-value" id="ais-_width">5 m</div>'
    '<div class="info-label">Lat</div>'
    '<div class="info-value" id="ais-_lat">49-38.752 N</div>'
    '<div class="info-label">Lon</div>'
    '<div class="info-value" id="ais-_lon">1-37.201 W</div>'
    '<div class="info-label">Course</div>'
    '<div class="info-value" id="ais-course_f">173.8 &#176;</div>'
    '<div class="info-label">Speed</div>'
    '<div class="info-value" id="ais-_sog">5.7 kn</div>'
    '<div class="info-label">Draught</div>'
    '<div class="info-value" id="ais-_draught">-</div>'
    '<div class="info-label">Dest</div>'
    '<div class="info-value" id="ais-dest">-</div>'
    '<div class="info-label">Status</div>'
    '<div class="info-value" id="ais-shipStatus">Under way</div>'
    '<div class="info-label">Last update</div>'
    '<div class="info-value" id="ais-lastTime">2026-09-02 16:01:54</div>'
    '</div>'
)


def test_shipfinder_fetch_parses_core_fields():
    with patch("sources.shipfinder.requests.get", return_value=_response(SF_HTML)):
        row = shipfinder.fetch("276017710", timeout=5)
    # 49 + 38.752/60 ; -(1 + 37.201/60)
    assert row["lat"] == 49.645867
    assert row["lon"] == -1.620017
    assert row["reported_at"] == "2026-09-02T16:01:54+00:00"
    assert row["speed"] == "5.7 kn"
    assert row["course"] == "173.8 °"          # &#176; decoded
    assert row["status"] == "Under way"
    assert row["flag"] == "EST"                # from the flag image file name
    assert row["call_sign"] == "ES4371"
    assert row["size"] == "14 x 5 m"
    assert row["imo"] == ""                    # lone '-' -> blank
    assert row["draught"] == ""
    assert row["area"] == ""
    assert row["source"] == "shipfinder"


def test_shipfinder_fetch_returns_none_without_coordinates():
    with patch(
        "sources.shipfinder.requests.get",
        return_value=_response("<html>no position here</html>"),
    ):
        assert shipfinder.fetch("276017710", timeout=5) is None


def test_shipfinder_to_decimal_degrees():
    assert shipfinder._to_decimal_degrees("49-38.752 N") == 49.645867
    assert shipfinder._to_decimal_degrees("1-37.201 W") == -1.620017
    assert shipfinder._to_decimal_degrees("0-00.000 S") == 0.0
    assert shipfinder._to_decimal_degrees("-") is None
    assert shipfinder._to_decimal_degrees("") is None


# --- aisvesseltracker ------------------------------------------------

AVT_INITIAL_DATA = {
    "id": 276017710,
    "cog": 228.5,
    "sog": 5.7,
    "shipName": "SANUK",
    "callSign": "ES4371",
    "maxDraught": 2.4,
    "imoNumber": 0,               # site's "unknown" sentinel -> blank
    "flag": "EE",
    "country": "Estonia",
    "navigationalStatus": "Under way using engine",
    "time_utc": "2026-09-01T20:02:30Z",
    "length": 14,
    "beam": 5,
    "destination": "BOULOGNE",
    "avgSpeed": 2.9085613523045124,
    "maxSpeed": 10.5,
    "longitude": -0.22798,
    "latitude": 50.04312,
    "weather": {
        "temperature_c": 18.295480796160025,
        "pressure_hpa": 1021.6848037611519,
        "wind_speed_10m_ms": 5.288364414654898,
        "wind_direction_10m_deg": 271.1325592850968,
    },
}


def _avt_html(initial_data):
    """Wrap an initialData object the way Next.js flushes it into the
    page: a __next_f.push chunk carrying an escaped JSON string."""
    import json as _json

    inner = '23:["$","$L25",null,{"mmsi":"276017710","initialData":' \
        + _json.dumps(initial_data) + '}]\n'
    return (
        "<html><body>"
        + f'<script>self.__next_f.push([1,{_json.dumps(inner)}])</script>'
        + "</body></html>"
    )


def test_aisvesseltracker_fetch_parses_initial_data():
    html = _avt_html(AVT_INITIAL_DATA)
    with patch("sources.aisvesseltracker.requests.get", return_value=_response(html)):
        row = aisvesseltracker.fetch("276017710", timeout=5)
    assert row["lat"] == 50.04312 and row["lon"] == -0.22798
    assert row["reported_at"] == "2026-09-01T20:02:30+00:00"
    assert row["speed"] == "5.7 knots"
    assert row["course"] == "228.5 °"
    assert row["status"] == "Under way using engine"
    assert row["area"] == "BOULOGNE"
    assert row["draught"] == "2.4"
    assert row["imo"] == ""                     # 0 sentinel -> blank
    assert row["flag"] == "EE"
    assert row["call_sign"] == "ES4371"
    assert row["size"] == "14 x 5 m"
    assert row["avg_speed"] == "2.9 knots"
    assert row["max_speed"] == "10.5 knots"
    assert row["temperature"] == "18.3 °C"
    assert row["pressure"] == "1021.7 hPa"
    assert row["wind_speed"] == "5.3 m/s"
    assert row["wind_direction"] == "271.1 °"
    assert row["humidity"] == "" and row["cloud_coverage"] == ""
    assert row["source"] == "aisvesseltracker"


def test_aisvesseltracker_zero_sentinels_stay_blank():
    data = dict(AVT_INITIAL_DATA, maxDraught=0, length=0, beam=0, callSign="")
    with patch(
        "sources.aisvesseltracker.requests.get",
        return_value=_response(_avt_html(data)),
    ):
        row = aisvesseltracker.fetch("276017710", timeout=5)
    assert row["draught"] == "" and row["size"] == "" and row["call_sign"] == ""


def test_aisvesseltracker_fetch_returns_none_without_initial_data():
    with patch(
        "sources.aisvesseltracker.requests.get",
        return_value=_response("<html><body>no data</body></html>"),
    ):
        assert aisvesseltracker.fetch("276017710", timeout=5) is None


def test_aisvesseltracker_fetch_returns_none_without_coordinates():
    data = dict(AVT_INITIAL_DATA)
    del data["latitude"]
    with patch(
        "sources.aisvesseltracker.requests.get",
        return_value=_response(_avt_html(data)),
    ):
        assert aisvesseltracker.fetch("276017710", timeout=5) is None


def test_aisvesseltracker_normalizes_trailing_z():
    assert aisvesseltracker._normalize_iso_utc("2026-09-01T20:02:30Z") == "2026-09-01T20:02:30+00:00"
    assert aisvesseltracker._normalize_iso_utc("") == ""
