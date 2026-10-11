// UNTESTED RN glue. Release builds MUST use an https:// API_BASE (SRS 14).
// Debug: reach the laptop API from an emulator OR a USB phone with `adb reverse tcp:8000 tcp:8000` (see docs/DEVICE_TEST.md).
export const API_BASE = __DEV__ ? 'http://localhost:8000' : 'https://REPLACE-WITH-YOUR-HTTPS-API-DOMAIN';
// Demo coordinates inside the fictional-station catchment (fixture); users can enter their own locality in Settings.
export const DEMO_LOCATION = { lat: 26.15, lon: 85.9 };
// Map tiles: tile.openstreetmap.org forbids bulk/offline prefetching. Use your own tile server or a licensed provider for offline packs.
export const MAP_STYLE_URL = 'https://REPLACE-WITH-YOUR-STYLE-JSON-URL';
