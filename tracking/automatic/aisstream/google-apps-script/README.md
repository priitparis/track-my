# AISStream GeoJSON endpoint

A read-only Google Apps Script web app that serves the `Auto` sheet tab
(written by [../fetch_position.py](../fetch_position.py)) as GeoJSON, so
a map (e.g. uMap) can read it as a live layer — the same role
[Code.gs's `getGeoJSON()`](../../../manual/google-apps-script/Code.gs)
plays for the manual method's `location` tab.

This is a **separate** Apps Script project from the manual method's,
deployed on its own, even though both read from the exact same
spreadsheet (the manual method's `location` tab and this method's `Auto`
tab live side by side in it) — keeping automatic and manual tracking
fully independent at the deployment level, per the project's directory
convention (see [tracking/automatic/README.md](../../README.md)).

A spreadsheet can only have one *container-bound* script (the kind you
get via Extensions → Apps Script from inside the sheet) — the manual
method already uses that slot for its own project. So this script is a
**standalone** project instead, created directly at script.google.com,
and it opens the spreadsheet explicitly by ID
(`SpreadsheetApp.openById(SPREADSHEET_ID)`) rather than relying on
`getActiveSpreadsheet()`, which only works for container-bound scripts.

Unlike the manual method's script, this one is read-only: there's no
`doGet` branch for an HTML page and no `saveData` — this project only
serves data, it never writes any. Writing to `Auto` is
[fetch_position.py](../fetch_position.py)'s job, run by GitHub Actions.

## Files

- [Code.gs](Code.gs) — `doGet` always returns the `Auto` sheet as a
  GeoJSON `FeatureCollection`. `SPREADSHEET_ID` at the top must be filled
  in with the real spreadsheet ID before deploying.

This is a documentation copy of code that runs in Google's environment,
not a deploy source — to update the live version, edit the script
directly in the Google Apps Script editor and keep this copy in sync,
same as the manual method's [Code.gs](../../../manual/google-apps-script/Code.gs).

## Setup

1. Go to [script.google.com](https://script.google.com) and create a
   **New project** — do *not* open it from within the spreadsheet's
   Extensions menu, since that slot is already taken by the manual
   method's container-bound script.
2. Paste [Code.gs](Code.gs)'s content into the project's `Code.gs`.
3. Fill in `SPREADSHEET_ID` at the top with the ID of the spreadsheet
   `fetch_position.py` writes to (from its URL:
   `/spreadsheets/d/<THIS_PART>/edit`).
4. Share that spreadsheet with the Google account you're using for this
   Apps Script project (Editor access), if it isn't already the owner —
   `openById()` still needs permission to read it.
5. Deploy → New deployment → Web app. Execute as yourself, access to
   Anyone (uMap needs to fetch this URL without authentication).
6. Use the resulting Web App URL directly as the uMap layer's Remote
   Data URL (Format: GeoJSON) — no `?format=` query parameter needed,
   since this endpoint only ever serves GeoJSON.
