import { TruthClass } from '../api';

export type LayerId =
  | 'country-boundaries'
  | 'population-observations'
  | 'aircraft-states'
  | 'maritime-vessels'
  | 'space-satellites'
  | 'surveillance-cameras'
  | 'earthquake-events'
  | 'thermal-fires'
  | 'critical-infrastructure'
  | 'anomalies'
  | 'system-alerts';

export type LayerCategory =
  | 'geography'
  | 'aviation'
  | 'maritime'
  | 'space'
  | 'surveillance'
  | 'disasters'
  | 'infrastructure'
  | 'intelligence';

export type BasemapMode = 'dark-tactical' | 'satellite-hybrid' | 'oceanic';

export interface LayerDefinition {
  id: LayerId;
  name: string;
  category: LayerCategory;
  description: string;
  source: string;
  color: string;
  enabled: boolean;
  count: number;
  lastUpdated?: string;
  truthClass: TruthClass;
  loading: boolean;
  error?: string;
}

export const INITIAL_LAYERS: LayerDefinition[] = [
  {
    id: 'country-boundaries',
    name: 'Sovereign Boundaries',
    category: 'geography',
    description: 'PostGIS global sovereign state and territorial boundaries.',
    source: 'Natural Earth v5.1.2 / PostGIS',
    color: '#3d8bff', // Blue
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'population-observations',
    name: 'Demographic Densities',
    category: 'geography',
    description: 'Sovereign and regional population metrics and historical census series.',
    source: 'World Bank Open Data (SP.POP.TOTL)',
    color: '#2bf0c8', // Cyan green
    enabled: false,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'aircraft-states',
    name: 'Aircraft (ADS-B)',
    category: 'aviation',
    description: 'Live aircraft state vectors, callsigns, altitudes, velocities, headings, and transponder coordinates.',
    source: 'OpenSky Network Association',
    color: '#38bdf8', // Sky blue
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'maritime-vessels',
    name: 'Maritime Vessels (AIS)',
    category: 'maritime',
    description: 'Class A transponder telemetry across international maritime trade corridors, choke points, and EEZs.',
    source: 'Global AIS / UN-IMO Transponder Protocol',
    color: '#06b6d4', // Cyan
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'space-satellites',
    name: 'Satellites & Orbit Tracks',
    category: 'space',
    description: 'Active orbital assets, Keplerian SGP4 propagation ephemeris, and 360° predicted ground tracks.',
    source: 'CelesTrak / NORAD Ephemeris',
    color: '#a855f7', // Purple
    enabled: true,
    count: 0,
    truthClass: 'DERIVED',
    loading: false,
  },
  {
    id: 'surveillance-cameras',
    name: 'DOT & Sensor Feeds',
    category: 'surveillance',
    description: 'Public transportation department CCTV cameras and geological observatory optical nodes.',
    source: 'Caltrans / NYSDOT 511 / TfL / USGS',
    color: '#10b981', // Emerald green
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'earthquake-events',
    name: 'Seismic Events (USGS)',
    category: 'disasters',
    description: 'Real-time seismic activity, epicenter coordinates, depths, and magnitude observations.',
    source: 'USGS Earthquake Hazards API',
    color: '#f97316', // Orange
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'thermal-fires',
    name: 'Active Fires (NASA FIRMS)',
    category: 'disasters',
    description: 'Near-real-time satellite thermal anomaly detections, Fire Radiative Power (MW), and brightness.',
    source: 'NASA FIRMS (VIIRS / MODIS)',
    color: '#ef4444', // Red
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'critical-infrastructure',
    name: 'Strategic Infrastructure',
    category: 'infrastructure',
    description: 'International hub airports, deep-water container ports, and global orbital spaceports.',
    source: 'ICAO / IMO / Space Agency Registries',
    color: '#eab308', // Yellow
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'anomalies',
    name: 'Cross-Domain Anomalies',
    category: 'intelligence',
    description: 'Statistical deviations and cross-domain anomalies computed across observation series.',
    source: 'Engine 8 / Anomaly Detection Bus',
    color: '#facc15', // Gold
    enabled: true,
    count: 0,
    truthClass: 'DERIVED',
    loading: false,
  },
  {
    id: 'system-alerts',
    name: 'Tactical Alerts',
    category: 'intelligence',
    description: 'High-severity system warnings, threshold breaches, and intelligence flags.',
    source: 'WORLDOS Alert Dispatcher',
    color: '#f43f5e', // Rose
    enabled: true,
    count: 0,
    truthClass: 'INFERRED',
    loading: false,
  },
];
