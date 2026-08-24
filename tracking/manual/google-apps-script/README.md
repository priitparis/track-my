# Google Apps Script location tracker

A manual, button-triggered location tracking method: the user opens a web
page on their phone, taps a button, and the current GPS coordinates are
saved. This method is general-purpose (not ship-specific) and happens to be
used for ship tracking today.

This directory is a documentation copy of code that actually runs in
Google's environment (Apps Script + Sheets), not a deploy source. To update
the live version, edit the script directly in the Google Apps Script
editor and keep this copy in sync.

## Architecture

- **Database**: Google Sheets (sheet name: `location`, columns: `Lat`,
  `Lon`, `Time`).
- **Backend + Frontend**: Google Apps Script ([Code.gs](Code.gs) and
  [Index.html](Index.html)).
- **Map**: uMap (OpenStreetMap), which reads GeoJSON data served by the
  Apps Script.

## Files

- [Code.gs](Code.gs) — serves the HTML page, saves incoming
  `{lat, lon, time}` data to the `location` sheet, and generates a GeoJSON
  feed (`?format=geojson`) for uMap.
- [Index.html](Index.html) — the page shown to the user, with a button
  that reads the browser's geolocation and sends it to `Code.gs` via
  `google.script.run`.

## Links and setup

- **Web App URL** (for mobile use): `<your Web App URL>`
  Used to open the page in a phone browser and add it to the home screen.
- **uMap Remote Data URL** (for the map): `<your Web App URL>?format=geojson`
  Set in the uMap layer settings under Remote Data, with Format: GeoJSON.

Fill in the actual URLs above once the script is deployed as a web app.
