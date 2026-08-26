"""
Unit tests for generate_status_svg.py. Run with:
    pytest test_generate_status_svg.py
(requires pytest, not listed in requirements.txt since it's dev-only —
install separately: pip install pytest)
"""

from generate_status_svg import (
    THEMES,
    VARIANTS,
    WIDTHS,
    _wrap_text,
    build_status,
    output_filename,
    render_svg,
)


def test_build_status_uses_latest_rows():
    latest_scraper_row = {
        "Lat": "52.1",
        "Lon": "4.1",
        "Time": "2026-08-25T14:07:46+00:00",
        "speed": "5.2",
        "course": "270",
        "full_distance": "988.7",
    }
    latest_event_row = {"Event": "STOP Moving", "Port": "DEN HELDER", "Country": "Netherlands"}

    status = build_status(latest_scraper_row, latest_event_row)

    assert status["lat"] == 52.1
    assert status["lon"] == 4.1
    assert status["distance_nm"] == 988.7
    assert status["event_summary"] == "STOP Moving - DEN HELDER - Netherlands"
    assert status["speed"] == "5.2"


def test_build_status_handles_missing_event():
    latest_scraper_row = {
        "Lat": "52.0", "Lon": "4.0", "Time": "t",
        "speed": "", "course": "", "full_distance": "900.0",
    }
    status = build_status(latest_scraper_row, None)
    assert status["event_summary"] == "unknown"


SAMPLE_STATUS = {
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


def test_render_svg_contains_key_values():
    svg = render_svg(SAMPLE_STATUS, "normal", "dark")

    assert "Sanuk" in svg
    assert "ES4371" in svg
    assert "988.7 nm" in svg
    assert "STOP Moving - DEN HELDER - Netherlands" in svg
    assert svg.strip().startswith("<svg")
    assert svg.strip().endswith("</svg>")


def test_render_svg_all_variants_are_well_formed():
    for width_key, theme_key in VARIANTS:
        svg = render_svg(SAMPLE_STATUS, width_key, theme_key)
        assert svg.strip().startswith("<svg")
        assert svg.strip().endswith("</svg>")
        assert f'width="{WIDTHS[width_key]["width"]}"' in svg


def test_render_svg_transparent_theme_has_no_background_rect():
    svg = render_svg(SAMPLE_STATUS, "normal", "transparent")
    assert "<rect" not in svg


def test_render_svg_dark_and_light_themes_have_background_rect():
    for theme_key in ("dark", "light"):
        svg = render_svg(SAMPLE_STATUS, "normal", theme_key)
        assert f'fill="{THEMES[theme_key]["bg"]}"' in svg


def test_render_svg_compact_is_narrower_than_normal():
    normal_svg = render_svg(SAMPLE_STATUS, "normal", "dark")
    compact_svg = render_svg(SAMPLE_STATUS, "compact", "dark")
    assert 'width="600"' in normal_svg
    assert 'width="400"' in compact_svg


def test_render_svg_height_grows_with_wrapped_text():
    short_status = dict(SAMPLE_STATUS, event_summary="Short")
    long_status = dict(
        SAMPLE_STATUS,
        event_summary="A very long event description that should not fit on a single line "
        "at the compact width and therefore needs to wrap onto more lines",
    )
    short_svg = render_svg(short_status, "compact", "dark")
    long_svg = render_svg(long_status, "compact", "dark")

    def _height(svg):
        return int(svg.split('height="')[1].split('"')[0])

    assert _height(long_svg) > _height(short_svg)


def test_wrap_text_fits_within_width():
    text = "This is a fairly long line of text that should wrap across lines"
    lines = _wrap_text(text, font_size=14, max_width=150)
    assert len(lines) > 1
    assert " ".join(lines) == text


def test_wrap_text_short_text_stays_one_line():
    assert _wrap_text("Short", font_size=14, max_width=300) == ["Short"]


def test_output_filename_is_unique_per_variant():
    names = {output_filename(w, t) for w, t in VARIANTS}
    assert len(names) == len(VARIANTS) == 6


def test_output_filename_supports_svg_and_png_extensions():
    assert output_filename("normal", "dark", "svg") == "status-normal-dark.svg"
    assert output_filename("normal", "dark", "png") == "status-normal-dark.png"
