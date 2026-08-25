# MyShipTracking event log scraper

Automatic ship event tracking by scraping the ship's public
[MyShipTracking.com](https://www.myshiptracking.com/) event log
(`/vessel-events`) — port arrivals/departures, start/stop moving,
coverage changes — on a schedule, no manual action required.

This is a **separate** method from
[../myshiptracking/](../myshiptracking/), which scrapes the ship's
*current* position only, from a different page, on every run. This one
scrapes a rolling *event log* covering roughly the last 3 weeks, so most
runs will re-fetch events already seen — duplicates are avoided by
comparing each event's `(Time, Event)` against what's already in the
sheet before appending anything new.

## Architecture

- **Data source**: the ship's public event log at
  `myshiptracking.com/vessel-events?mmsi=<MMSI>&time=<start>_<end>` — no
  API key or account needed. Each row is parsed directly out of the
  page's HTML table; no JavaScript rendering or headless browser
  required. See [helper/myshiptracking-history/](../../../../helper/myshiptracking-history/)
  for the one-off manual CSV export this script's parsing logic is
  based on.
- **Trigger**: GitHub Actions, scheduled (cron) and manual
  (`workflow_dispatch`).
- **Runtime**: [fetch_events.py](fetch_events.py), a short-lived Python
  script, run fresh on every scheduled tick — no persistent process.
  Each run re-fetches the whole ~3-week window and only appends events
  not already recorded.
- **Database**: the same spreadsheet as every other tracking method, in
  its own **separate tab** (`Events`), using the same `Lat` / `Lon` /
  `Time` column convention as the other tabs, plus `Event`, `Port`,
  `Country`, `Speed`, `Course`.

## Files

- [fetch_events.py](fetch_events.py) — fetches every page of the event
  log for the configured MMSI and lookback window, parses each row, and
  appends any events not already present in the `Events` sheet tab.
- [requirements.txt](requirements.txt) — Python dependencies
  (`requests`, `gspread`, `google-auth`, `python-dotenv`).
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/myshiptracking-events-tracker.yml](../../../../.github/workflows/myshiptracking-events-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Sheet columns

`Lat | Lon | Time | Event | Port | Country | Speed | Course`

- `Time` is an ISO-8601 UTC timestamp built from the page's separate
  date/time fields (e.g. `2026-08-24T10:06:00Z`), matching the
  convention every other tracking method's `Time` column uses.
- `Event` is one of: `PORT ARRIVAL`, `PORT DEPARTURE`, `START Moving`,
  `STOP Moving`, `IN Coverage`, `OUT of Coverage`.
- `Port` / `Country` are blank for events that aren't tied to a specific
  port (e.g. `IN Coverage`).
- A `511°` course value is the source site's own placeholder for "not
  available," not a real heading.

## Setup

1. Reuse the same Google Cloud service account as the other automatic
   methods (or create a new one the same way), and make sure it has
   Editor access to the shared spreadsheet.
2. Add an `Events` tab to that spreadsheet, with a header row
   `Lat | Lon | Time | Event | Port | Country | Speed | Course`.
3. In the GitHub repo, add these secrets under Settings → Secrets and
   variables → Actions (skip any that already exist from setting up the
   other methods, since `SHIP_MMSI`, `GCP_SA_KEY`, and `GOOGLE_SHEET_ID`
   are shared across methods): `SHIP_MMSI`, `GCP_SA_KEY` (the full
   service account JSON key content), `GOOGLE_SHEET_ID`.
4. Trigger the workflow manually once via the Actions tab
   (`workflow_dispatch`) to confirm rows appear in `Events` before
   relying on the cron schedule.
5. (Optional, for map display) Point a uMap layer at the
   [shared GeoJSON endpoint](../../../google-apps-script/)'s Web App URL
   with `?sheet=Events`.

### Local testing (optional)

Use a Python virtual environment so dependencies stay isolated from the
system Python:

```bash
cd tracking/automatic/scraper/myshiptracking-events
python3 -m venv events-venv
source events-venv/bin/activate     # Windows: events-venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # fill in the real values; .env is git-ignored
# copy your downloaded service account key to gcp-service-account.json
# (same directory; also git-ignored) — GCP_SA_KEY_PATH in .env already
# points at it by default

python fetch_events.py        # loads .env automatically (run from this directory)
```

## Known limitations

- This regex-scrapes the event log's HTML table, not a documented
  public API — MyShipTracking could change its page structure at any
  time without notice, silently breaking extraction. The event type
  itself is read from whatever label follows each row's icon, rather
  than matched against a fixed list — a fixed list previously caused
  whole rows (including the ship's most recent event) to be silently
  dropped when MyShipTracking added event types (e.g. "Change Sea Area",
  "Detected in Sea") that weren't in it.
- MyShipTracking only serves roughly the last 3 weeks of event history
  for a vessel, regardless of how far back `LOOKBACK_DAYS` requests —
  there's no way to backfill further back than that from this source.
  See [helper/myshiptracking-history/](../../../../helper/myshiptracking-history/)
  for what was investigated for older history.
- Duplicate detection reads every existing row in the `Events` tab on
  every run (`sheet.get_all_values()`), which is fine at this data
  volume but would need revisiting if the sheet grows very large.
- A missing User-Agent header gets a 403 from this site; the script
  always sends a standard browser User-Agent string.
- GitHub Actions cron schedules are not exact — runs can be delayed
  under load.
