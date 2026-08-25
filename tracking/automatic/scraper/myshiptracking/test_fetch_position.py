"""
Unit tests for the duplicate-position guard in fetch_position.py. Run with:
    pytest test_fetch_position.py
(requires pytest, not listed in requirements.txt since it's dev-only —
install separately: pip install pytest)
"""

from unittest.mock import MagicMock

from fetch_position import is_duplicate_position, append_to_sheet, SHEET_COLUMNS


def _sheet_with_last_row(*rows):
    sheet = MagicMock()
    header = ["Lat", "Lon", "Time"]
    sheet.get_all_values.return_value = [header, *rows]
    return sheet


def test_empty_sheet_is_not_duplicate():
    sheet = _sheet_with_last_row()
    assert is_duplicate_position(sheet, 54.32, 10.13) is False


def test_identical_position_is_duplicate():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(sheet, 54.32, 10.13) is True


def test_position_within_tolerance_is_duplicate():
    sheet = _sheet_with_last_row(["54.32000", "10.13000", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(sheet, 54.32009, 10.13009) is True


def test_position_beyond_tolerance_is_not_duplicate():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(sheet, 54.33, 10.13) is False


def test_unparseable_last_row_is_not_duplicate():
    sheet = _sheet_with_last_row(["", "", "2026-06-01T09:00:00Z"])
    assert is_duplicate_position(sheet, 54.32, 10.13) is False


def test_append_to_sheet_skips_duplicate_row():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    gc = MagicMock()
    gc.open_by_key.return_value.worksheet.return_value = sheet
    row_data = {col: "" for col in SHEET_COLUMNS}
    row_data.update(lat=54.32, lon=10.13)

    from unittest.mock import patch
    with patch("fetch_position.gspread.authorize", return_value=gc), \
         patch("fetch_position.Credentials.from_service_account_file"):
        written = append_to_sheet("dummy-key.json", "dummy-sheet-id", "Scraper", row_data)

    assert written is False
    sheet.append_row.assert_not_called()


def test_append_to_sheet_writes_new_position():
    sheet = _sheet_with_last_row(["54.32", "10.13", "2026-06-01T09:00:00Z"])
    gc = MagicMock()
    gc.open_by_key.return_value.worksheet.return_value = sheet
    row_data = {col: "" for col in SHEET_COLUMNS}
    row_data.update(lat=54.50, lon=10.13)

    from unittest.mock import patch
    with patch("fetch_position.gspread.authorize", return_value=gc), \
         patch("fetch_position.Credentials.from_service_account_file"):
        written = append_to_sheet("dummy-key.json", "dummy-sheet-id", "Scraper", row_data)

    assert written is True
    sheet.append_row.assert_called_once_with([row_data[col] for col in SHEET_COLUMNS])
