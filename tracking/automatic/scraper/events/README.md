# Ship event-log scraper

Automatic ship event tracking by scraping several public vessel-tracking
sites for the ship's recent event history — port arrivals/departures,
start/stop moving, coverage and sea-area changes — on a schedule, no
manual action required. Every run queries all configured sources, takes
the **union** of everything they report, and appends any events not
already recorded.

This is a **separate** method from the
[position scraper](../position/), which records the ship's *current
position* on every run. This one scrapes rolling *event logs* (a few
weeks at most), so most runs re-see events already written — duplicates
are avoided by comparing each event's `(Time, Event)` against what's
already in the sheet before appending anything new.

## Sources

Each source is a module under [sources/](sources/) exposing `SOURCE` (a
short site name, for log messages) and
`fetch(mmsi, timeout, lookback_days) -> list[dict]`, one dict per event
in the site's window. [sources/__init__.py](sources/__init__.py) lists
them in `SOURCES`; adding a site is a new module plus one line there.

| Module | Site | How events are read | History depth |
|---|---|---|---|
| [sources/myshiptracking.py](sources/myshiptracking.py) | [myshiptracking.com](https://www.myshiptracking.com/) | Pages through the `/vessel-events` HTML table (`?mmsi=&time=<start>_<end>`), parsing each row directly out of the markup. The event type is read from whatever label follows the row's `<i>` icon — not matched against a fixed list. | ~3 weeks |
| [sources/aisvesseltracker.py](sources/aisvesseltracker.py) | [aisvesseltracker.com](https://aisvesseltracker.com/) (Voyage Radar) | Next.js app; the page streams its server data as `self.__next_f.push([...])` chunks (same shape as the position scraper's MarineRadar/AISVesselTracker sources). Brace-matching the embedded `"initialEvents": { "data": [ … ] }` array yields a structured list: `event_type`, position, `sog`/`cog`, `water_body`, ISO-8601 `timestamp`. | ~1 week (free tier) |

No site needs an API key or account, and the data is served over plain
HTTP (in the page's HTML or its embedded server-data payload) — no
JavaScript rendering or headless browser.

**Event-type labels are stored exactly as each site words them** — there
is no shared vocabulary. MyShipTracking writes `PORT ARRIVAL`,
`START Moving`, `Change Sea Area`, …; AISVesselTracker writes
`port_arrival`, `started_moving`, `waterbody_changed`, …. The union is
de-duplicated on `(Time, Event)`, so the *same* real-world event seen by
two sites under different names is kept as two rows.

## Architecture

- **Trigger**: GitHub Actions, scheduled (cron, daily) and manual
  (`workflow_dispatch`).
- **Runtime**: [fetch_events.py](fetch_events.py), a short-lived Python
  script run fresh on every scheduled tick — no persistent process. It
  queries all sources **concurrently** (a `ThreadPoolExecutor`), each
  waiting up to `REQUEST_TIMEOUT_SECONDS` (30s by default), so a run's
  wall time stays near the slowest single source, not the sum. (A source
  may itself make more than one request — MyShipTracking pages through
  the log — but those are sequential within that source's slot.)
- **Merge**: the flat union of every source's events. There is no
  "primary" source and no cross-source reconciliation; de-duplication is
  purely `(Time, Event)`, applied both within a run's batch and against
  the sheet's existing rows. A run's new events are sorted by `Time`
  (Event breaking ties within a minute) before being appended, so the
  tab stays in chronological order — rows are only ever appended, never
  re-sorted.
- **Database**: the same spreadsheet as every other tracking method, in
  its own **separate tab** (`Events`), using the same `Lat` / `Lon` /
  `Time` column convention as the other tabs, plus `Event`, `Port`,
  `Country`, `Speed`, `Course`.
- **Map feed**: point a uMap layer at the
  [shared GeoJSON endpoint](../../../google-apps-script/)'s Web App URL
  with `?sheet=Events`.

## Files

- [fetch_events.py](fetch_events.py) — the orchestrator: queries every
  source in [sources/](sources/), unions their events, applies the
  duplicate guard, and appends new rows to the `Events` tab.
- [sources/](sources/) — one module per site (see "Sources" above), plus
  [sources/_common.py](sources/_common.py) (shared User-Agent, the
  common event-dict shape).
- [requirements.txt](requirements.txt) — Python dependencies
  (`requests`, `gspread`, `google-auth`, `python-dotenv`).
- [test_sources.py](test_sources.py) — unit tests for each source
  module's parsing, against small fixtures. (`pytest`; dev-only, not in
  requirements.txt.)
- [test_fetch_events.py](test_fetch_events.py) — unit tests for the
  orchestrator (source collection, the union, the duplicate guard).
- [.env.example](.env.example) — documents the required environment
  variables, for local runs.
- [gcp-service-account.json.example](gcp-service-account.json.example) —
  shows the shape of the Google service account key file; copy your real
  downloaded key to `gcp-service-account.json` next to it (git-ignored).

The GitHub Actions workflow itself lives at the repo root,
[.github/workflows/events-tracker.yml](../../../../.github/workflows/events-tracker.yml),
not in this directory — GitHub only discovers workflows under
`.github/workflows/` at the repo root, so it can't be colocated here.

## Sheet columns

`Lat | Lon | Time | Event | Port | Country | Speed | Course`

- `Time` is an ISO-8601 UTC timestamp built from each source's
  date/time (e.g. `2026-08-24T10:06:00Z`), matching the convention every
  other tracking method's `Time` column uses.
- `Event` is written through as the reporting site words it — e.g.
  `PORT ARRIVAL` / `PORT DEPARTURE` / `START Moving` / `STOP Moving` /
  `IN Coverage` / `OUT of Coverage` / `Change Sea Area` from
  MyShipTracking, or `port_arrival` / `started_moving` /
  `stopped_moving` / `waterbody_changed` / `online_after_gap` /
  `berth_departure` from AISVesselTracker.
- `Port` / `Country` are populated for port-tied events when the source
  exposes them: MyShipTracking gives a port name and country;
  AISVesselTracker gives only a port slug (in `Port`), leaving `Country`
  blank. Non-port events (e.g. a coverage change) leave both blank.
- `Speed` / `Course` are the source's values as shown (units follow the
  site — MyShipTracking appends `kn` / `°`, AISVesselTracker gives bare
  numbers). A `511°` course from MyShipTracking is that site's
  placeholder for "not available," not a real heading.

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
cd tracking/automatic/scraper/events
python3 -m venv events-venv
source events-venv/bin/activate     # Windows: events-venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # fill in the real values; .env is git-ignored
# copy your downloaded service account key to gcp-service-account.json
# (same directory; also git-ignored) — GCP_SA_KEY_PATH in .env already
# points at it by default

python fetch_events.py        # loads .env automatically (run from this directory)

# run the tests (needs pytest, not in requirements.txt):
pip install pytest && pytest
```

## Known limitations

- Every source scrapes an undocumented page layout, not a public API —
  a site can change its structure at any time and silently break that
  source. The design contains the blast radius:
  - Within a source, a row/event it can't parse is skipped; other
    events on the page still come through.
  - Across sources, the run succeeds as long as **at least one** source
    returns events; a broken source is logged (to stdout) and skipped.
    Only if **every** source fails *or* returns nothing does the script
    exit nonzero — GitHub Actions then marks the run failed and emails a
    notification, since every source going quiet at once almost always
    means a structural change rather than the ship genuinely having zero
    events (not even a coverage change) everywhere.
  - MyShipTracking's event type is read from whatever label follows each
    row's icon, not matched against a fixed list — a fixed list
    previously caused whole rows (including the ship's most recent
    event) to be silently dropped when MyShipTracking added event types
    (e.g. "Change Sea Area", "Detected in Sea") that weren't in it.
- History depth is bounded by each source: MyShipTracking serves roughly
  the last 3 weeks and AISVesselTracker only the last week on the free
  tier, regardless of how far back `LOOKBACK_DAYS` requests. There is no
  way to backfill older history from these sources. See
  [helper/myshiptracking-history/](../../../../helper/myshiptracking-history/)
  for what was investigated for older history.
- The same real-world event reported by two sites under different labels
  (e.g. `PORT ARRIVAL` vs `port_arrival`, often a minute apart) is kept
  as two separate rows — `(Time, Event)` de-duplication is exact-match
  only, by design (keeping each site's raw vocabulary).
- Duplicate detection reads every existing row in the `Events` tab on
  every run (`sheet.get_all_values()`), which is fine at this data
  volume but would need revisiting if the sheet grows very large.
- A missing User-Agent header gets a 403 from some of these sites; every
  source sends a standard browser User-Agent string.
- GitHub Actions cron schedules are not exact — runs can be delayed
  under load.
