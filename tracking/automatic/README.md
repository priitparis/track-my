# Automatic tracking methods

This directory holds tracking methods that record location automatically,
without a manual button press. Methods are grouped by technique —
[api/](api/) for methods that call an official data API,
[scraper/](scraper/) for methods that read a public web page — and each
individual method gets its own subdirectory within its group, following
the same pattern as [../manual/](../manual/).

## Methods

- [scraper/position/](scraper/position/) — primary method. Every 30
  minutes, scrapes several public vessel-tracking sites
  (MyShipTracking.com, MarineRadar.com) for the ship's position and
  records the one reporting the freshest AIS fix.
- [scraper/myshiptracking-events/](scraper/myshiptracking-events/) —
  scrapes MyShipTracking.com's separate event log (port arrivals/
  departures, start/stop moving) daily, appending only events not
  already recorded.
- [api/aisstream/](api/aisstream/) — secondary/backup method. Polls
  AISStream.io's AIS WebSocket API for the ship's position every 3
  hours (lower frequency, since it shares the same GitHub Actions
  minutes budget as the other methods — see each method's README for
  details).
- [api/blog-locations/](api/blog-locations/) — a different kind of
  method: doesn't track live position at all, instead uses an LLM
  (Gemini) to extract the locations mentioned in the trip's own blog
  posts (RSS feed), daily.
