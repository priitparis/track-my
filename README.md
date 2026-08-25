# track-my

Ship location tracking: collects a ship's position (and related data)
through several independent methods, all writing to the same Google
Sheets spreadsheet, and serves that data as GeoJSON for display on a map
(uMap).

## Structure

- [tracking/](tracking/) — the tracking methods themselves, plus the
  shared read endpoint:
  - [tracking/manual/](tracking/manual/) — button-triggered, user-initiated
    capture (a phone page with a "save my location" button).
  - [tracking/automatic/](tracking/automatic/) — scheduled methods that run
    with no manual action required (GitHub Actions on a cron schedule),
    grouped by technique:
    - [tracking/automatic/api/](tracking/automatic/api/) — methods that call an
      official data API (AISStream.io, Gemini).
    - [tracking/automatic/scraper/](tracking/automatic/scraper/) — methods that
      read a public web page (MyShipTracking.com).
  - [tracking/google-apps-script/](tracking/google-apps-script/) — one
    shared, read-only GeoJSON endpoint serving any method's sheet tab,
    used by every method's map layer.
- [helper/](helper/) — one-off, manually-run tools that support the
  tracking system but aren't part of its ongoing automation (no GitHub
  Actions workflow runs anything here), plus ready-to-use sample files.

Every method writes to its own tab in the same spreadsheet (`Location`,
`Auto`, `Scraper`, `Events`, `Blog`), so methods never interfere with
each other; each subdirectory's own README has its setup steps and
required secrets/environment variables.

## Contributing

See [CLAUDE.md](CLAUDE.md) for working conventions used in this repo.
