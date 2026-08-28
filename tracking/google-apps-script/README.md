# Shared GeoJSON endpoint

A single, read-only Google Apps Script web app that serves any tracking
method's sheet tab as GeoJSON, selected by a `?sheet=` query parameter —
so one map (e.g. uMap) can add a layer per tracking method, each
pointing at the same Web App URL with a different `?sheet=` value:

- `?sheet=Location` — the [manual method](../manual/google-apps-script/)'s tab
- `?sheet=Auto` — the [AISStream method](../automatic/api/aisstream/)'s tab
- `?sheet=Scraper` — the [scraper method](../automatic/scraper/position/)'s tab
- `?sheet=Events` — the [event log scraper](../automatic/scraper/myshiptracking-events/)'s tab (each point's `properties` also includes `event`, `port`, `country`, `speed`, `course` when present, on top of the usual `time`)
- `?sheet=Blog` — the [blog location extractor](../automatic/api/blog-locations/)'s tab (each point's `properties` also includes `name`, `description`, `post_title`, `post_date`, `post_url`, `group_id`)

Optional parameters combine with `?sheet=`:

- `&latest=1` — only the single most recent point, instead of the full
  history — e.g. `?sheet=Auto&latest=1`. Still wrapped in the same
  `FeatureCollection` shape (with zero or one `Feature` in it), so
  existing GeoJSON consumers don't need special handling for it.
- `&exclude_latest=1` — the opposite: every point *except* the most
  recent one — e.g. `?sheet=Auto&exclude_latest=1`. Useful for drawing
  "everywhere the ship has been" separately from its current position
  (e.g. a different marker for the latest point). If both `&latest=1`
  and `&exclude_latest=1` are given, `&latest=1` wins.
- `&line=1` — adds a `LineString` Feature connecting every point in
  order, so a map can draw the ship's route — e.g.
  `?sheet=Auto&line=1` returns the individual points *and* the route
  line together. Use `&line=only` instead to get *just* the line,
  without the individual points (e.g. `?sheet=Auto&line=only`). A line
  needs at least two points, so `&line=` has no effect when combined
  with `&latest=1`. The line's `Feature.properties` includes
  `dashArray` (set via `LINE_DASH_ARRAY` in [Code.gs](Code.gs), default
  `"5,5"`) — a style property uMap recognizes to render the route dashed
  instead of solid, without any per-layer styling needed in uMap itself.
- `&group=` — only include rows whose `group_id` column matches this
  value — e.g. `?sheet=Blog&group=2`. Only meaningful for sheets that
  have a `group_id` column (currently just `Blog`, since one blog can
  cover more than one trip over time); on sheets without that column,
  `&group=` has no effect.

This replaces having a separate GeoJSON endpoint per automatic method;
the manual method's own Apps Script project still handles its own
button-triggered page and `saveData` (writing), since this endpoint is
read-only and only serves data — it never writes any.

## Files

- [Code.gs](Code.gs) — `doGet` reads `?sheet=`, validates it against
  `ALLOWED_SHEETS`, and returns that sheet tab as a GeoJSON
  `FeatureCollection` — trimmed to just the latest point with
  `?latest=1`, or with the latest point removed with
  `?exclude_latest=1`, optionally filtered to one `group_id` with
  `?group=`, and/or including a route `LineString` with `?line=1` (or
  `?line=only` for just the line). `SPREADSHEET_ID` at the top must be
  filled in with the real spreadsheet ID before deploying.

This is a documentation copy of code that runs in Google's environment,
not a deploy source — to update the live version, edit the script
directly in the Google Apps Script editor and keep this copy in sync.

## Setup

1. Go to [script.google.com](https://script.google.com) and create a
   **New project** — do *not* open it from within the spreadsheet's
   Extensions menu, since that slot is already taken by the manual
   method's container-bound script.
2. Paste [Code.gs](Code.gs)'s content into the project's `Code.gs`.
3. Fill in `SPREADSHEET_ID` at the top with the ID of the spreadsheet
   all tracking methods write to (from its URL:
   `/spreadsheets/d/<THIS_PART>/edit`).
4. Share that spreadsheet with the Google account you're using for this
   Apps Script project (Editor access), if it isn't already the owner —
   `openById()` still needs permission to read it.
5. Deploy → New deployment → Web app. Execute as yourself, access to
   Anyone (uMap needs to fetch this URL without authentication).
6. In uMap, add one layer per tracking method, each with Remote Data URL
   set to the Web App URL plus the matching `?sheet=` parameter (Format:
   GeoJSON) — e.g. `<Web App URL>?sheet=Auto`.

## Known limitations

- `ALLOWED_SHEETS` is an explicit allowlist — adding a new tracking
  method's tab here requires editing and redeploying this script.
- A request with no `?sheet=` parameter, or one not in the allowlist,
  gets a plain-text error message instead of GeoJSON.
