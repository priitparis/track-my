const SHEET_NAME = "Location"; // Veendu, et lehe nimi Google Sheetsis on "Location"

function doGet(e) {
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