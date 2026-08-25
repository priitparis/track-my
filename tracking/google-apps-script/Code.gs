const SPREADSHEET_ID = "<your Google Sheet ID>"; // from its URL: /spreadsheets/d/<THIS_PART>/edit

// Sheet tabs this endpoint is allowed to serve, keyed by the ?sheet= value.
const ALLOWED_SHEETS = ["Location", "Auto", "Scraper", "Events", "Blog"];

// uMap-recognized style property, applied to the route LineString so it
// renders dashed instead of solid by default.
const LINE_DASH_ARRAY = "5,5";

function doGet(e) {
  const sheetName = e && e.parameter && e.parameter.sheet;
  const latestOnly = !!(e && e.parameter && e.parameter.latest);
  const excludeLatest = !!(e && e.parameter && e.parameter.exclude_latest);
  const lineParam = e && e.parameter && e.parameter.line;
  const includeLine = lineParam === "1" || lineParam === "only";
  const includePoints = lineParam !== "only";
  const groupFilter = e && e.parameter && e.parameter.group;

  if (!sheetName || ALLOWED_SHEETS.indexOf(sheetName) === -1) {
    return ContentService.createTextOutput(
      "Missing or unknown ?sheet= parameter. Allowed values: " + ALLOWED_SHEETS.join(", ")
    ).setMimeType(ContentService.MimeType.TEXT);
  }

  return getGeoJSON(sheetName, latestOnly, excludeLatest, includeLine, includePoints, groupFilter);
}

// GeoJSON generator for uMap, for any of the allowed sheet tabs.
// - latestOnly: only the most recent valid point is included.
// - excludeLatest: every point EXCEPT the most recent one is included
//   (ignored if latestOnly is also set, since latestOnly is more
//   specific and wins).
// - includeLine: adds a LineString Feature connecting all points, in
//   order, as the ship's route (ignored together with latestOnly, since
//   a line needs more than one point).
// - includePoints: whether the individual Point Features are included
//   at all (false when ?line=only is requested).
// - groupFilter: if set, only points whose "group_id" column (only
//   present on some sheets, e.g. Blog) matches this value are included —
//   lets one sheet hold multiple trips/voyages and serve just one at a
//   time via ?group=.
function getGeoJSON(sheetName, latestOnly, excludeLatest, includeLine, includePoints, groupFilter) {
  const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName(sheetName);
  const data = sheet.getDataRange().getValues();
  const points = [];

  // Columns beyond Lat/Lon/Time vary per sheet (e.g. Events has Event/
  // Port/Country/Speed/Course, Scraper has speed/course/weather/trip
  // fields) — read the header row so any extra column becomes a GeoJSON
  // property automatically, by its own header name, instead of relying
  // on fixed column positions that would only match one sheet's layout.
  const headers = data.length > 0 ? data[0] : [];
  const groupColumn = headers.indexOf("group_id");

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const lat = parseFloat(row[0]);
    const lon = parseFloat(row[1]);
    const time = row[2];

    if (groupFilter && groupColumn !== -1 && String(row[groupColumn]) !== String(groupFilter)) {
      continue;
    }

    if (!isNaN(lat) && !isNaN(lon)) {
      const extra = {};
      for (let c = 3; c < row.length; c++) {
        const header = headers[c];
        if (header && row[c] !== "" && row[c] !== undefined && row[c] !== null) {
          extra[header] = row[c];
        }
      }
      points.push({ lat: lat, lon: lon, time: time, extra: extra });
    }
  }

  let pointsToUse = points;
  if (latestOnly) {
    pointsToUse = points.slice(-1);
  } else if (excludeLatest) {
    pointsToUse = points.slice(0, -1);
  }
  const features = [];

  if (includePoints) {
    pointsToUse.forEach(function (p) {
      const properties = { "time": p.time };
      for (const key in p.extra) {
        properties[key] = p.extra[key];
      }

      features.push({
        "type": "Feature",
        "geometry": {
          "type": "Point",
          "coordinates": [p.lon, p.lat]
        },
        "properties": properties
      });
    });
  }

  if (includeLine && !latestOnly && pointsToUse.length > 1) {
    features.push({
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": pointsToUse.map(function (p) { return [p.lon, p.lat]; })
      },
      "properties": {
        "dashArray": LINE_DASH_ARRAY
      }
    });
  }

  const geojson = {
    "type": "FeatureCollection",
    "features": features
  };

  return ContentService.createTextOutput(JSON.stringify(geojson))
                       .setMimeType(ContentService.MimeType.JSON);
}
