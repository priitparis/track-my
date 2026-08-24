# Tracking

Ship location tracking, via multiple independent methods:

- [manual/](manual/) — button-triggered, user-initiated capture.
- [automatic/](automatic/) — scheduled, no manual action required.
  Grouped by technique: [automatic/api/](automatic/api/) for methods
  that call an official data API, [automatic/scraper/](automatic/scraper/)
  for methods that read a public web page.

Every method writes to its own tab in the same underlying spreadsheet
(`Location`, `Auto`, `Scraper`, ...), so they never interfere with each
other. Reading that data back out for a map happens through a single
shared endpoint:

- [google-apps-script/](google-apps-script/) — one read-only GeoJSON
  endpoint, serving any method's tab via a `?sheet=` parameter, used by
  every method's map layer.
