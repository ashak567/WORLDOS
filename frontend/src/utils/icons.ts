/**
 * Vector SVG Data URLs for Heading-Aware Tactical Rendering in 2D (Deck.gl) and 3D (CesiumJS).
 * Designed for crisp high-DPI rendering without external asset dependencies.
 */

// Helper to create colored SVGs
function createSvgDataUrl(svgContent: string, fillColorHex: string): string {
  const fullSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="32" height="32" fill="${fillColorHex}">${svgContent}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(fullSvg)}`;
}

// 1. Aircraft (Jet / Airplane) - Divided into Commercial, Military, and Private
// Commercial Airliner (Swept wings, long passenger fuselage, twin turbines)
const AIRPLANE_PATH_COMMERCIAL = `<path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>`;

// Military Fighter / Interceptor (Aggressive delta-wing stealth fighter silhouette)
const AIRPLANE_PATH_MILITARY = `<path d="M12 2L9 8l-6 5 2 1.5 5-1.5V17l-3 2v2l5-1.5 5 1.5v-2l-3-2v-4l5 1.5 2-1.5-6-5-3-6z"/>`;

// Private & Executive Jet (Twin-engine business jet with tapered swept wings)
const AIRPLANE_PATH_PRIVATE = `<path d="M12 3c-.55 0-1 .45-1 1v5.5L4 13v1.5l7-2v4l-2 1.5v1.5l3-.8 3 .8v-1.5L13 16.5v-4l7 2V13l-7-3.5V4c0-.55-.45-1-1-1z"/>`;

export const AIRPLANE_ICON_COMMERCIAL = createSvgDataUrl(AIRPLANE_PATH_COMMERCIAL, '#38bdf8');
export const AIRPLANE_ICON_MILITARY = createSvgDataUrl(AIRPLANE_PATH_MILITARY, '#f59e0b');
export const AIRPLANE_ICON_PRIVATE = createSvgDataUrl(AIRPLANE_PATH_PRIVATE, '#10b981');

export const AIRPLANE_ICON_BLUE = AIRPLANE_ICON_COMMERCIAL;
export const AIRPLANE_ICON_AMBER = AIRPLANE_ICON_MILITARY;
export const AIRPLANE_ICON_INTERNATIONAL = AIRPLANE_ICON_COMMERCIAL;
export const AIRPLANE_ICON_DOMESTIC = AIRPLANE_ICON_PRIVATE;
export const AIRPLANE_ICON_GROUND = createSvgDataUrl(AIRPLANE_PATH_COMMERCIAL, '#94a3b8');
export const AIRPLANE_ICON_WHITE = createSvgDataUrl(AIRPLANE_PATH_COMMERCIAL, '#ffffff');

// 2. Maritime Vessel (Ship)
const VESSEL_PATH = `<path d="M12 2L4 9v7l8 6 8-6V9l-8-7zm0 3.5l5 4.38v4.24l-5 3.75-5-3.75V9.88l5-4.38z"/>`;
export const VESSEL_ICON_CYAN = createSvgDataUrl(VESSEL_PATH, '#06b6d4');
export const VESSEL_ICON_WHITE = createSvgDataUrl(VESSEL_PATH, '#ffffff');

// 3. Satellite (Orbital Solar Array + Directional Tangent Velocity Vector)
// Combines authentic dual photovoltaic solar wings with a forward velocity vector arrow
function createSatelliteHybridSvg(wingColorHex: string): string {
  const cleanId = wingColorHex.replace('#', '');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="40" height="40">
  <defs>
    <filter id="satglow_${cleanId}" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="0" stdDeviation="1.5" flood-color="${wingColorHex}" flood-opacity="0.8"/>
    </filter>
  </defs>
  <!-- Forward Directional Velocity Vector Arrow (Tangential Orbital Motion) -->
  <path d="M20 2 L24 9 L20 7.5 L16 9 Z" fill="${wingColorHex}" opacity="0.95"/>
  <line x1="20" y1="7.5" x2="20" y2="13" stroke="${wingColorHex}" stroke-width="1.5" stroke-dasharray="2,1.5" opacity="0.8"/>
  <!-- Left Solar Array Wing -->
  <rect x="2" y="16" width="12" height="8" rx="1" fill="${wingColorHex}" stroke="#ffffff" stroke-width="0.8" filter="url(#satglow_${cleanId})"/>
  <line x1="6" y1="16" x2="6" y2="24" stroke="#ffffff" stroke-width="0.6" opacity="0.7"/>
  <line x1="10" y1="16" x2="10" y2="24" stroke="#ffffff" stroke-width="0.6" opacity="0.7"/>
  <line x1="2" y1="20" x2="14" y2="20" stroke="#ffffff" stroke-width="0.6" opacity="0.7"/>
  <!-- Wing Boom Mount Left -->
  <line x1="14" y1="20" x2="16" y2="20" stroke="#ffffff" stroke-width="1.8"/>
  <!-- Right Solar Array Wing -->
  <rect x="26" y="16" width="12" height="8" rx="1" fill="${wingColorHex}" stroke="#ffffff" stroke-width="0.8" filter="url(#satglow_${cleanId})"/>
  <line x1="30" y1="16" x2="30" y2="24" stroke="#ffffff" stroke-width="0.6" opacity="0.7"/>
  <line x1="34" y1="16" x2="34" y2="24" stroke="#ffffff" stroke-width="0.6" opacity="0.7"/>
  <line x1="26" y1="20" x2="38" y2="20" stroke="#ffffff" stroke-width="0.6" opacity="0.7"/>
  <!-- Wing Boom Mount Right -->
  <line x1="24" y1="20" x2="26" y2="20" stroke="#ffffff" stroke-width="1.8"/>
  <!-- Central Satellite Avionics Bus -->
  <rect x="16" y="15" width="8" height="10" rx="1.5" fill="#f8fafc" stroke="${wingColorHex}" stroke-width="1.2"/>
  <circle cx="20" cy="20" r="2.2" fill="${wingColorHex}"/>
  <!-- Parabolic Communication Antenna Dish -->
  <path d="M17.5 28 C17.5 25.5, 22.5 25.5, 22.5 28" fill="none" stroke="#f8fafc" stroke-width="1.4" stroke-linecap="round"/>
  <line x1="20" y1="25" x2="20" y2="28" stroke="#f8fafc" stroke-width="1.2"/>
</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

// Low Earth Orbit (LEO, 200 - 2,000 km, Starlink / ISS / Earth Observation) - Electric Cyan
export const SATELLITE_ICON_LEO = createSatelliteHybridSvg('#00e5ff');

// Medium Earth Orbit (MEO, 2,000 - 30,000 km, GPS / Galileo / Navigation) - Amber Gold
export const SATELLITE_ICON_MEO = createSatelliteHybridSvg('#fbbf24');

// Geostationary Orbit (GEO, > 30,000 km, Weather & Telecom) - Emerald Green
export const SATELLITE_ICON_GEO = createSatelliteHybridSvg('#10b981');

// Lunar & Cislunar Spacecraft - Deep Space Rose
export const SATELLITE_ICON_LUNAR = createSatelliteHybridSvg('#f43f5e');

export const SATELLITE_ICON_CYAN = SATELLITE_ICON_LEO;
export const SATELLITE_ICON_NEON_RED = SATELLITE_ICON_LEO; // Deprecated neon red alias mapped to Electric Cyan
export const SATELLITE_ICON_PURPLE = SATELLITE_ICON_MEO;
export const SATELLITE_ICON_WHITE = createSatelliteHybridSvg('#ffffff');

// 4. Surveillance / Traffic Camera
const CAMERA_PATH = `<path d="M12 15c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3zm0-4c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm9-2h-3.17l-1.83-2H8L6.17 9H3c-1.1 0-2 .9-2 2v9c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2v-9c0-1.1-.9-2-2-2zm0 11H3v-9h3.83l1.83-2h6.68l1.83 2H21v9z"/>`;
export const CAMERA_ICON_EMERALD = createSvgDataUrl(CAMERA_PATH, '#10b981');

// 5. Thermal Anomaly / Wildfire (Flame)
const FIRE_PATH = `<path d="M12 2C8.13 4.57 6 8.65 6 13c0 3.31 2.69 6 6 6s6-2.69 6-6c0-4.35-2.13-8.43-6-11zm0 15c-1.66 0-3-1.34-3-3 0-1.57.88-3.08 2.25-3.83.39-.21.84.07.84.51v1.5c0 .83.67 1.5 1.5 1.5.44 0 .72.45.51.84A2.99 2.99 0 0 1 12 17z"/>`;
export const FIRE_ICON_ORANGE = createSvgDataUrl(FIRE_PATH, '#f97316');
export const FIRE_ICON_RED = createSvgDataUrl(FIRE_PATH, '#ef4444');

// 6. Airport Hub
const AIRPORT_PATH = `<path d="M22 16v-2l-8.5-5V3.5c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5V9L2 14v2l8.5-2.5V19L8 20.5V22l4-1 4 1v-1.5L13.5 19v-5.5L22 16z"/>`;
export const AIRPORT_ICON_BLUE = createSvgDataUrl(AIRPORT_PATH, '#60a5fa');

// 7. Deep-Water Port
const PORT_PATH = `<path d="M12 2c1.1 0 2 .9 2 2 0 .74-.4 1.38-1 1.72V7h4c1.1 0 2 .9 2 2v2h-2V9h-4v10.18c2.4-.41 4.38-2.12 4.88-4.48l1.96.42C21.14 20.31 17.02 23 12 23s-9.14-2.69-9.84-5.88l1.96-.42c.5 2.36 2.48 4.07 4.88 4.48V9H5v2H3V9c0-1.1.9-2 2-2h4V5.72C8.4 5.38 8 4.74 8 4c0-1.1.9-2 2-2zm0 2c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z"/>`;
export const PORT_ICON_TEAL = createSvgDataUrl(PORT_PATH, '#14b8a6');

// 8. Spaceport / Launch Facility (Rocket)
const SPACEPORT_PATH = `<path d="M13.13 22.19l-1.63-3.83c1.57-.58 3.04-1.5 4.31-2.77l2.55 3.32c-.57.88-1.28 1.68-2.11 2.37l-3.12.91zm-2.26 0l-3.12-.91c-.83-.69-1.54-1.49-2.11-2.37l2.55-3.32c1.27 1.27 2.74 2.19 4.31 2.77l-1.63 3.83zM12 2c3.5 3.5 5 7.5 5 12H7c0-4.5 1.5-8.5 5-12zm0 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>`;
export const SPACEPORT_ICON_ROSE = createSvgDataUrl(SPACEPORT_PATH, '#f43f5e');

