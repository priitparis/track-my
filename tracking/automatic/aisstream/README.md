# AISStream.io ship tracker

Automatic ship tracking via AISStream.io — polls a ship's live AIS position
by MMSI on a schedule, no manual action required.

## Architecture

- **Data source**: [AISStream.io](https://aisstream.io/) — a free
  real-time AIS WebSocket API.
- **Trigger**: GitHub Actions, scheduled (cron, hourly) and manual
  (`workflow_dispatch`).
- **Runtime**: [fetch_position.py](fetch_position.py), a short-lived
  Python script (waits up to `CONNECT_TIMEOUT_SECONDS`, 120s by default),
  run fresh on every scheduled tick — no persistent process.
- **Database**: the same spreadsheet as the
  [manual method](../../manual/google-apps-script/) (the manual method
  writes to its `location` tab), but a **separate tab** (`Auto`) with the
  same `Lat` / `Lon` / `Time` column convention, so manual and automatic
  points can be styled differently later (e.g. different map
  layers/colors).
- **Map feed**: a separate, read-only Apps Script web app
  ([google-apps-script/](google-apps-script/)) serves the `Auto` tab as
  GeoJSON for a uMap layer — the same role the manual method's
  `getGeoJSON()` plays for its own `location` tab, kept as its own
  deployment so the two tracking methods stay independent end-to-end.

## Files

- [fetch_position.py](fetch_position.py) — connects to AISStream, waits
  for one position report for the configured MMSI, and appends it to the
  `Auto` sheet tab.
- [requirements.txt](requirements.txt) — Python dependencies
  (`websockets`, `gspread`, `google-auth`, `python-dotenv`).
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).
- [test_connection.py](test_connection.py) — connects, subscribes for the
  configured MMSI, and prints the first message received, then exits.
  Useful for checking `AISSTREAM_API_KEY` and `SHIP_MMSI` are correct
  without writing anything to the sheet.
- [google-apps-script/](google-apps-script/) — a separate, read-only Apps
  Script project that serves the `Auto` tab as GeoJSON for a map layer.
  See its own README for setup.

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/aisstream-tracker.yml](../../../.github/workflows/aisstream-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Setup

1. Get a free AISStream API key at
   [aisstream.io/authenticate](https://aisstream.io/authenticate).
2. Find the target ship's MMSI (e.g. via MarineTraffic or VesselFinder).
3. Create a Google Cloud service account, enable the Google Sheets API for
   its project, and download its JSON key.
4. Share the spreadsheet (the same one the
   [manual method](../../manual/google-apps-script/) uses) with the
   service account's `...@...iam.gserviceaccount.com` email (Editor
   access), the same way you'd share it with any collaborator.
5. Add an `Auto` tab to that spreadsheet, with a header row
   `Lat | Lon | Time` matching the `location` tab.
6. In the GitHub repo, add these secrets under Settings → Secrets and
   variables → Actions: `AISSTREAM_API_KEY`, `SHIP_MMSI`, `GCP_SA_KEY`
   (paste the full downloaded JSON key file's content as-is — the
   workflow writes it to a temp file at runtime, it's never committed),
   `GOOGLE_SHEET_ID` (from the sheet's URL:
   `/spreadsheets/d/<THIS_PART>/edit`). `CONNECT_TIMEOUT_SECONDS` is set
   directly in the workflow file (not a secret) — see "Actions minutes
   budget" below before changing it or the cron interval.
7. Trigger the workflow manually once via the Actions tab
   (`workflow_dispatch`) to confirm a row appears in `Auto` before
   relying on the cron schedule.
8. (Optional, for map display) Set up the
   [google-apps-script/](google-apps-script/) GeoJSON endpoint and point
   a uMap layer at it — see that directory's README for deployment
   steps.

### Actions minutes budget

On a private GitHub repo, the free tier includes 2,000 Actions minutes
per month (public repos are unlimited). GitHub also caps any single job
at 6 hours regardless of your own timeout, so a very long
`CONNECT_TIMEOUT_SECONDS` doesn't buy unlimited waiting — it just spends
the same budget on fewer, longer attempts instead of more, shorter ones.

A run's cost is roughly `CONNECT_TIMEOUT_SECONDS` plus ~25s of setup
overhead (checkout, Python install), *every time*, since a run that
never receives a PositionReport still waits out the full timeout. The
defaults here (hourly cron, 120s timeout) cost at most
`720 runs × 145s ≈ 1,740 minutes/month` in the worst case (no position
ever received), leaving some headroom under the 2,000 minute cap. If you
change the interval or timeout, recompute this — e.g. a 15-minute
interval with the same 120s timeout would cost up to ~3,480 min/month,
well over the free tier.

### Local testing (optional)

Use a Python virtual environment so dependencies stay isolated from the
system Python:

```bash
cd tracking/automatic/aisstream
python3 -m venv aisstream-venv
source aisstream-venv/bin/activate     # Windows: aisstream-venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # fill in the real values; .env is git-ignored
# copy your downloaded service account key to gcp-service-account.json
# (same directory; also git-ignored) — GCP_SA_KEY_PATH in .env already
# points at it by default

python test_connection.py     # optional: verify the AIS subscription works first
python fetch_position.py      # loads .env automatically (run from this directory)
```

## Known limitations

- The subscription message must include a `BoundingBoxes` field — without
  it, AISStream accepts the connection and confirms the subscription, but
  never sends any position data. Both scripts subscribe to the whole
  world (`[[-90, -180], [90, 180]]`) and rely on `FiltersShipMMSI` to
  narrow results to the target ship.
- The full subscription message must be sent within 3 seconds of the
  WebSocket connecting, or AISStream closes the connection.
- Free-tier limits (per AISStream's docs): max 3 concurrent subscribed
  connections per account, max 200 MMSIs per subscription, and at most
  one subscription update per second per connection — not a concern for
  this single-ship, one-connection-per-run setup, but worth knowing if
  this is extended to track more ships.
- If the ship is outside AIS receiver coverage during a run, the script
  exits cleanly without writing a row — this is expected and does not
  fail the workflow (a red X only appears for genuine problems, such as
  missing secrets or a Sheets write failure). AISStream relies on a
  community network of land-based receivers (~200km range each), so its
  coverage can differ from aggregator sites that also use satellite AIS.
- GitHub Actions cron schedules are not exact — runs can be delayed under
  load, so the hourly interval is approximate.
- Each run opens a fresh WebSocket connection rather than keeping one
  open continuously; this matches how GitHub Actions jobs work and keeps
  the setup serverless.
