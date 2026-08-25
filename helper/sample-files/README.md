# Sample files

Two ready-to-use example files, safe to publish and import as-is —
useful as a starting point instead of building a spreadsheet or uMap
config from scratch.

## Files

- [tracking_sample.xlsx](tracking_sample.xlsx) — a spreadsheet with the
  same sheet names and columns as the real tracking spreadsheet
  (`Location`, `Auto`, `Scraper`, `Blog`, `Events` — see each tracking
  method's own README for what each column means), but with invented
  data for a short fictional two-stop trip ("Example Harbor" →
  "Example Bay"). Import this into Google Sheets as a starting point,
  then point the tracking methods' `GOOGLE_SHEET_ID` at it.
- [umap_backup_sample.umap](umap_backup_sample.umap) — a uMap layer
  configuration with two example layer groups: **Scraper (peamine)**
  (all three layer types — route line, latest position, history — for
  the primary automatic method) and **Substack** (the LLM-extracted
  blog-locations layer). Import this into uMap (Import data → upload
  file → format "uMap") as a starting point, then update each layer's
  Remote Data URL with your own deployed
  [shared GeoJSON endpoint](../../tracking/google-apps-script/)'s Web
  App URL.

## Why these are safe to publish

Both files are deliberately stripped of anything specific to a real
trip:

- All coordinates, dates, and narrative text are invented, not from any
  real voyage.
- Every `remoteData.url` in the uMap file is replaced with
  `https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec` — a
  placeholder, not a real deployed Apps Script URL.
- The uMap file only includes two of the possible layer groups (as a
  representative example of the pattern — see
  [tracking/google-apps-script/README.md](../../tracking/google-apps-script/README.md)
  for the full set of `?sheet=` values available), and omits the
  hand-entered trip-note layers entirely, since those would otherwise
  need real personal content to be meaningful.
- The map's center/zoom point in the uMap file is a neutral location,
  not any real trip's starting point.

If you regenerate either file from your own real data, re-check it for
the same things before committing — sample files are meant to be
committed to a public repo; your own working spreadsheet and uMap
export are not (see the repo root [.gitignore](../../.gitignore), which
excludes `*.csv` and `umap_backup*.json` for this reason — these
`.xlsx`/`.umap` sample files are a deliberate, reviewed exception).
