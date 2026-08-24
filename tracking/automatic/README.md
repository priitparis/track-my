# Automatic tracking methods

This directory holds tracking methods that record location automatically,
without a manual button press. Methods are grouped by technique —
[api/](api/) for methods that call an official data API,
[scraper/](scraper/) for methods that read a public web page — and each
individual method gets its own subdirectory within its group, following
the same pattern as [../manual/](../manual/).

## Methods

- [scraper/myshiptracking/](scraper/myshiptracking/) — primary method.
  Scrapes the ship's MyShipTracking.com vessel page for its position
  hourly.
- [scraper/myshiptracking-events/](scraper/myshiptracking-events/) —
  scrapes MyShipTracking.com's separate event log (port arrivals/
  departures, start/stop moving) daily, appending only events not
  already recorded.
- [api/aisstream/](api/aisstream/) — secondary/backup method. Polls
  AISStream.io's AIS WebSocket API for the ship's position every 3
  hours (lower frequency, since it shares the same GitHub Actions
  minutes budget as the other methods — see each method's README for
  details).
