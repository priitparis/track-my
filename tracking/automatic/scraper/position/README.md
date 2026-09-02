# Position scraper

Automatic ship tracking by scraping several public vessel-tracking
sites for the ship's current position, on a schedule, no manual action
required. Every run queries all configured sources and records the one
reporting the **freshest AIS fix**, so a lag or outage at one site is
covered by the others.

This is the **primary** automatic method (fastest updates, most reliable
coverage found so far). See [../../api/aisstream/](../../api/aisstream/)
for the AIS WebSocket-based method, which runs as a secondary/backup
source at a lower frequency.

## Sources

Each source is a module under [sources/](sources/) exposing `SOURCE`
(the string written to the sheet's `source` column) and
`fetch(mmsi, timeout) -> dict | None`. [sources/__init__.py](sources/__init__.py)
lists them in `SOURCES`; adding a site is a new module plus one line
there.

| Module | Site | How the position is read |
|---|---|---|
| [sources/myshiptracking.py](sources/myshiptracking.py) | [myshiptracking.com](https://www.myshiptracking.com/) | `(lat, lon)` from a `<script>` block's AJAX URL string; speed/course/trip/weather/vessel-info from the page's clearly-sectioned tables (`ft-info`, `ft-trip`, `ft-position`, `ft-weather`); the AIS "reported on" time from the page's prose summary. |
| [sources/marineradar.py](sources/marineradar.py) | [marineradar.com](https://www.marineradar.com/) | The Next.js server-data payload embedded in the page (`self.__next_f.push([...])` chunks) carries a structured `ship` object: coordinates, `last_position` (AIS time), speed/course/heading/navigation-status, plus static details (call sign, IMO, AIS dimensions → size, tonnage, year built, draught) when present. Weather is a second request to MarineRadar's own `GET /api/weather?lat=&lon=` (an Open-Meteo passthrough): temperature, humidity, pressure, wind. |
| [sources/shipfinder.py](sources/shipfinder.py) | [shipfinder.com](https://www.shipfinder.com/) | The vessel detail page is fully server-rendered: current AIS fix and static vessel details sit in an `id="ais-…"` info grid, and the "reported at" time in the `ais-lastTime` cell. Coordinates are degrees + decimal-minutes with a hemisphere letter (`49-38.752 N`), converted to signed decimal degrees. Fills lat/lon, reported-at, speed, course, status, call sign, size, and flag (from the flag image's file name); no weather, tonnage or year-built on this page. |
| [sources/aisvesseltracker.py](sources/aisvesseltracker.py) | [aisvesseltracker.com](https://aisvesseltracker.com/) (Voyage Radar) | Next.js app; the page streams its server data as `self.__next_f.push([...])` chunks (same shape as MarineRadar). Brace-matching the embedded `"initialData": { … }` object yields one record with coordinates, `time_utc` (AIS time), speed/course/navigation-status, static details (call sign, IMO, flag, AIS dimensions → size, draught), current-trip avg/max speed and destination, and a nested `weather` object (temperature, pressure, wind). `0` is the site's "unknown" sentinel for imo/draught/dimensions and maps to blank. No humidity or cloud-cover figure. |

None of these sites needs an API key or account, and the data is served
over plain HTTP (in the page's HTML, or a public JSON endpoint) — no
JavaScript rendering or headless browser.

Sites investigated and **not** usable for precise position without a
paid API: **VesselFinder** (HTML rounds lat/lon to whole degrees),
**MarineTraffic** (Cloudflare-blocks plain requests), **ShipXplorer**
(position only in a token-gated XHR).

## Architecture

- **Trigger**: GitHub Actions, scheduled (cron, every 30 minutes) and
  manual (`workflow_dispatch`).
- **Runtime**: [fetch_position.py](fetch_position.py), a short-lived
  Python script run fresh on every scheduled tick — no persistent
  process. It queries all sources **concurrently** (a
  `ThreadPoolExecutor`), each waiting up to `REQUEST_TIMEOUT_SECONDS`
  (30s by default), so a run's wall time stays near one source's work,
  not the sum. (A source may itself make more than one request —
  MarineRadar fetches the page then the weather endpoint — but those are
  sequential within that source's slot.)
- **Selection**: of the sources that returned a position, the one with
  the newest `reported_at` (AIS observation time) wins; ties, or sources
  that expose no observation time, are broken by `SOURCES` order
  (MyShipTracking first). Exactly one row is appended per run.
- **Database**: the same spreadsheet as the
  [manual method](../../../manual/google-apps-script/) and
  [aisstream method](../../api/aisstream/), but its own **separate tab**
  (`Scraper`) — see "Sheet columns" below for its (much wider) layout.
- **Map feed**: the [shared GeoJSON endpoint](../../../google-apps-script/)
  serves the `Scraper` tab as GeoJSON for a uMap layer (via
  `?sheet=Scraper`) — one Apps Script project shared by every tracking
  method's read side.

## Files

- [fetch_position.py](fetch_position.py) — the orchestrator: queries
  every source in [sources/](sources/), picks the freshest fix, applies
  the duplicate-position guard, computes `full_distance`, and appends a
  row to the `Scraper` tab.
- [sources/](sources/) — one module per site (see "Sources" above), plus
  [sources/_common.py](sources/_common.py) (shared User-Agent, the
  common result-row shape, an HTML tag stripper).
- [requirements.txt](requirements.txt) — Python dependencies
  (`requests`, `gspread`, `google-auth`, `python-dotenv`).
- [test_fetch_position.py](test_fetch_position.py) — unit tests for the
  orchestrator (source collection, freshest-fix selection, the
  duplicate-position guard, distance tracking).
- [test_sources.py](test_sources.py) — unit tests for each source
  module's parsing, against small HTML fixtures.
  (`pytest`; dev-only, not in requirements.txt.)
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/position-tracker.yml](../../../../.github/workflows/position-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Sheet columns

```
Lat | Lon | Time | speed | course | area | status | draught |
imo | flag | call_sign | size | gt | dwt | build |
distance_travelled | remaining_distance | avg_speed | max_speed | time_travelled |
temperature | wind_speed | wind_direction | pressure | humidity | cloud_coverage |
full_distance | source
```

- `Lat` / `Lon` / `Time` follow the same convention as every other
  tracking method's sheet. `Time` is the winning source's AIS
  observation time as an ISO-8601 UTC string (MyShipTracking parses it
  from the page's "... as reported on `2026-08-27 09:18` by AIS ..."
  sentence, minute precision; MarineRadar takes it from the `ship`
  payload's `last_position`). If the winning source exposed no
  observation time, `Time` falls back to the script's own UTC run time.
- `speed` / `course` / `area` / `status` / `draught` — position/status
  fields. Every source fills what it has and leaves the rest blank
  (MarineRadar has speed/course/status and draught, but not `area`).
- `imo` / `flag` / `call_sign` / `size` / `gt` / `dwt` / `build` —
  static vessel-info fields. These rarely or never change between runs
  and are simply repeated on every row rather than stored once
  separately, for simplicity. Both sources populate these when the site
  has them (`size` is a `L x B m` string; MarineRadar derives it from
  the AIS reference-point dimensions).
- `distance_travelled` / `remaining_distance` / `avg_speed` /
  `max_speed` / `time_travelled` — current-trip fields (MyShipTracking's
  "Current Trip" table; blank for sources that don't expose them).
- `temperature` / `wind_speed` / `wind_direction` / `pressure` /
  `humidity` / `cloud_coverage` — current weather at the ship's
  position. MyShipTracking reads its "Weather" table; MarineRadar calls
  its `/api/weather` endpoint. Units follow each source (e.g. wind in
  knots from MyShipTracking, km/h from MarineRadar); `cloud_coverage` is
  blank for MarineRadar (its weather response has no cloud figure).
- `full_distance` — cumulative distance since departure, in nautical
  miles (see the source comment on `BASE_DISTANCE_NM` for the
  derivation). One chain across all sources: each new row adds the
  Haversine leg from the previous row regardless of which site it came
  from.
- `source` — which site this row's position came from
  (`myshiptracking`, `marineradar`, ...). This column is **not**
  considered by the duplicate-position guard.

A field a source doesn't have (including MyShipTracking's `---` "not
available" cells) is written as a blank cell.

Before appending, the script applies two guards against the sheet's
current last row and skips the write if either trips:

- **Duplicate position** — the new `(lat, lon)` is within ~10m (0.0001°)
  of the last row. Avoids piling up rows while the ship is stationary
  (in port, at anchor) and the sites keep returning the same last-known
  AIS fix.
- **Stale fix** — the new `Time` is not strictly newer than the last
  row's `Time`. Since one row is appended per run with no re-sorting
  step, writing an older fix (which can happen only if *every* source
  serves an out-of-date position at once) would leave the tab out of
  chronological order, so it's dropped instead.

## Setup

1. Find the target ship's MMSI (e.g. via MyShipTracking, MarineTraffic,
   or VesselFinder) and confirm it has a page on the sites listed under
   "Sources" above.
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
cd tracking/automatic/scraper/position
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

This repo is **public**, so GitHub Actions minutes are unlimited and
this workflow's every-30-minute schedule costs nothing against a quota.
(If the repo is ever made private, the free tier is 2,000 minutes/month
shared across every workflow — recompute this workflow's and
[aisstream](../../api/aisstream/)'s worst cases together at that point.)

## Known limitations

- Every source scrapes an undocumented page layout, not a public API —
  a site can change its structure at any time and silently break that
  source. The design contains the blast radius:
  - Within a source, only `(lat, lon)` is required; every other field
    is best-effort and left blank if not found, so a partial page change
    degrades gracefully.
  - Across sources, the run succeeds as long as **at least one** source
    returns a position; a broken source is logged (to stdout) and
    skipped. Only if **every** source fails does the script exit nonzero
    — GitHub Actions then marks the run failed and emails a
    notification, since an all-sources failure almost always means a
    structural change, not the ship being out of coverage.
- Static vessel-info fields (`imo`, `flag`, `call_sign`, ...) rarely
  change and are repeated on every row — this keeps the sheet's shape
  simple at the cost of redundant storage, a non-issue at this data
  volume.
- A missing User-Agent header gets a 403 from some of these sites; every
  source sends a standard browser User-Agent string.
- If the ship hasn't reported a new AIS position recently, a site may
  serve a stale position rather than an error — there's no built-in
  staleness check. The `Time` column carries the AIS observation time,
  so a stale fix is at least visible as an old timestamp, but the row is
  still written.
- All sources are queried by a single job that appends exactly one row
  per run, so the `Scraper` tab stays in chronological order on its own —
  there's no separate sorting step.
- GitHub Actions cron schedules are not exact — runs can be delayed
  under load, so the 30-minute interval is approximate.
