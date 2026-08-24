const SHEET_NAME = "Auto";
const SPREADSHEET_ID = "<your Google Sheet ID>"; // from its URL: /spreadsheets/d/<THIS_PART>/edit

function doGet(e) {
  return getGeoJSON();
}

// GeoJSON generator for uMap
function getGeoJSON() {
  const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();
  const features = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const lat = parseFloat(row[0]);
    const lon = parseFloat(row[1]);
    const time = row[2];

    if (!isNaN(lat) && !isNaN(lon)) {
      features.push({
        "type": "Feature",
        "geometry": {
          "type": "Point",
          "coordinates": [lon, lat]
        },
        "properties": {
          "time": time
        }
      });
    }
  }

  const geojson = {
    "type": "FeatureCollection",
    "features": features
  };

  return ContentService.createTextOutput(JSON.stringify(geojson))
                       .setMimeType(ContentService.MimeType.JSON);
}
