"""
Generates a status SVG summarizing the ship's current position, last
event, and total distance traveled, reading from the "Scraper" and
"Events" Google Sheet tabs. Intended to run as a short-lived GitHub
Actions job on a cron schedule; the workflow uploads the generated SVGs
to a fixed GitHub release ("latest-status") so they can be embedded
elsewhere (e.g. Substack) via a stable download URL.

The total distance traveled is read directly from the Scraper tab's own
"full_distance" column (computed and written by
../scraper/myshiptracking/fetch_position.py on each of its runs) rather
than recomputed here.

Renders every combination of width (normal/compact) and background
(dark/light/transparent) — six SVG files per run, listed in VARIANTS —
plus a rasterized PNG counterpart of each (via cairosvg), for embedding
contexts that don't support SVG.
"""

import os
import sys

import cairosvg
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

# --- Ship identity (hardcoded; not stored in any sheet) ---------------
SHIP_NAME = "Sanuk"
SHIP_TYPE = "Sailing yacht"
SHIP_FLAG = "Estonia"
SHIP_CALL_SIGN = "ES4371"

# Used only to display the distance in km alongside its source nm value
# (Scraper's own full_distance column stays nm-only).
KM_PER_NM = 1.852


def load_config():
    required = ["GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "scraper_tab": os.environ.get("GOOGLE_SHEET_SCRAPER_TAB", "Scraper"),
        "events_tab": os.environ.get("GOOGLE_SHEET_EVENTS_TAB", "Events"),
        "output_dir": os.environ.get("OUTPUT_SVG_DIR", "status"),
    }


# --- Sheet reading -----------------------------------------------------------

