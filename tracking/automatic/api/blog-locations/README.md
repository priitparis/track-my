# Blog location extractor

Extracts the locations mentioned in the trip's own blog posts — using an
LLM (Gemini) to turn free-text trip narrative into structured waypoints —
on a schedule, no manual action required.

Unlike every other tracking method, this one doesn't track the ship's
live position. It reads the crew's own trip blog and asks an LLM to
extract the chronological locations actually visited (ports, stops,
landmarks reached by e.g. a shore excursion) — not merely mentioned in
passing — with a short description of what happened there. This mirrors
a manual
workflow the user already had — pasting a blog post into an LLM chat with
a location-extraction prompt, then copying the CSV result into a map by
hand — automated and running on a free LLM tier.

## Architecture

- **Data source**: the blog's RSS feed (set via `BLOG_FEED_URL`, e.g. a
  Substack feed at `https://yourblog.substack.com/feed`), which includes
  each post's full HTML content (`content:encoded`) — no scraping of the
  blog's web pages needed.
- **Extraction**: [Gemini API](https://ai.google.dev/) (free tier), using
  structured JSON output (`response_schema`) so the response is already
  a typed list of locations, not free text to parse.
- **Trigger**: GitHub Actions, scheduled (cron, daily) and manual
  (`workflow_dispatch`).
- **Runtime**: [fetch_locations.py](fetch_locations.py), a short-lived
  Python script, run fresh on every scheduled tick. Each run re-reads
  the whole feed, skips posts already processed, and only calls Gemini
  for genuinely new posts.
- **Database**: the same spreadsheet as every other tracking method, in
  its own **separate tab** (`Blog`) — see "Sheet columns" below.

## Files

- [fetch_locations.py](fetch_locations.py) — fetches the RSS feed, skips
  posts whose URL is already recorded in the `Blog` sheet tab, sends
  each new post's cleaned text to Gemini, and appends the extracted
  locations as rows.
- [requirements.txt](requirements.txt) — Python dependencies
  (`requests`, `gspread`, `google-auth`, `google-genai`, `pydantic`,
  `python-dotenv`).
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/blog-locations-tracker.yml](../../../../.github/workflows/blog-locations-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Sheet columns

```
Lat | Lon | Time | name | description | post_title | post_date | post_url | group_id
```

- `Lat` / `Lon` / `Time` follow the same convention as every other
  tracking method's sheet, but `Time` here is this script's own
  processing time, not a timestamp from the blog post itself (blog posts
  don't have precise per-location timestamps).
- `name` / `description` — the extracted location's name and summary, as
  returned by Gemini.
- `post_title` / `post_date` / `post_url` — which blog post this location
  came from; `post_url` is also the field used to detect already-
  processed posts (see "Known limitations").
- `group_id` — a manually-set value (via the `GROUP_ID` environment
  variable, default `0`) tagging every row with which trip/voyage it
  belongs to, since one blog can cover more than one trip over time. The
  [shared GeoJSON endpoint](../../../google-apps-script/) recognizes a
  `group_id` column on any sheet and can filter to just one group via
  `?group=` — e.g. `?sheet=Blog&group=2` returns only rows written while
  `GROUP_ID=2` was set. Change `GROUP_ID` in `.env` (or the GitHub
  Actions workflow) when starting a new trip.

If a post has no identifiable locations, one row is still written for it
with `Lat`/`Lon`/`name`/`description` left blank — this records the post
as processed (so it isn't re-sent to Gemini every run) without adding a
map point. The [shared GeoJSON endpoint](../../../google-apps-script/)
already skips any row where Lat/Lon don't parse as numbers, so these
rows are automatically excluded from the map without needing a separate
"has location" flag column.

## Setup

1. Get a free Gemini API key at
   [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no
   credit card required.
2. Reuse the same Google Cloud service account as the other automatic
   methods (or create a new one the same way), and make sure it has
   Editor access to the shared spreadsheet.
3. Add a `Blog` tab to that spreadsheet, with a header row
   `Lat | Lon | Time | name | description | post_title | post_date | post_url | group_id`.
4. In the GitHub repo, add these secrets under Settings → Secrets and
   variables → Actions: `BLOG_FEED_URL` (your blog's RSS feed URL),
   `GEMINI_API_KEY`, plus the ones shared with other methods if not
   already present (`GCP_SA_KEY`, `GOOGLE_SHEET_ID`).
5. Trigger the workflow manually once via the Actions tab
   (`workflow_dispatch`) to confirm rows appear in `Blog` before relying
   on the cron schedule — this will process every post currently in the
   feed on its first run, since none are recorded yet.
6. (Optional, for map display) Point a uMap layer at the
   [shared GeoJSON endpoint](../../../google-apps-script/)'s Web App URL
   with `?sheet=Blog`.

### Local testing (optional)

Use a Python virtual environment so dependencies stay isolated from the
system Python:

```bash
cd tracking/automatic/api/blog-locations
python3 -m venv blog-venv
source blog-venv/bin/activate     # Windows: blog-venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # fill in the real values; .env is git-ignored
# copy your downloaded service account key to gcp-service-account.json
# (same directory; also git-ignored) — GCP_SA_KEY_PATH in .env already
# points at it by default

python fetch_locations.py     # loads .env automatically (run from this directory)
```

## Known limitations

- If the RSS feed is fetched successfully but zero posts can be parsed
  out of it, the script exits with a nonzero code instead of skipping
  silently — GitHub Actions marks that run failed and emails a
  notification, since this almost always means the feed's XML structure
  changed (e.g. `content:encoded` renamed or dropped) rather than the
  blog genuinely having no posts. A backlog of "every post already
  processed" (the normal steady-state case once history is caught up)
  does not trigger this — only literally failing to parse any post at
  all does.
- Duplicate detection reads every existing row's `post_url` column
  (column 8) on every run, which is fine at this data volume but would
  need revisiting if the sheet grows very large.
- The Gemini free tier's rate limits and even model *names* have changed
  abruptly before (Google cut free-tier quotas significantly in December
  2025 without much notice, and has deprecated model names for new users
  with little warning — `GEMINI_MODEL`'s default has already had to
  change once during this project). A 404 "model no longer available"
  error means the default in `.env.example` is stale; check
  [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
  for the current name and set `GEMINI_MODEL` explicitly. Any such
  failure — model 404, quota error — currently just fails that post's
  extraction; the script logs it and continues with any other new posts
  rather than aborting the whole run.
- Coordinates are only as accurate as the LLM's geocoding of place names
  mentioned in the text — there's no independent verification against a
  real geocoding service. Spot-check new entries before trusting them
  for navigation purposes.
- The prompt asks the model to only extract locations actually visited
  (e.g. a port the ship stopped at, or a place reached via a bus/walk
  described in the text) and to skip places merely mentioned in passing
  (background references, previews of an upcoming stop, etc.). This
  relies on the LLM correctly reading intent from the narrative — it can
  still misjudge an ambiguous mention either way. Spot-check new entries.
- `Time` is when the script processed the post, not when the location
  was actually visited — the blog text itself may mention approximate
  dates/times in its narrative (captured in `description` if the model
  includes them), but this isn't parsed into a structured field.
- GitHub Actions cron schedules are not exact — runs can be delayed
  under load.
