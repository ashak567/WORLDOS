/// <reference types="vite/client" />

interface Window {
  CESIUM_BASE_URL?: string;
}

declare namespace GeoJSON {
  type Geometry = { type: string; coordinates: unknown };
}
