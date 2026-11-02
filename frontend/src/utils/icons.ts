/**
 * Vector SVG Data URLs for Heading-Aware Tactical Rendering in 2D (Deck.gl) and 3D (CesiumJS).
 * Designed for crisp high-DPI rendering without external asset dependencies.
 */

// Helper to create colored SVGs
function createSvgDataUrl(svgContent: string, fillColorHex: string): string {
  const encodedColor = encodeURIComponent(fillColorHex);
  const fullSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="32" height="32" fill="${encodedColor}">${svgContent}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(fullSvg)}`;
}

// 1. Aircraft (Jet / Airplane)
const AIRPLANE_PATH = `<path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>`;
export const AIRPLANE_ICON_BLUE = createSvgDataUrl(AIRPLANE_PATH, '#38bdf8');
export const AIRPLANE_ICON_GROUND = createSvgDataUrl(AIRPLANE_PATH, '#94a3b8');
export const AIRPLANE_ICON_WHITE = createSvgDataUrl(AIRPLANE_PATH, '#ffffff');

// 2. Maritime Vessel (Ship)
const VESSEL_PATH = `<path d="M12 2L4 9v7l8 6 8-6V9l-8-7zm0 3.5l5 4.38v4.24l-5 3.75-5-3.75V9.88l5-4.38z"/>`;
export const VESSEL_ICON_CYAN = createSvgDataUrl(VESSEL_PATH, '#06b6d4');
export const VESSEL_ICON_WHITE = createSvgDataUrl(VESSEL_PATH, '#ffffff');

// 3. Satellite (Orbital Solar Array) - Glowing Neon Red Space Beacon
const SATELLITE_PATH = `<circle cx="12" cy="12" r="3.5"/><path d="M4 10h3v4H4zm13 0h3v4h-3zM10 4h4v3h-4zm0 13h4v3h-4zM2 11h2v2H2zm18 0h2v2h-2zM11 2h2v2h-2zm0 18h2v2h-2z"/>`;
export const SATELLITE_ICON_NEON_RED = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32"><defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur in="SourceGraphic" stdDeviation="1.8" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><circle cx="16" cy="16" r="12" fill="%23ff003b" fill-opacity="0.28"/><circle cx="16" cy="16" r="10" fill="none" stroke="%23ff003b" stroke-width="1.8" filter="url(%23glow)"/><circle cx="16" cy="16" r="5.5" fill="%23ff1744" filter="url(%23glow)"/><circle cx="16" cy="16" r="2.5" fill="%23ffffff"/><line x1="16" y1="2" x2="16" y2="8" stroke="%23ff1744" stroke-width="2.5" stroke-linecap="round"/><line x1="16" y1="24" x2="16" y2="30" stroke="%23ff1744" stroke-width="2.5" stroke-linecap="round"/><line x1="2" y1="16" x2="8" y2="16" stroke="%23ff1744" stroke-width="2.5" stroke-linecap="round"/><line x1="24" y1="16" x2="30" y2="16" stroke="%23ff1744" stroke-width="2.5" stroke-linecap="round"/></svg>`;
export const SATELLITE_ICON_PURPLE = SATELLITE_ICON_NEON_RED;
export const SATELLITE_ICON_WHITE = createSvgDataUrl(SATELLITE_PATH, '#ffffff');

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
