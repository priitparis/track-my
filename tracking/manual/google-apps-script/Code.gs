const SHEET_NAME = "location"; // Veendu, et lehe nimi Google Sheetsis on "location"

function doGet(e) {
  // Kui uMap küsib GeoJSON andmeid (?format=geojson)
  if (e && e.parameter && e.parameter.format === "geojson") {
    return getGeoJSON();
  }
  
  // Serveerib HTML-lehte
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Saada asukoht')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// Funktsioon, mida HTML-i JavaScript kutsub otse välja
function saveData(data) {
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    
    const lat = data.lat;
    const lon = data.lon;
    const time = data.time || new Date().toISOString(); 
    
    sheet.appendRow([lat, lon, time]);
    
    return { status: "success" };
  } catch (error) {
    return { status: "error", message: error.toString() };
  }
}

// uMapi GeoJSON generaator
function getGeoJSON() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
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