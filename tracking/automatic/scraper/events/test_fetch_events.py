"""
Unit tests for the orchestrator in fetch_events.py: source collection
(union + error separation), the ISO timestamp helper, and the
duplicate-event guard in append_new_events. Run with:
    pytest test_fetch_events.py
(requires pytest, not in requirements.txt since it's dev-only).

Source-specific parsing is covered in test_sources.py.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from fetch_events import (
    append_new_events,
    collect_events,
    event_time_iso,
    existing_keys,
)


def _event(date, time, event, **overrides):
    base = {
        "date": date, "time": time, "event": event,
        "port": "", "country": "", "lat": "", "lon": "",
        "speed": "", "course": "",
    }
    base.update(overrides)
    return base


def _fake_source(name, events=None, exc=None):
    def fetch(mmsi, timeout, lookback_days):
        if exc is not None:
            raise exc
        return events or []
    return SimpleNamespace(SOURCE=name, __name__=name, fetch=fetch)


# --- collect_events ---------------------------------------------------

def test_collect_events_unions_every_source():
    a = _fake_source("a", [_event("2026-08-27", "05:12", "PORT DEPARTURE")])
    b = _fake_source("b", [
        _event("2026-09-01", "14:35", "waterbody_changed"),
        _event("2026-09-01", "05:41", "started_moving"),
    ])
    with patch("fetch_events.SOURCES", [a, b]):
        events, errors = collect_events("1", timeout=5, lookback_days=30)
    assert errors == []
    assert sorted(e["event"] for e in events) == [
        "PORT DEPARTURE", "started_moving", "waterbody_changed"
    ]


def test_collect_events_separates_errors_and_keeps_the_rest():
    good = _fake_source("good", [_event("2026-08-27", "05:12", "PORT DEPARTURE")])
    boom = _fake_source("boom", exc=requests.RequestException("timeout"))
    broken = _fake_source("broken", exc=KeyError("unexpected shape"))
    with patch("fetch_events.SOURCES", [good, boom, broken]):
        events, errors = collect_events("1", timeout=5, lookback_days=30)
    assert [e["event"] for e in events] == ["PORT DEPARTURE"]
    names = [name for name, _ in errors]
    assert names == ["boom", "broken"]
    assert "request failed" in dict(errors)["boom"]
    assert "parse failed" in dict(errors)["broken"]


def test_collect_events_runs_sources_concurrently():
    import time

    active = []
    max_active = []

    def slow_fetch(mmsi, timeout, lookback_days):
        active.append(1)
        max_active.append(len(active))
        time.sleep(0.1)
        active.pop()
        return [_event("2026-08-27", "05:12", "PORT DEPARTURE")]

    sources = [
        SimpleNamespace(SOURCE=f"s{i}", __name__=f"s{i}", fetch=slow_fetch)
        for i in range(3)
    ]
    with patch("fetch_events.SOURCES", sources):
        start = time.monotonic()
        events, _ = collect_events("1", timeout=5, lookback_days=30)
        elapsed = time.monotonic() - start
    assert len(events) == 3
    assert max(max_active) == 3
    assert elapsed < 0.25


# --- event_time_iso -------------------------------------------------

def test_event_time_iso_builds_utc_timestamp():
    assert event_time_iso(_event("2026-08-27", "05:12", "x")) == "2026-08-27T05:12:00Z"


# --- append_new_events (dedup) --------------------------------------

def _sheet_with_rows(*data_rows):
    header = ["Lat", "Lon", "Time", "Event", "Port", "Country", "Speed", "Course"]
    sheet = MagicMock()
    sheet.get_all_values.return_value = [header, *data_rows]
    return sheet


def _patch_sheet(sheet):
    gc = MagicMock()
    gc.open_by_key.return_value.worksheet.return_value = sheet
    creds_patch = patch(
        "fetch_events.Credentials.from_service_account_file", return_value=MagicMock()
    )
    authorize_patch = patch("fetch_events.gspread.authorize", return_value=gc)
    return creds_patch, authorize_patch


def test_existing_keys_reads_time_and_event_columns():
    sheet = _sheet_with_rows(
        ["1", "2", "2026-08-27T05:12:00Z", "PORT DEPARTURE", "", "", "", ""],
        ["3", "4", "2026-09-01T14:35:00Z", "waterbody_changed", "", "", "", ""],
    )
    assert existing_keys(sheet) == {
        ("2026-08-27T05:12:00Z", "PORT DEPARTURE"),
        ("2026-09-01T14:35:00Z", "waterbody_changed"),
    }


def test_append_new_events_skips_events_already_in_sheet():
    sheet = _sheet_with_rows(
        ["1", "2", "2026-08-27T05:12:00Z", "PORT DEPARTURE", "", "", "", ""],
    )
    events = [
        _event("2026-08-27", "05:12", "PORT DEPARTURE"),          # dup
        _event("2026-09-01", "14:35", "waterbody_changed", lat="50.1", lon="0.5"),
    ]
    creds_patch, authorize_patch = _patch_sheet(sheet)
    with creds_patch, authorize_patch:
        added = append_new_events("key.json", "sheet-id", "Events", events)
    assert added == 1
    sheet.append_rows.assert_called_once()
    appended = sheet.append_rows.call_args[0][0]
    assert appended == [
        ["50.1", "0.5", "2026-09-01T14:35:00Z", "waterbody_changed", "", "", "", ""]
    ]


def test_append_new_events_dedupes_within_one_batch():
    sheet = _sheet_with_rows()  # empty sheet
    events = [
        _event("2026-08-27", "11:17", "port_arrival", lat="50.7", lon="1.5"),
        _event("2026-08-27", "11:17", "port_arrival", lat="50.7", lon="1.5"),
        _event("2026-08-27", "11:17", "stopped_moving", lat="50.7", lon="1.5"),
    ]
    creds_patch, authorize_patch = _patch_sheet(sheet)
    with creds_patch, authorize_patch:
        added = append_new_events("key.json", "sheet-id", "Events", events)
    assert added == 2


def test_append_new_events_appends_in_chronological_order():
    sheet = _sheet_with_rows()  # empty sheet
    # deliberately shuffled: two sources' events interleaved, out of order
    events = [
        _event("2026-09-01", "14:35", "waterbody_changed"),
        _event("2026-08-27", "11:17", "port_arrival"),
        _event("2026-09-01", "05:41", "started_moving"),
        _event("2026-08-27", "05:12", "PORT DEPARTURE"),
        _event("2026-09-01", "14:35", "IN Coverage"),  # same minute, other event
    ]
    creds_patch, authorize_patch = _patch_sheet(sheet)
    with creds_patch, authorize_patch:
        append_new_events("key.json", "sheet-id", "Events", events)
    appended = sheet.append_rows.call_args[0][0]
    times = [row[2] for row in appended]
    assert times == sorted(times)
    assert times == [
        "2026-08-27T05:12:00Z",
        "2026-08-27T11:17:00Z",
        "2026-09-01T05:41:00Z",
        "2026-09-01T14:35:00Z",
        "2026-09-01T14:35:00Z",
    ]
    # tie within the same minute is broken by Event name, deterministically
    same_minute = [row[3] for row in appended if row[2] == "2026-09-01T14:35:00Z"]
    assert same_minute == ["IN Coverage", "waterbody_changed"]


def test_append_new_events_writes_nothing_when_all_known():
    sheet = _sheet_with_rows(
        ["1", "2", "2026-08-27T05:12:00Z", "PORT DEPARTURE", "", "", "", ""],
    )
    events = [_event("2026-08-27", "05:12", "PORT DEPARTURE")]
    creds_patch, authorize_patch = _patch_sheet(sheet)
    with creds_patch, authorize_patch:
        added = append_new_events("key.json", "sheet-id", "Events", events)
    assert added == 0
    sheet.append_rows.assert_not_called()
