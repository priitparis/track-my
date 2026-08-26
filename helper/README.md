# Helper tools

One-off, manually-run tools that support the [tracking/](../tracking/)
system but aren't part of its ongoing automation — no GitHub Actions
workflow runs anything in this directory.

## Contents

- [sample-files/](sample-files/) — a ready-to-use example spreadsheet
  and uMap config, with invented data, safe to import as a starting
  point or reference for the spreadsheet/map structure the tracking
  methods expect.
- [myshiptracking-history/](myshiptracking-history/) — a script for a
  one-time export of a vessel's recent MyShipTracking.com event history
  to CSV, for manual review or import into Excel.
- [backfill-full-distance/](backfill-full-distance/) — a script that
  fills in the `Scraper` tab's `full_distance` column for rows written
  before that column existed.
