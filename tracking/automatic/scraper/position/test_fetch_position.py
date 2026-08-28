"""
Unit tests for the orchestrator in fetch_position.py: source collection,
freshest-fix selection, the duplicate-position guard and distance
tracking. Run with:
    pytest test_fetch_position.py
(requires pytest, not listed in requirements.txt since it's dev-only —
install separately: pip install pytest)

Source-specific parsing is covered in test_sources.py.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from fetch_position import (
    BASE_DISTANCE_NM,
    SHEET_COLUMNS,
    append_to_sheet,
    collect_positions,
    compute_full_distance,
    haversine_nm,
    is_duplicate_position,
    pick_freshest,
)


def _values(*rows):
    header = ["Lat", "Lon", "Time"]
    return [header, *rows]


def _sheet_with_last_row(*rows):
    sheet = MagicMock()
    sheet.get_all_values.return_value = _values(*rows)
    return sheet


def _fake_source(name, row=None, exc=None):
    def fetch(mmsi, timeout):
        if exc is not None:
            raise exc
        return row
    return SimpleNamespace(SOURCE=name, __name__=name, fetch=fetch)


# --- source collection & selection ---------------------------------------

def test_collect_positions_separates_results_from_errors():
    good = _fake_source("good", row={"lat": 1.0, "lon": 2.0, "reported_at": ""})
    boom = _fake_source("boom", exc=requests.RequestException("timeout"))
    none = _fake_source("none", row=None)
    with patch("fetch_position.SOURCES", [good, boom, none]):
        results, errors = collect_positions("123", timeout=5)
    assert [r["lat"] for _, r in results] == [1.0]
    assert [name for name, _ in errors] == ["boom", "none"]


def test_collect_positions_swallows_a_broken_parser():
    ok = _fake_source("ok", row={"lat": 1.0, "lon": 2.0, "reported_at": ""})
    broken = _fake_source("broken", exc=KeyError("unexpected shape"))
    with patch("fetch_position.SOURCES", [ok, broken]):
        results, errors = collect_positions("123", timeout=5)
    assert len(results) == 1
    assert errors[0][0] == "broken" and "parse failed" in errors[0][1]


def test_collect_positions_runs_sources_concurrently():
    import time

    active = []
    max_active = []

    def slow_fetch(mmsi, timeout):
        active.append(1)
        max_active.append(len(active))
        time.sleep(0.1)
        active.pop()
        return {"lat": 1.0, "lon": 2.0, "reported_at": ""}

    sources = [
        SimpleNamespace(SOURCE=f"s{i}", __name__=f"s{i}", fetch=slow_fetch)
        for i in range(3)
    ]
    with patch("fetch_position.SOURCES", sources):
        start = time.monotonic()
        results, _ = collect_positions("123", timeout=5)
        elapsed = time.monotonic() - start

    assert len(results) == 3
    # Ran in parallel: all three overlapped, and total time is ~one
    # sleep, not three.
    assert max(max_active) == 3
    assert elapsed < 0.25


def test_pick_freshest_returns_row_with_newest_reported_at():
    results = [
        (None, {"source": "a", "reported_at": "2026-06-01T00:00:00+00:00"}),
        (None, {"source": "b", "reported_at": "2026-06-02T12:00:00+00:00"}),
        (None, {"source": "c", "reported_at": "2026-06-01T18:00:00+00:00"}),
    ]
    assert pick_freshest(results)["source"] == "b"


def test_pick_freshest_breaks_ties_by_source_order():
    # Both blank reported_at -> first in list wins (max is stable).
    results = [
        (None, {"source": "primary", "reported_at": ""}),
        (None, {"source": "secondary", "reported_at": ""}),
    ]
    assert pick_freshest(results)["source"] == "primary"


def test_pick_freshest_prefers_a_dated_row_over_a_blank_one():
    results = [
        (None, {"source": "blank", "reported_at": ""}),
        (None, {"source": "dated", "reported_at": "2020-01-01T00:00:00+00:00"}),
    ]
    assert pick_freshest(results)["source"] == "dated"


def test_pick_freshest_of_nothing_is_none():
    assert pick_freshest([]) is None


# --- duplicate guard ---------------------------------------------------

def test_empty_sheet_is_not_duplicate():
    assert is_duplicate_position(_values(), 54.32, 10.13) is False


def test_identical_position_is_duplicate():
    values = _values(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(values, 54.32, 10.13) is True


def test_position_within_tolerance_is_duplicate():
    values = _values(["54.32000", "10.13000", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(values, 54.32009, 10.13009) is True


def test_position_beyond_tolerance_is_not_duplicate():
    values = _values(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(values, 54.33, 10.13) is False


def test_unparseable_last_row_is_not_duplicate():
    values = _values(["", "", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(values, 54.32, 10.13) is False


# --- full_distance ---------------------------------------------------

def test_compute_full_distance_with_empty_sheet_is_base_distance():
    assert compute_full_distance(_values(), 54.32, 10.13) == BASE_DISTANCE_NM


def test_compute_full_distance_uses_prior_full_distance_column():
    index = SHEET_COLUMNS.index("full_distance")
    last_row = [""] * len(SHEET_COLUMNS)
    last_row[0], last_row[1] = "54.32", "10.13"
    last_row[index] = "900.0"

    expected_leg = haversine_nm(54.32, 10.13, 54.40, 10.13)
    result = compute_full_distance(_values(last_row), 54.40, 10.13)

    assert result == 900.0 + expected_leg


def test_compute_full_distance_falls_back_to_base_when_column_missing():
    # A last row with no full_distance value yet (e.g. written before this
    # column existed) should still produce a sensible cumulative figure.
    last_row = ["54.32", "10.13", "2026-06-01T09:00:00Z"]
    expected_leg = haversine_nm(54.32, 10.13, 54.40, 10.13)
    result = compute_full_distance(_values(last_row), 54.40, 10.13)
    assert result == BASE_DISTANCE_NM + expected_leg


# --- sheet append ---------------------------------------------------

def test_source_column_is_last_in_sheet_columns():
    assert SHEET_COLUMNS[-1] == "source"


def test_append_to_sheet_skips_duplicate_row():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    gc = MagicMock()
    gc.open_by_key.return_value.worksheet.return_value = sheet
    row_data = {col: "" for col in SHEET_COLUMNS}
    row_data.update(lat=54.32, lon=10.13)

    with patch("fetch_position.gspread.authorize", return_value=gc), \
         patch("fetch_position.Credentials.from_service_account_file"):
        written = append_to_sheet("dummy-key.json", "dummy-sheet-id", "Scraper", row_data)

    assert written is False
    sheet.append_row.assert_not_called()


def test_append_to_sheet_writes_new_position_with_full_distance_and_source():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    gc = MagicMock()
    gc.open_by_key.return_value.worksheet.return_value = sheet
    row_data = {col: "" for col in SHEET_COLUMNS}
    row_data.update(lat=54.50, lon=10.13, source="marineradar")

    with patch("fetch_position.gspread.authorize", return_value=gc), \
         patch("fetch_position.Credentials.from_service_account_file"):
        written = append_to_sheet("dummy-key.json", "dummy-sheet-id", "Scraper", row_data)

    assert written is True
    expected_full_distance = round(
        BASE_DISTANCE_NM + haversine_nm(54.32, 10.13, 54.50, 10.13), 4
    )
    row_data["full_distance"] = expected_full_distance
    sheet.append_row.assert_called_once_with([row_data[col] for col in SHEET_COLUMNS])
    appended = sheet.append_row.call_args[0][0]
    assert appended[SHEET_COLUMNS.index("source")] == "marineradar"
