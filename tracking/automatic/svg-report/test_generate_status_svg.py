"""
Unit tests for generate_status_svg.py. Run with:
    pytest test_generate_status_svg.py
(requires pytest, not listed in requirements.txt since it's dev-only —
install separately: pip install pytest)
"""

from generate_status_svg import (
    BASE_DISTANCE_NM,
    build_status,
    haversine_nm,
    render_svg,
    total_distance_nm,
)


def test_haversine_known_distance():
    # Tallinn to Helsinki is approximately 44 nm (~82 km) in a straight line.
    tallinn = (59.4370, 24.7536)
    helsinki = (60.1699, 24.9384)
    distance = haversine_nm(*tallinn, *helsinki)
    assert 42 <= distance <= 46


def test_haversine_zero_for_identical_points():
    assert haversine_nm(52.0, 4.0, 52.0, 4.0) == 0


def test_total_distance_adds_base_constant_to_live_sum():
    points = [(52.0, 4.0), (52.01, 4.0)]
    expected_live = haversine_nm(52.0, 4.0, 52.01, 4.0)
    assert total_distance_nm(points) == BASE_DISTANCE_NM + expected_live


def test_total_distance_with_single_point_is_just_base():
    assert total_distance_nm([(52.0, 4.0)]) == BASE_DISTANCE_NM


def test_build_status_uses_latest_rows():
    scraper_positions = [(52.0, 4.0), (52.1, 4.1)]
    latest_scraper_row = {
        "Lat": "52.1",
        "Lon": "4.1",
        "Time": "2026-08-25T14:07:46+00:00",
        "speed": "5.2",
        "course": "270",
    }
    latest_event_row = {"Event": "STOP Moving", "Port": "DEN HELDER", "Country": "Netherlands"}

    status = build_status(scraper_positions, latest_scraper_row, latest_event_row)

    assert status["lat"] == 52.1
    assert status["lon"] == 4.1
    assert status["event_summary"] == "STOP Moving - DEN HELDER - Netherlands"
    assert status["speed"] == "5.2"


def test_build_status_handles_missing_event():
    latest_scraper_row = {"Lat": "52.0", "Lon": "4.0", "Time": "t", "speed": "", "course": ""}
    status = build_status([(52.0, 4.0)], latest_scraper_row, None)
    assert status["event_summary"] == "unknown"


def test_render_svg_contains_key_values():
    status = {
        "ship_name": "Sanuk",
        "ship_type": "Sailing yacht",
        "ship_flag": "Estonia",
        "ship_call_sign": "ES4371",
        "lat": 52.1,
        "lon": 4.1,
        "position_time": "2026-08-25T14:07:46+00:00",
        "speed": "5.2",
        "course": "270",
        "distance_nm": 988.7,
        "event_summary": "STOP Moving - DEN HELDER - Netherlands",
    }
    svg = render_svg(status)

    assert "Sanuk" in svg
    assert "ES4371" in svg
    assert "988.7 nm" in svg
    assert "STOP Moving - DEN HELDER - Netherlands" in svg
    assert svg.strip().startswith("<svg")
    assert svg.strip().endswith("</svg>")
