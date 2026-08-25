"""
Fetches new posts from the trip's blog RSS feed (BLOG_FEED_URL), sends
each post's text to the Gemini API to extract the chronological
locations mentioned (ports, stops, landmarks) as structured data, and
appends any posts not already processed to the "Blog" Google Sheet tab.
Intended to run as a short-lived GitHub Actions job on a cron schedule.

Unlike the other tracking methods, this one doesn't track the ship's
live position — it turns the trip's own blog narrative into a rough,
human-curated set of waypoints with descriptions, extracted once per
post rather than continuously.
"""

import html
import os
import re
import sys
from datetime import datetime, timezone

import requests
import gspread
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from pydantic import BaseModel

load_dotenv()

REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

ITEM_PATTERN = re.compile(r"<item>(.*?)</item>", re.DOTALL)
TITLE_PATTERN = re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>")
LINK_PATTERN = re.compile(r"<link>(.*?)</link>")
PUBDATE_PATTERN = re.compile(r"<pubDate>(.*?)</pubDate>")
CONTENT_PATTERN = re.compile(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", re.DOTALL)
TAG_STRIP_PATTERN = re.compile(r"<[^>]+>")

EXTRACTION_PROMPT = """\
Analyze the following travel/blog post (written in Estonian) and extract \
every location visited (ports, stops, landmarks, etc.) in chronological \
order.

For each location, provide:
- latitude and longitude: precise WGS84 coordinates (decimal degrees)
- name: the location's name with a sequence number (e.g. "1. Ruhnu sadam")
- description: a short 1-2 sentence summary of what happened there, in \
Estonian (matching the source text's language)

If the text contains no identifiable locations, return an empty list.

Text:
{text}
"""


class Location(BaseModel):
    latitude: float
    longitude: float
    name: str
    description: str


def load_config():
    required = ["BLOG_FEED_URL", "GEMINI_API_KEY", "GCP_SA_KEY_PATH", "GOOGLE_SHEET_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing required environment variables: {missing}")
    return {
        "feed_url": os.environ["BLOG_FEED_URL"],
        "gemini_api_key": os.environ["GEMINI_API_KEY"],
        "sa_key_path": os.environ["GCP_SA_KEY_PATH"],
        "sheet_id": os.environ["GOOGLE_SHEET_ID"],
        "tab": os.environ.get("GOOGLE_SHEET_TAB", "Blog"),
        "group_id": os.environ.get("GROUP_ID", "0"),
    }


def clean_html(raw_html):
    text = html.unescape(raw_html)
    text = TAG_STRIP_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed_posts(feed_url):
    """Fetch the RSS feed and return a list of posts, each with title,
    url, published date, and plain-text content."""
    response = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    xml = response.text

    posts = []
    for item in ITEM_PATTERN.findall(xml):
        title_match = TITLE_PATTERN.search(item)
        link_match = LINK_PATTERN.search(item)
        pubdate_match = PUBDATE_PATTERN.search(item)
        content_match = CONTENT_PATTERN.search(item)
        if not (link_match and content_match):
            continue

        posts.append({
            "title": title_match.group(1).strip() if title_match else "",
            "url": link_match.group(1).strip(),
            "pub_date": pubdate_match.group(1).strip() if pubdate_match else "",
            "text": clean_html(content_match.group(1)),
        })
    return posts


def extract_locations(client, post_text):
    """Send the post text to Gemini and return a list of Location, or an
    empty list if the model finds nothing (or the call fails)."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=EXTRACTION_PROMPT.format(text=post_text),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[Location],
        ),
    )
    return response.parsed or []


def already_processed_urls(sheet):
    """Read the post_url column from every existing row, to skip
    re-processing posts already extracted — including posts that had no
    locations, which are still recorded (with blank Lat/Lon) so they
    aren't re-sent to Gemini on every run."""
    rows = sheet.get_all_values()[1:]  # skip header
    return {row[7] for row in rows if len(row) > 7 and row[7]}


def append_locations(sheet, post, locations, group_id):
    """Append one row per extracted location. If none were found, still
    append a single row (with blank Lat/Lon) so this post is recorded as
    processed and skipped next run. Lat/Lon are left blank rather than
    0,0 so the shared GeoJSON endpoint (which filters on
    parseFloat(lat)/parseFloat(lon) being valid numbers) naturally
    excludes it as a map point — no separate "has location" column
    needed.

    group_id tags every row with which trip/voyage it belongs to (a
    manual setting via GROUP_ID, since a blog can cover more than one
    trip over time) — the shared GeoJSON endpoint can then be asked for
    just one group's locations via ?group=."""
    time_iso = datetime.now(timezone.utc).isoformat()

    if locations:
        rows = [
            [loc.latitude, loc.longitude, time_iso, loc.name, loc.description,
             post["title"], post["pub_date"], post["url"], group_id]
            for loc in locations
        ]
    else:
        rows = [
            ["", "", time_iso, "", "", post["title"], post["pub_date"], post["url"], group_id]
        ]

    sheet.append_rows(rows)
    return len(locations)


def main():
    cfg = load_config()

    try:
        posts = fetch_feed_posts(cfg["feed_url"])
    except requests.RequestException as e:
        print(f"Failed to fetch blog feed: {e}")
        sys.exit(0)

    if not posts:
        # A feed with literally zero parseable posts almost certainly
        # means the RSS XML structure changed (e.g. content:encoded
        # renamed or dropped) rather than the blog genuinely having no
        # posts ever. Fail loudly so GitHub Actions marks the run failed
        # and emails a notification — a post backlog of "all already
        # processed" (handled below) is the normal, non-failing case.
        sys.exit("No posts found in the feed; the feed's structure may have changed.")

    creds = Credentials.from_service_account_file(
        cfg["sa_key_path"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(cfg["sheet_id"]).worksheet(cfg["tab"])

    seen = already_processed_urls(sheet)
    new_posts = [p for p in posts if p["url"] not in seen]

    if not new_posts:
        print(f"No new posts to process ({len(posts)} in feed, all already recorded).")
        sys.exit(0)

    client = genai.Client(api_key=cfg["gemini_api_key"])

    total_added = 0
    for post in new_posts:
        try:
            locations = extract_locations(client, post["text"])
        except Exception as e:
            print(f"Failed to extract locations for '{post['title']}': {e}")
            continue

        added = append_locations(sheet, post, locations, cfg["group_id"])
        total_added += added
        print(f"'{post['title']}': extracted {len(locations)} location(s), added {added} row(s).")

    print(f"Processed {len(new_posts)} new post(s), added {total_added} row(s) total to '{cfg['tab']}'.")


if __name__ == "__main__":
    main()
