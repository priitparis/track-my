# Backfill full_distance

A one-off helper (not part of the ongoing [tracking/](../../tracking/)
system) that computes the `full_distance` column for every existing row
in the `Scraper` sheet tab that was written before that column existed.

## Why this exists

[fetch_position.py](../../tracking/automatic/scraper/position/fetch_position.py)
now writes a `full_distance` value (cumulative nautical miles traveled
since departure) on every new row it appends, but rows written before
that column was added are left blank. This script fills those in, using
the exact same Haversine + `BASE_DISTANCE_NM` logic (imported directly
from `fetch_position.py`, not duplicated here): the first row gets
`BASE_DISTANCE_NM`, and each following row adds the Haversine distance
from the previous row.

## Usage

```bash
python3 -m venv backfill-venv
source backfill-venv/bin/activate     # Windows: backfill-venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env    # fill in GCP_SA_KEY_PATH / GOOGLE_SHEET_ID
python backfill_full_distance.py
```

Safe to re-run: it always recomputes every row from scratch (using each
row's own Lat/Lon, not any existing full_distance value) and overwrites
the column in one batch update.

## Known limitations

- Requires the `full_distance` column to already exist in the sheet's
  header row — this script doesn't create it.
- Recomputes every row's distance from scratch each time it's run; for
  a very large sheet this means one batch update covering every row,
  not just the ones missing a value.