// 9. Multimodal Places & Stays
const HOTEL_PATH = `<path d="M7 13c1.66 0 3-1.34 3-3S8.66 7 7 7s-3 1.34-3 3 1.34 3 3 3zm12-6h-8v7H3V5H1v15h2v-3h18v3h2v-9c0-2.21-1.79-4-4-4z"/>`;
export const HOTEL_ICON_GOLD = createSvgDataUrl(HOTEL_PATH, '#eab308');

const DINING_PATH = `<path d="M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h2.5v-9.03C11.34 12.84 13 11.12 13 9V2h-2v7zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z"/>`;
export const DINING_ICON_ROSE = createSvgDataUrl(DINING_PATH, '#f43f5e');

const SCENERY_PATH = `<path d="M14 6l-3.75 5 2.85 3.8-1.6 1.2L7 10l-6 8h22L14 6z"/>`;
export const SCENERY_ICON_EMERALD = createSvgDataUrl(SCENERY_PATH, '#10b981');

const NIGHTLIFE_PATH = `<path d="M21 5V3H3v2l8 9v5H6v2h12v-2h-5v-5l8-9zM7.43 7L5.66 5h12.69l-1.78 2H7.43z"/>`;
export const NIGHTLIFE_ICON_PURPLE = createSvgDataUrl(NIGHTLIFE_PATH, '#a855f7');

