# MyShipTracking event history export

A one-off helper (not part of the ongoing [tracking/](../../tracking/)
system) for pulling a ship's recent event history — port arrivals/
departures, start/stop moving, coverage changes, each with a timestamp
and position — from MyShipTracking's website, and saving it to a CSV
for import into Excel.

## Why this exists

MyShipTracking's `/vessel-events` page shows a public log of a vessel's
recent events. It's more detailed than a simple track (it includes port
names, speed, and course), but it's paginated (20 rows per page) and
**only covers roughly the last 3 weeks**, regardless of how far back you
set the date range in the URL — the site silently caps it server-side.

## Usage

```bash
python3 -m venv history-venv
source history-venv/bin/activate     # Windows: history-venv\Scripts\activate
pip install -r requirements.txt

python fetch_history.py <mmsi> <start_unix> <end_unix> [output.csv]
```

- `mmsi` — the ship's MMSI number.
- `start_unix` / `end_unix` — Unix timestamps for the requested range.
  Getting these exactly right doesn't matter much, since the site caps
  results to ~3 weeks back regardless — a wide range (e.g. covering the
  last 2 months) is a safe default. You can compute one with e.g.
  `date -d '2026-08-01' +%s`, or copy them out of the site's own URL
  after picking a date range in its UI.
- `output.csv` — optional, defaults to `<mmsi>_history.csv`.

Example:

```bash
python fetch_history.py 276017710 1785715200 1787671664 sanuk.csv
```

The output CSV has columns: `date, time, event, port, country, lat, lon,
speed, course` — one row per event, sorted chronologically. Open it
directly in Excel.

## Known limitations

- Only covers roughly the last 3 weeks of events — there's no known free
  way to get older history for a specific vessel (see the project
  conversation history for what else was investigated and ruled out:
  AISStream has no historical data at all, MarineTraffic's free tier
  only shows 1 day, and paid historical-data products from VesselFinder/
  Datalastic/MarineTraffic were judged too expensive for a one-off need).
- This regex-scrapes the page's HTML structure, not a documented API —
  MyShipTracking could change it at any time without notice, silently
  breaking extraction.
- Some rows (mostly `IN Coverage` / `OUT of Coverage`) don't have a
  speed or course in the source page; those fields are left blank
  rather than guessed.
- A `511°` course value in the output is the site's own placeholder for
  "not available," not a real heading — this is a quirk of the source
  data, not a parsing bug.
