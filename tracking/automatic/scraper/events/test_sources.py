"""
Unit tests for the individual event source modules (sources/). Run with:
    pytest test_sources.py
(requires pytest, dev-only, not in requirements.txt).

These use small hand-built HTML / RSC fixtures rather than network calls;
the orchestrator glue is tested in test_fetch_events.py.
"""

import json
from unittest.mock import MagicMock, patch

from sources import SOURCES, aisvesseltracker, myshiptracking
from sources._common import EVENT_FIELDS, blank_event


def _response(text):
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


# --- shared contract -----------------------------------------------------

def test_every_source_declares_name_and_fetch():
    for source in SOURCES:
        assert isinstance(source.SOURCE, str) and source.SOURCE
        assert callable(source.fetch)


def test_blank_event_has_all_fields_empty():
    event = blank_event()
    assert set(event) == set(EVENT_FIELDS)
    assert all(value == "" for value in event.values())


# --- myshiptracking ----------------------------------------------------

MST_HTML = (
    '<tbody class="table-body">'
    "<tr>"
    "<td>2026-08-27 <b>05:12</b></td>"
    '<td><i class="fa fa-anchor"></i> PORT DEPARTURE </td>'
    '<td><a href="#"><img title=" France "/> DUNKERQUE</a></td>'
    '<td><div class="area_txt_1lines">51.06301 / 2.34976</div></td>'
    "<td>Speed: 7.1 kn<br>Course: 329.5° </td>"
    "</tr>"
    "<tr>"
    "<td>2026-08-27 <b>08:17</b></td>"
    '<td><i class="fa fa-map"></i> Change Sea Area </td>'
    "<td></td>"
    '<td><div class="area_txt_1lines">50.97497 / 1.65315</div></td>'
    "<td>Speed: 8.7 kn<br>Course: 227.1° </td>"
    "</tr>"
    "<tr>"
    "<td>2026-09-01 <b>20:02</b></td>"
    '<td><i class="fa fa-signal"></i> OUT of Coverage </td>'
    "<td></td>"
    '<td><div class="area_txt_1lines">50.04312 / -0.22798</div></td>'
    "<td>Speed: 5.7 kn<br>Course: 228.5° </td>"
    "</tr>"
    "</tbody>"
    "<div>Showing 1 - 3 of 3 Results</div>"
)


def test_myshiptracking_parses_rows_and_stops_on_last_page():
    with patch(
        "sources.myshiptracking.requests.get", return_value=_response(MST_HTML)
    ):
        events = myshiptracking.fetch("276017710", timeout=5, lookback_days=30)
    assert [e["event"] for e in events] == [
        "PORT DEPARTURE", "Change Sea Area", "OUT of Coverage"
    ]
    first = events[0]
    assert first["date"] == "2026-08-27" and first["time"] == "05:12"
    assert first["port"] == "DUNKERQUE" and first["country"] == "France"
    assert first["lat"] == "51.06301" and first["lon"] == "2.34976"
    assert first["speed"] == "7.1 kn" and first["course"] == "329.5°"
    # non-port event leaves port/country blank
    assert events[1]["port"] == "" and events[1]["country"] == ""


def test_myshiptracking_paginates_until_results_exhausted():
    page1 = MST_HTML.replace(
        "Showing 1 - 3 of 3 Results", "Showing 1 - 3 of 5 Results"
    )
    page2 = (
        '<tbody class="table-body">'
        "<tr>"
        "<td>2026-09-02 <b>03:00</b></td>"
        '<td><i class="fa fa-signal"></i> IN Coverage </td>'
        "<td></td>"
        '<td><div class="area_txt_1lines">50.1 / 0.5</div></td>'
        "<td>Speed: 6.0 kn<br>Course: 90.0° </td>"
        "</tr>"
        "</tbody>"
        "<div>Showing 4 - 5 of 5 Results</div>"
    )
    empty = '<tbody class="table-body"></tbody>'
    pages = [page1, page2, empty]
    with patch(
        "sources.myshiptracking.requests.get",
        side_effect=lambda *a, **k: _response(pages.pop(0)),
    ), patch("sources.myshiptracking.time_module.sleep"):
        events = myshiptracking.fetch("1", timeout=5, lookback_days=30)
    assert [e["event"] for e in events] == [
        "PORT DEPARTURE", "Change Sea Area", "OUT of Coverage", "IN Coverage"
    ]


