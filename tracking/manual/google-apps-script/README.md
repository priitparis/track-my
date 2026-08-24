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

- **Database**: Google Sheets (sheet name: `Location`, columns: `Lat`,
  `Lon`, `Time`).
- **Backend + Frontend**: Google Apps Script ([Code.gs](Code.gs) and
  [Index.html](Index.html)).
- **Map**: uMap (OpenStreetMap), which reads GeoJSON data from the
  [shared GeoJSON endpoint](../../google-apps-script/) — a separate Apps
  Script project that serves the `Location` tab (and every other
  tracking method's tab) as GeoJSON. This project itself is write-only:
  it never serves GeoJSON directly.

## Files

- [Code.gs](Code.gs) — serves the HTML page and saves incoming
  `{lat, lon, time}` data to the `Location` sheet. Read-side (GeoJSON for
  uMap) lives in the [shared endpoint](../../google-apps-script/) instead.
- [Index.html](Index.html) — the page shown to the user, with a button
  that reads the browser's geolocation and sends it to `Code.gs` via
  `google.script.run`.

## Links and setup

- **Web App URL** (for mobile use): `<your Web App URL>`
  Used to open the page in a phone browser and add it to the home screen.

For the uMap layer, deploy the [shared GeoJSON endpoint](../../google-apps-script/)
and use its Web App URL with `?sheet=Location` as the uMap Remote Data
URL (Format: GeoJSON) — see that project's README for setup.

Fill in the actual Web App URL above once this script is deployed.
