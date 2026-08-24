# MyShipTracking scraper

Automatic ship tracking by scraping the ship's public
[MyShipTracking.com](https://www.myshiptracking.com/) vessel page for its
current position, on a schedule, no manual action required.

This is the **primary** automatic method (fastest updates, most reliable
coverage found so far). See [../../api/aisstream/](../../api/aisstream/) for the AIS
WebSocket-based method, which runs as a secondary/backup source at a
lower frequency.

## Architecture

- **Data source**: the ship's public vessel page at
  `myshiptracking.com/vessels/mmsi-<MMSI>` — no API key or account
  needed. The page embeds precise coordinates directly in its raw HTML
  (inside a `<script>` block's AJAX URL string), so a plain HTTP request
  is enough; no JavaScript rendering or headless browser required.
- **Trigger**: GitHub Actions, scheduled (cron, hourly) and manual
  (`workflow_dispatch`).
- **Runtime**: [fetch_position.py](fetch_position.py), a short-lived
  Python script (a single HTTP request, waits up to
  `REQUEST_TIMEOUT_SECONDS`, 30s by default), run fresh on every
  scheduled tick — no persistent process.
- **Database**: the same spreadsheet as the
  [manual method](../../../manual/google-apps-script/) and
  [aisstream method](../../api/aisstream/), but its own **separate tab**
  (`Scraper`) with the same `Lat` / `Lon` / `Time` column convention.
- **Map feed**: the [shared GeoJSON endpoint](../../../google-apps-script/)
  serves the `Scraper` tab as GeoJSON for a uMap layer (via
  `?sheet=Scraper`) — one Apps Script project shared by every tracking
  method's read side.

## Files

- [fetch_position.py](fetch_position.py) — fetches the vessel page,
  extracts `(lat, lon)` with a regex match on the embedded AJAX URL
  string, and appends it to the `Scraper` sheet tab.
- [requirements.txt](requirements.txt) — Python dependencies
  (`requests`, `gspread`, `google-auth`, `python-dotenv`).
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/scraper-tracker.yml](../../../../.github/workflows/scraper-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Setup

1. Find the target ship's MMSI (e.g. via MyShipTracking, MarineTraffic,
   or VesselFinder) and confirm it has a page at
   `myshiptracking.com/vessels/mmsi-<MMSI>`.
2. Reuse the same Google Cloud service account as the
   [aisstream method](../../api/aisstream/) (or create a new one the same way),
   and make sure it has Editor access to the shared spreadsheet.
3. Add a `Scraper` tab to that spreadsheet, with a header row
   `Lat | Lon | Time` matching the other tabs.
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

- This regex-scrapes an internal AJAX URL string embedded in the page's
  HTML, not a documented public API — MyShipTracking could change its
  page structure at any time without notice, silently breaking
  extraction. `fetch_position()` returns `None` if the pattern isn't
  found, so the script skips the run cleanly rather than writing bad
  data, but there's no automatic alert if this happens — check the
  Actions log occasionally.
- A missing User-Agent header gets a 403 from this site; the script
  always sends a standard browser User-Agent string.
- If the ship hasn't reported a new AIS position recently, the page may
  show a stale position rather than an error — there's no built-in
  staleness check here (unlike the "Position Received" timestamp
  visible on the page itself, which this script doesn't currently
  parse).
- GitHub Actions cron schedules are not exact — runs can be delayed
  under load, so the hourly interval is approximate.