def open_sheet(sa_key_path, sheet_id, tab):
    creds = Credentials.from_service_account_file(
        sa_key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(sheet_id).worksheet(tab)


def read_latest_scraper_row(sheet):
    records = sheet.get_all_records()
    return records[-1] if records else None


def read_latest_event(sheet):
    records = sheet.get_all_records()
    return records[-1] if records else None


# --- SVG rendering -----------------------------------------------------------

# Two widths (px) — "normal" fits the original layout comfortably,
# "compact" is a narrower variant for tighter spots (e.g. a Substack
# sidebar), using smaller fonts and tighter line spacing rather than
# dropping any field.
WIDTHS = {
    "normal": {"width": 600, "padding": 24, "label_size": 13, "value_size": 18, "title_size": 22, "line_gap": 4},
    "compact": {"width": 400, "padding": 16, "label_size": 11, "value_size": 14, "title_size": 17, "line_gap": 3},
}

# Three backgrounds. "transparent" omits the background <rect> entirely
# (no fill attribute at all) so the SVG composites onto whatever page
# background it's embedded in.
THEMES = {
    "dark": {"bg": "#0b1f33", "label_fill": "#9fb8cc", "value_fill": "#ffffff"},
    "light": {"bg": "#ffffff", "label_fill": "#5b6b78", "value_fill": "#0b1f33"},
    "transparent": {"bg": None, "label_fill": "#9fb8cc", "value_fill": "#0b1f33"},
}

# Every (width, theme) combination rendered on each run, e.g. "normal-dark".
VARIANTS = [(w, t) for w in WIDTHS for t in THEMES]

# Rough average character width as a fraction of font-size, used to
# estimate rendered text width for word-wrapping without needing an
# actual font-metrics library — good enough to decide when a line of
# this sans-serif font needs to wrap, not pixel-exact.
AVG_CHAR_WIDTH_RATIO = 0.55


def _estimate_text_width(text, font_size):
    return len(text) * font_size * AVG_CHAR_WIDTH_RATIO


def _wrap_text(text, font_size, max_width):
    """Greedily wraps `text` into lines that fit `max_width` at
    `font_size`, using the character-count width estimate above."""
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _estimate_text_width(candidate, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_svg(status, width_key="normal", theme_key="dark"):
    """Renders one SVG variant for the given width/theme keys (see
    WIDTHS/THEMES). Height is computed from the actual number of lines
    each field needs once long values (e.g. a long event description)
    are word-wrapped to fit the chosen width."""
    dims = WIDTHS[width_key]
    theme = THEMES[theme_key]
    width = dims["width"]
    padding = dims["padding"]
    label_size = dims["label_size"]
    value_size = dims["value_size"]
    title_size = dims["title_size"]
    line_gap = dims["line_gap"]
    text_max_width = width - 2 * padding

    fields = [
        ("title", f"{status['ship_name']} ({status['ship_type']})", title_size, True),
        ("label", f"Flag: {status['ship_flag']}  Call sign: {status['ship_call_sign']}", label_size, False),
        ("label", f"Last position ({status['position_time']})", label_size, False),
        ("value", f"{status['lat']:.4f}, {status['lon']:.4f}", value_size, False),
        ("label", "Speed / Course", label_size, False),
        ("value", f"{status['speed']} kn / {status['course']}°", value_size, False),
        ("label", "Total distance traveled", label_size, False),
        ("value", f"{status['distance_nm']:.1f} nm ({status['distance_nm'] * KM_PER_NM:.1f} km)", value_size, False),
        ("label", "Last event", label_size, False),
        ("value", status["event_summary"], value_size, False),
    ]

    elements = []
    y = padding + title_size
    for kind, text, font_size, bold in fields:
        fill = theme["value_fill"] if kind in ("title", "value") else theme["label_fill"]
        weight = ' font-weight="bold"' if bold else ""
        for line in _wrap_text(text, font_size, text_max_width):
            elements.append(
                f'  <text x="{padding}" y="{y}" fill="{fill}" font-size="{font_size}"{weight}>'
                f"{_escape(line)}</text>"
            )
            y += font_size + line_gap
        y += font_size * 0.6  # extra gap between fields

    height = round(y - font_size * 0.6 + padding - line_gap)

    background = ""
    if theme["bg"] is not None:
        background = f'\n  <rect width="{width}" height="{height}" fill="{theme["bg"]}"/>'

    body = "\n".join(elements)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">'
        f"{background}\n{body}\n</svg>\n"
    )


def build_status(latest_scraper_row, latest_event_row):
    distance_nm = float(latest_scraper_row["full_distance"])
    event_summary = "unknown"
    if latest_event_row:
        parts = [
            latest_event_row.get("Event", ""),
            latest_event_row.get("Port", ""),
            latest_event_row.get("Country", ""),
        ]
        event_summary = " - ".join(p for p in parts if p)
    return {
        "ship_name": SHIP_NAME,
        "ship_type": SHIP_TYPE,
        "ship_flag": SHIP_FLAG,
        "ship_call_sign": SHIP_CALL_SIGN,
        "lat": float(latest_scraper_row["Lat"]),
        "lon": float(latest_scraper_row["Lon"]),
        "position_time": latest_scraper_row["Time"],
        "speed": latest_scraper_row.get("speed") or "?",
        "course": latest_scraper_row.get("course") or "?",
        "distance_nm": distance_nm,
        "event_summary": event_summary,
    }


def output_filename(width_key, theme_key, extension="svg"):
    return f"status-{width_key}-{theme_key}.{extension}"


def main():
    cfg = load_config()

    scraper_sheet = open_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["scraper_tab"])
    latest_scraper_row = read_latest_scraper_row(scraper_sheet)
    if latest_scraper_row is None:
        sys.exit("Scraper tab has no data rows; nothing to render.")

    events_sheet = open_sheet(cfg["sa_key_path"], cfg["sheet_id"], cfg["events_tab"])
    latest_event_row = read_latest_event(events_sheet)

    status = build_status(latest_scraper_row, latest_event_row)

    os.makedirs(cfg["output_dir"], exist_ok=True)
    for width_key, theme_key in VARIANTS:
        svg = render_svg(status, width_key, theme_key)

        svg_path = os.path.join(cfg["output_dir"], output_filename(width_key, theme_key, "svg"))
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"Wrote {svg_path}")

        png_path = os.path.join(cfg["output_dir"], output_filename(width_key, theme_key, "png"))
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=png_path)
        print(f"Wrote {png_path}")

    print(
        f"Done: {status['distance_nm']:.1f} nm, last event: {status['event_summary']}"
    )


if __name__ == "__main__":
    main()