def test_myshiptracking_returns_empty_when_no_rows():
    with patch(
        "sources.myshiptracking.requests.get",
        return_value=_response('<tbody class="table-body"></tbody>'),
    ):
        assert myshiptracking.fetch("1", timeout=5, lookback_days=30) == []


# --- aisvesseltracker ------------------------------------------------

AVT_EVENTS = [
    {
        "id": 1, "mmsi": 276017710, "ship_name": "SANUK",
        "event_type": "waterbody_changed",
        "old_value": "Land", "new_value": "English Channel",
        "latitude": 50.17565, "longitude": 0.55532,
        "sog": 6.3, "cog": 247.2, "water_body": "English Channel",
        "timestamp": "$D2026-09-01T14:35:50.000Z",
    },
    {
        "id": 2, "mmsi": 276017710, "ship_name": "SANUK",
        "event_type": "port_arrival",
        "new_value": "boulognesurmer_fr_bol",
        "latitude": 50.72807, "longitude": 1.59718,
        "sog": 0, "cog": 18.5, "water_body": "English Channel",
        "timestamp": "$D2026-08-27T11:17:17.000Z",
    },
    {
        "id": 3, "mmsi": 276017710, "ship_name": "SANUK",
        "event_type": "started_moving",
        "latitude": 50.72627, "longitude": 1.59885,
        "sog": 4.2, "cog": 333.5, "water_body": "Land",
        "timestamp": "$D2026-09-01T05:41:45.000Z",
    },
]


def _avt_html(events):
    """Wrap an initialEvents payload the way Next.js flushes it into the
    page: a __next_f.push chunk carrying an escaped JSON string, with the
    RSC "$D" Date markers on timestamps."""
    inner = (
        '23:["$","$L25",null,{"mmsi":"276017710","initialEvents":'
        + json.dumps({"data": events})
        + '}]\n'
    )
    return (
        "<html><body>"
        + f"<script>self.__next_f.push([1,{json.dumps(inner)}])</script>"
        + "</body></html>"
    )


def test_aisvesseltracker_parses_initial_events():
    with patch(
        "sources.aisvesseltracker.requests.get",
        return_value=_response(_avt_html(AVT_EVENTS)),
    ):
        events = aisvesseltracker.fetch("276017710", timeout=5, lookback_days=30)
    assert [e["event"] for e in events] == [
        "waterbody_changed", "port_arrival", "started_moving"
    ]
    wb = events[0]
    assert wb["date"] == "2026-09-01" and wb["time"] == "14:35"
    assert wb["lat"] == "50.17565" and wb["lon"] == "0.55532"
    assert wb["speed"] == "6.3" and wb["course"] == "247.2"
    assert wb["port"] == "" and wb["country"] == ""
    # port event carries the slug in `port`, country stays blank
    assert events[1]["port"] == "boulognesurmer_fr_bol"
    assert events[1]["country"] == ""


def test_aisvesseltracker_raises_without_events_payload():
    import pytest

    with patch(
        "sources.aisvesseltracker.requests.get",
        return_value=_response("<html><body>no data here</body></html>"),
    ):
        with pytest.raises(RuntimeError):
            aisvesseltracker.fetch("276017710", timeout=5, lookback_days=30)


def test_aisvesseltracker_skips_events_with_unparseable_timestamp():
    bad = dict(AVT_EVENTS[0], timestamp="")
    with patch(
        "sources.aisvesseltracker.requests.get",
        return_value=_response(_avt_html([bad, AVT_EVENTS[1]])),
    ):
        events = aisvesseltracker.fetch("1", timeout=5, lookback_days=30)
    assert [e["event"] for e in events] == ["port_arrival"]


def test_aisvesseltracker_split_timestamp():
    assert aisvesseltracker._split_timestamp("2026-09-01T14:35:50.000Z") == (
        "2026-09-01", "14:35"
    )
    assert aisvesseltracker._split_timestamp("$D2026-09-01T14:35:50.000Z") == (
        "2026-09-01", "14:35"
    )
    assert aisvesseltracker._split_timestamp("") == ("", "")
    assert aisvesseltracker._split_timestamp("not-a-date") == ("", "")
