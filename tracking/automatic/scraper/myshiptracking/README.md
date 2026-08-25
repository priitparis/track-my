# MyShipTracking scraper

Automatic ship tracking by scraping the ship's public
[MyShipTracking.com](https://www.myshiptracking.com/) vessel page for its
current position, status, trip, and weather details, on a schedule, no
manual action required.

This is the **primary** automatic method (fastest updates, most reliable
coverage found so far). See [../../api/aisstream/](../../api/aisstream/) for the AIS
WebSocket-based method, which runs as a secondary/backup source at a
lower frequency.

## Architecture

- **Data source**: the ship's public vessel page at
  `myshiptracking.com/vessels/mmsi-<MMSI>` — no API key or account
  needed. The page embeds precise coordinates directly in its raw HTML
  (inside a `<script>` block's AJAX URL string), and the rest of the
  page's clearly-sectioned tables (`ft-info`, `ft-trip`, `ft-position`,
  `ft-weather`) expose vessel, trip, and weather details, so a plain
  HTTP request is enough; no JavaScript rendering or headless browser
  required.
- **Trigger**: GitHub Actions, scheduled (cron, hourly) and manual
  (`workflow_dispatch`).
- **Runtime**: [fetch_position.py](fetch_position.py), a short-lived
  Python script (a single HTTP request, waits up to
  `REQUEST_TIMEOUT_SECONDS`, 30s by default), run fresh on every
  scheduled tick — no persistent process.
- **Database**: the same spreadsheet as the
  [manual method](../../../manual/google-apps-script/) and
  [aisstream method](../../api/aisstream/), but its own **separate tab**
  (`Scraper`) — see "Sheet columns" below for its (much wider) layout.
- **Map feed**: the [shared GeoJSON endpoint](../../../google-apps-script/)
  serves the `Scraper` tab as GeoJSON for a uMap layer (via
  `?sheet=Scraper`) — one Apps Script project shared by every tracking
  method's read side.

## Files

- [fetch_position.py](fetch_position.py) — fetches the vessel page,
  extracts `(lat, lon)` with a regex match on the embedded AJAX URL
  string, plus every other field listed under "Sheet columns" below
  from the page's other tables, and appends a row to the `Scraper`
  sheet tab.
- [requirements.txt](requirements.txt) — Python dependencies
  (`requests`, `gspread`, `google-auth`, `python-dotenv`).
- [test_fetch_position.py](test_fetch_position.py) — unit tests for the
  duplicate-position guard (`pytest test_fetch_position.py`; requires
  `pytest`, dev-only, not in requirements.txt).
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/scraper-tracker.yml](../../../../.github/workflows/scraper-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Sheet columns

```
Lat | Lon | Time | speed | course | area | status | draught |
imo | flag | call_sign | size | gt | dwt | build |
distance_travelled | remaining_distance | avg_speed | max_speed | time_travelled |
temperature | wind_speed | wind_direction | pressure | humidity | cloud_coverage
```

- `Lat` / `Lon` / `Time` follow the same convention as every other
  tracking method's sheet; `Time` is this script's own UTC capture time,
  same as before.
- `speed` / `course` / `area` / `status` / `draught` — the page's
  "Current Position" table.
- `imo` / `flag` / `call_sign` / `size` / `gt` / `dwt` / `build` — the
  page's static vessel-info table. These rarely or never change between
  runs and are simply repeated on every row rather than stored once
  separately, for simplicity.
- `distance_travelled` / `remaining_distance` / `avg_speed` /
  `max_speed` / `time_travelled` — the "Current Trip" table.
- `temperature` / `wind_speed` / `wind_direction` / `pressure` /
  `humidity` / `cloud_coverage` — the "Weather" table, for the ship's
  current position.

Any field the page shows as `---` (not available) is written as a blank
cell, not the literal string `---`.

Before appending, the script compares the new `(lat, lon)` against the
sheet's last row; if both are within ~10m (0.0001°) of each other, the
row is skipped rather than written — this avoids piling up duplicate
rows while the ship is stationary (in port, at anchor) and the page
keeps returning the same last-known AIS fix on every hourly run.

# Data
**Time**: {time}
**Latitude**: {lat}
**Longitude**: {lon}
**Speed**: {speed}
**Course**: {course}
**Area**: {area}
**Status**: {status}
**Draught**: {draught}
**IMO**: {imo}
**Flag**: {flag}
**Call sign**: {call_sign}
**Size**: {size}
**GT**: {gt}
**DWT**: {dwt}
**Build**: {build}
**Distance travelled**: {distance_travelled}
**Remaining distance**: {remaining_distance}
**Average speed**: {avg_speed}
**Max speed**: {max_speed}
**Time travelled**: {time_travelled}
**Temperature**: {temperature}
**Wind speed**: {wind_speed}
**Wind direction**: {wind_direction}
**Pressure**: {pressure}
**Humidity**: {humidity}
**Cloud coverage**: {cloud_coverage}

## Setup

1. Find the target ship's MMSI (e.g. via MyShipTracking, MarineTraffic,
   or VesselFinder) and confirm it has a page at
   `myshiptracking.com/vessels/mmsi-<MMSI>`.