// 10. High-Contrast Pinpoint Location Markers (Pin with needle pointing directly to ground coordinates)
function createPinpointSvg(pinColorHex: string, innerIconPath: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 48" width="36" height="48">
    <defs>
      <filter id="pindrop" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000000" flood-opacity="0.85"/>
      </filter>
    </defs>
    <!-- Outer teardrop pin body -->
    <path d="M18 2C9.72 2 3 8.72 3 17c0 10.5 15 29 15 29s15-18.5 15-29c0-8.28-6.72-15-15-15z" fill="${pinColorHex}" stroke="#ffffff" stroke-width="2.5" filter="url(#pindrop)"/>
    <!-- Inner contrast disk -->
    <circle cx="18" cy="17" r="9" fill="#0a0f1d"/>
    <!-- Centered category icon scaled inside disk -->
    <g transform="translate(10, 9) scale(0.65)" fill="${pinColorHex}">
      ${innerIconPath}
    </g>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const MAP_PIN_STAYS_GOLD = createPinpointSvg('#eab308', HOTEL_PATH);
export const MAP_PIN_DINING_ROSE = createPinpointSvg('#f43f5e', DINING_PATH);
export const MAP_PIN_SCENERY_EMERALD = createPinpointSvg('#10b981', SCENERY_PATH);
export const MAP_PIN_NIGHTLIFE_PURPLE = createPinpointSvg('#a855f7', NIGHTLIFE_PATH);

export const MAP_PIN_SELECTED_GLOW = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 56" width="44" height="56">
  <defs>
    <filter id="goldglow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <path d="M22 3C11.5 3 3 11.5 3 22c0 13.5 19 31 19 31s19-17.5 19-31c0-10.5-8.5-19-19-19z" fill="%23facc15" stroke="%23ffffff" stroke-width="3" filter="url(%23goldglow)"/>
  <circle cx="22" cy="22" r="11" fill="%23050810"/>
  <circle cx="22" cy="22" r="6.5" fill="%23facc15"/>
</svg>`;
