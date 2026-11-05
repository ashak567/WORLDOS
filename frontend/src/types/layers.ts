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
  | 'thermal-fires';

export type LayerCategory =
  | 'geography'
  | 'aviation'
  | 'maritime'
  | 'space'
  | 'surveillance'
  | 'disasters';

export type BasemapMode = 'dark-tactical' | 'satellite-hybrid' | 'streets' | 'oceanic' | 'google-3d';

export interface SelectedItemPayload {
  type:
    | 'geometry'
    | 'event'
    | 'observation'
    | 'alert'
    | 'aircraft'
    | 'vessel'
    | 'satellite'
    | 'camera'
    | 'fire'
    | 'infrastructure'
    | 'place';
  data: any;
}

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
    color: '#ff1744', // Neon Red
    enabled: true,
    count: 0,
    truthClass: 'DERIVED',
    loading: false,
  },
  {
    id: 'surveillance-cameras',
    name: 'Street & Traffic Cameras',
    category: 'surveillance',
    description: 'Real-time global street & traffic camera network with 24/7 YouTube live streams and municipal feeds.',
    source: 'Global Street & Traffic Cameras · YouTube 24/7 Live',
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
];
