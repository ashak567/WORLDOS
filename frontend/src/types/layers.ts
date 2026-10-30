import { TruthClass } from '../api';

export type LayerId =
  | 'country-boundaries'
  | 'population-observations'
  | 'aircraft-states'
  | 'maritime-vessels'
  | 'space-satellites'
  | 'surveillance-cameras'
  | 'earthquake-events'
  | 'natural-hazards'
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
  feedStatus?: 'fresh' | 'stale' | 'partial' | 'unavailable';
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
    description: 'Stored OpenSky state-vector snapshots; age is shown and old coordinates are not extrapolated.',
    source: 'OpenSky Network · authenticated ingestion snapshots',
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
    description: 'Stored AIS positions; demo records are excluded. A free AISStream key is required for live vessel updates.',
    source: 'AISStream · live key required',
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
    description: 'Active CelesTrak catalog positions propagated from current orbital elements; selected satellite ground track is computed on demand.',
    source: 'CelesTrak Active GP Elements · SGP4',
    color: '#a855f7', // Purple
    enabled: true,
    count: 0,
    truthClass: 'DERIVED',
    loading: false,
  },
  {
    id: 'surveillance-cameras',
    name: 'Curated Camera Directory',
    category: 'surveillance',
    description: 'Static camera links and approximate locations; online status and worldwide coverage are not verified.',
    source: 'Curated examples · check each operator',
    color: '#10b981', // Emerald green
    enabled: false,
    count: 0,
    truthClass: 'SIMULATED',
    loading: false,
  },
  {
    id: 'earthquake-events',
    name: 'Seismic Events (USGS)',
    category: 'disasters',
    description: 'USGS magnitude 2.5+ earthquake events from the past 24 hours, including the publisher tsunami flag where present.',
    source: 'USGS Real-Time GeoJSON Feed',
    color: '#f97316', // Orange
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'natural-hazards',
    name: 'Global Hazards & Alerts',
    category: 'disasters',
    description: 'NASA EONET point events and track endpoints plus GDACS alerts, including cyclones, tsunami alerts, volcanoes, floods, and wildfires.',
    source: 'NASA EONET · GDACS',
    color: '#fb7185',
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'thermal-fires',
    name: 'Active Fires (NASA FIRMS)',
    category: 'disasters',
    description: 'NASA FIRMS satellite thermal anomalies with Fire Radiative Power and brightness; requires a free FIRMS map key. Keyless wildfire events are in Global Hazards & Alerts.',
    source: 'NASA FIRMS (VIIRS / MODIS) · key required',
    color: '#ef4444', // Red
    enabled: true,
    count: 0,
    truthClass: 'OBSERVED',
    loading: false,
  },
  {
    id: 'critical-infrastructure',
    name: 'Curated Infrastructure Examples',
    category: 'infrastructure',
    description: 'Small hand-curated list of airports, ports, and launch sites; not a live or complete registry.',
    source: 'WORLDOS sample directory · verify facility details',
    color: '#eab308', // Yellow
    enabled: false,
    count: 0,
    truthClass: 'SIMULATED',
    loading: false,
  },
  {
    id: 'anomalies',
    name: 'Flagged Observations',
    category: 'intelligence',
    description: 'Stored observations carrying an anomaly flag; detection runs and findings are not automatically included.',
    source: 'Stored observation flags',
    color: '#facc15', // Gold
    enabled: true,
    count: 0,
    truthClass: 'DERIVED',
    loading: false,
  },
  {
    id: 'system-alerts',
    name: 'Stored Rule Alerts',
    category: 'intelligence',
    description: 'Previously stored alert-engine results; these are not a live global warning feed.',
    source: 'WORLDOS alert rules · stored results',
    color: '#f43f5e', // Rose
    enabled: true,
    count: 0,
    truthClass: 'INFERRED',
    loading: false,
  },
];
