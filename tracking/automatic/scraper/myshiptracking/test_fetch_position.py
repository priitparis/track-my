"""
Unit tests for the duplicate-position guard and distance tracking in
fetch_position.py. Run with:
    pytest test_fetch_position.py
(requires pytest, not listed in requirements.txt since it's dev-only —
install separately: pip install pytest)
"""

from unittest.mock import MagicMock, patch

from fetch_position import (
    BASE_DISTANCE_NM,
    SHEET_COLUMNS,
    append_to_sheet,
    compute_full_distance,
    haversine_nm,
    is_duplicate_position,
)


def _values(*rows):
    header = ["Lat", "Lon", "Time"]
    return [header, *rows]


def _sheet_with_last_row(*rows):
    sheet = MagicMock()
    sheet.get_all_values.return_value = _values(*rows)
    return sheet


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


def test_append_to_sheet_writes_new_position_with_full_distance():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    gc = MagicMock()
    gc.open_by_key.return_value.worksheet.return_value = sheet
    row_data = {col: "" for col in SHEET_COLUMNS}
    row_data.update(lat=54.50, lon=10.13)

    with patch("fetch_position.gspread.authorize", return_value=gc), \
         patch("fetch_position.Credentials.from_service_account_file"):
        written = append_to_sheet("dummy-key.json", "dummy-sheet-id", "Scraper", row_data)

    assert written is True
    expected_full_distance = round(
        BASE_DISTANCE_NM + haversine_nm(54.32, 10.13, 54.50, 10.13), 4
    )
    row_data["full_distance"] = expected_full_distance
    sheet.append_row.assert_called_once_with([row_data[col] for col in SHEET_COLUMNS])