2. Reuse the same Google Cloud service account as the
   [aisstream method](../../api/aisstream/) (or create a new one the same way),
   and make sure it has Editor access to the shared spreadsheet.
3. Add a `Scraper` tab to that spreadsheet, with a header row matching
   the column list above exactly (the shared GeoJSON endpoint reads
   header names to build each point's properties, so header text must
   match).
4. In the GitHub repo, add these secrets under Settings → Secrets and
   variables → Actions (skip any that already exist from setting up the
   aisstream method, since `SHIP_MMSI`, `GCP_SA_KEY`, and
   `GOOGLE_SHEET_ID` are shared across methods): `SHIP_MMSI`,
   `GCP_SA_KEY` (the full service account JSON key content),
   `GOOGLE_SHEET_ID`.
5. Trigger the workflow manually once via the Actions tab
   (`workflow_dispatch`) to confirm a row appears in `Scraper` before
   relying on the cron schedule.
6. (Optional, for map display) Set up the
   [shared GeoJSON endpoint](../../../google-apps-script/) once (it
   serves every tracking method) and point a uMap layer at its Web App
   URL with `?sheet=Scraper` — see that project's README for deployment
   steps.

### Local testing (optional)

Use a Python virtual environment so dependencies stay isolated from the
system Python:

```bash
cd tracking/automatic/scraper/myshiptracking
python3 -m venv scraper-venv
source scraper-venv/bin/activate     # Windows: scraper-venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # fill in the real values; .env is git-ignored
# copy your downloaded service account key to gcp-service-account.json
# (same directory; also git-ignored) — GCP_SA_KEY_PATH in .env already
# points at it by default

python fetch_position.py      # loads .env automatically (run from this directory)
```

## Actions minutes budget

This method shares the same private-repo free tier (2,000 Actions
minutes/month) as [aisstream](../../api/aisstream/), since both workflows run
in the same repo. With the current defaults — scraper hourly (30s
timeout) and aisstream every 3 hours (120s timeout) — the combined
worst case (every run timing out) is about 1,240 minutes/month, leaving
good headroom. If you change either schedule or timeout, recompute both
together, not just the one you're editing.

## Known limitations

- This regex-scrapes several tables embedded in the page's HTML, not a
  documented public API — MyShipTracking could change its page
  structure at any time without notice, silently breaking extraction of
  some or all fields. Only the core position pattern is required for
  `fetch_position()` to succeed; every other field (speed, trip, weather,
  static vessel info) is best-effort and left blank if its `<th>` label
  isn't found on the page, so a partial page change degrades gracefully
  rather than failing the whole run. If the core position pattern itself
  isn't found, though, the script exits with a nonzero code (rather than
  skipping silently) — GitHub Actions marks that run failed and emails a
  notification, since this almost always means the page's structure
  changed, not that the ship is simply out of coverage (a stale-but-
  present position would still match the pattern).
- Static vessel-info fields (`imo`, `flag`, `call_sign`, `size`, `gt`,
  `dwt`, `build`) rarely change and are repeated on every row — this
  keeps the sheet's shape simple at the cost of redundant storage, which
  is a non-issue at this data volume.
- A missing User-Agent header gets a 403 from this site; the script
  always sends a standard browser User-Agent string.
- If the ship hasn't reported a new AIS position recently, the page may
  show a stale position rather than an error — there's no built-in
  staleness check here (unlike the "Position Received" timestamp
  visible on the page itself, which this script doesn't currently
  parse).
- GitHub Actions cron schedules are not exact — runs can be delayed
  under load, so the hourly interval is approximate.
