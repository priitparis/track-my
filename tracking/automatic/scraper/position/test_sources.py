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

MR_LDJSON = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"WebPage","@id":"x"},
 {"@type":"Boat","name":"SANUK",
  "identifier":[{"@type":"PropertyValue","propertyID":"MMSI","value":"276017710"}],
  "nationality":{"@type":"Country","name":"EE"},
  "location":{"@type":"GeoCoordinates","latitude":50.724968,"longitude":1.5996766,
    "observationDate":"2026-08-28T06:51:58Z"},
  "additionalProperty":[
    {"@type":"PropertyValue","propertyID":"speedOverGround","value":5.7,"unitText":"knots"},
    {"@type":"PropertyValue","propertyID":"courseOverGround","value":173,"unitText":"degrees"},
    {"@type":"PropertyValue","propertyID":"heading","value":511,"unitText":"degrees"},
    {"@type":"PropertyValue","propertyID":"navigationStatus","value":"Class B"}
  ]}
]}
</script>
"""


def test_marineradar_fetch_parses_jsonld_boat_node():
    with patch("sources.marineradar.requests.get", return_value=_response(MR_LDJSON)):
        row = marineradar.fetch("276017710", timeout=5)
    assert row["lat"] == 50.724968 and row["lon"] == 1.5996766
    assert row["reported_at"] == "2026-08-28T06:51:58+00:00"
    assert row["speed"] == "5.7 knots"
    assert row["course"] == "173 degrees"
    assert row["status"] == "Class B"
    assert row["flag"] == "EE"
    assert row["source"] == "marineradar"
    # Fields MarineRadar's JSON-LD doesn't carry stay blank.
    assert row["area"] == "" and row["draught"] == "" and row["temperature"] == ""


def test_marineradar_fetch_returns_none_without_boat_node():
    with patch("sources.marineradar.requests.get", return_value=_response("<html>nothing</html>")):
        assert marineradar.fetch("276017710", timeout=5) is None


def test_marineradar_fetch_returns_none_without_coordinates():
    ldjson = (
        '<script type="application/ld+json">'
        '{"@type":"Boat","location":{"@type":"GeoCoordinates"}}'
        "</script>"
    )
    with patch("sources.marineradar.requests.get", return_value=_response(ldjson)):
        assert marineradar.fetch("276017710", timeout=5) is None


def test_marineradar_normalizes_trailing_z():
    assert marineradar._normalize_iso_utc("2026-08-28T06:51:58Z") == "2026-08-28T06:51:58+00:00"
    assert marineradar._normalize_iso_utc("") == ""
