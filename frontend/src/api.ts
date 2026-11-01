export type TruthClass = "OBSERVED" | "DERIVED" | "INFERRED" | "PREDICTED" | "SIMULATED";

export type BoundingBox = {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
};

export type Observation = {
  id?: string;
  observation_id?: string;
  entity_id: string;
  canonical_name?: string;
  measure?: string;
  metric_name?: string;
  value?: number;
  value_numeric?: number;
  unit?: string;
  starts_at: string;
  ends_at?: string;
  observed_at?: string;
  truth_class?: TruthClass;
  confidence?: number;
  evidence_locator?: string;
  evidence_id?: string;
  point?: [number, number];
  coordinates?: [number, number];
  is_anomaly?: boolean;
  anomaly_score?: number;
  source_slug?: string;
  source_name?: string;
  evidence_content_hash?: string;
  properties?: Record<string, any>;
};

export type GeometryFeature = {
  id: string;
  entity_id: string;
  canonical_name: string;
  geometry_kind: string;
  geometry: GeoJSON.Geometry;
  evidence_id?: string;
  source_slug?: string;
  properties?: Record<string, any>;
};

export type EvidenceCitation = {
  evidence_id: string;
  source_id: string;
  source_slug: string;
  source_name: string;
  locator: string;
  retrieved_at: string;
  content_hash?: string | null;
  excerpt?: string | null;
};

export type Event = {
  id: string;
  event_id?: string;
  canonical_name?: string;
  title?: string;
  event_type?: string;
  kind?: string;
  category?: string;
  starts_at?: string;
  ends_at?: string;
  occurred_at?: string;
  time_precision?: string;
  magnitude?: number;
  confidence?: number;
  truth_class?: TruthClass;
  evidence_id?: string;
  evidence_locator?: string;
  evidence_content_hash?: string;
  attributes?: Record<string, any>;
  properties?: Record<string, any>;
  geometry?: GeoJSON.Geometry;
  coordinates?: [number, number]; // [longitude, latitude]
  point?: [number, number];
  source_slug?: string;
  source_name?: string;
};

export type LiveEventsResponse = {
  earthquakes: Event[];
  natural_events: Event[];
  sources: Record<string, { status: 'fresh' | 'stale' | 'unavailable'; retrieved_at?: string; count: number; error?: string }>;
  as_of: string;
};

export type LiveContextResponse = {
  news: Array<{ title: string; url: string; domain: string; published_at: string; language: string; source_country: string }>;
  climate: null | { period: string; global_temperature_anomaly_c: number; unit: string; baseline: string; measure: string; source: string; source_url: string; truth_class: TruthClass; cadence: string };
  sources: Record<string, { status: 'fresh' | 'stale' | 'unavailable'; retrieved_at?: string; count: number; error?: string }>;
  as_of: string;
};

export type AssistantContext = {
  selected_entity_id?: string;
  map_bounds?: BoundingBox;
  travel_preferences?: { pace?: 'relaxed' | 'balanced' | 'packed'; photo_interest?: string };
};

export type AssistantMapContext = {
  evidence: Array<{ evidence_id: string; source_name: string; retrieved_at: string }>;
  [key: string]: unknown;
};

export type AssistantAction = {
  type: 'set_layer_visibility';
  layer_id: string;
  visible: boolean;
};

export type AircraftState = {
  id: string;
  observation_id?: string;
  entity_id: string;
  canonical_name: string;
  measure?: string;
  value?: number;
  unit?: string;
  truth_class: TruthClass;
  observed_at: string;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Geometry;
  evidence_locator?: string;
  evidence_content_hash?: string;
  source_slug: string;
  source_name: string;
  confidence?: number;
  attributes: {
    icao24?: string;
    callsign?: string | null;
    origin_country?: string;
    baro_altitude?: number | null;
    geo_altitude?: number | null;
    velocity?: number | null;
    true_track?: number | null;
    vertical_rate?: number | null;
    on_ground?: boolean | null;
    squawk?: string | null;
    position_source?: number;
    category?: number | null;
  };
};

export type VesselState = {
  id?: string;
  observation_id?: string;
  entity_id: string;
  canonical_name: string;
  measure?: string;
  value?: number; // sog_knots
  unit?: string;
  truth_class: TruthClass;
  observed_at: string;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Geometry;
  evidence_locator?: string;
  evidence_content_hash?: string;
  source_slug: string;
  source_name: string;
  confidence?: number;
  attributes: {
    mmsi: string;
    imo?: string | null;
    callsign?: string | null;
    flag: string;
    ship_type: string;
    sog_knots: number;
    cog_degrees?: number | null;
    heading_degrees?: number | null;
    draft_meters?: number | null;
    destination: string;
    eta?: string | null;
    nav_status: string;
  };
};

export type SatelliteState = {
  id?: string;
  observation_id?: string;
  entity_id: string;
  canonical_name: string;
  measure?: string;
  value?: number; // altitude_km
  unit?: string;
  truth_class: TruthClass;
  observed_at: string;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Geometry;
  evidence_locator?: string;
  evidence_content_hash?: string;
  source_slug: string;
  source_name: string;
  confidence?: number;
  attributes: {
    norad_id: string;
    designator: string;
    category: string;
    operator: string;
    launch_date?: string;
    altitude_km: number;
    velocity_kms: number;
    apogee_km: number;
    perigee_km: number;
    inclination_deg: number;
    period_min: number;
    eccentricity: number;
    ground_track?: [number, number][];
    calculation_method?: string;
    derivation_class?: string;
    element_set_status?: 'fresh' | 'stale' | 'sample';
    elements_retrieved_at?: string;
    elements_epoch?: string;
    elements_age_hours?: number;
    position_calculated_at?: string;
  };
};

export type CameraEntity = {
  id?: string;
  observation_id?: string;
  entity_id: string;
  canonical_name: string;
  measure?: string;
  value?: number;
  unit?: string;
  truth_class: TruthClass;
  observed_at: string;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Geometry;
  evidence_locator?: string;
  evidence_content_hash?: string;
  source_slug: string;
  source_name: string;
  confidence?: number;
  attributes: {
    camera_id: string;
    region: string;
    operator: string;
    status: string;
    stream_type: string;
    snapshot_url: string;
    stream_url: string;
    view_direction: string;
    resolution: string;
  };
};

export type ThermalAnomalyEvent = {
  id?: string;
  observation_id?: string;
  entity_id: string;
  canonical_name: string;
  measure?: string;
  value?: number; // FRP in MW
  unit?: string;
  truth_class: TruthClass;
  observed_at: string;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Geometry;
  evidence_locator?: string;
  evidence_content_hash?: string;
  source_slug: string;
  source_name: string;
  confidence?: number;
  attributes: {
    fire_id: string;
    region: string;
    brightness_kelvin: number;
    frp_mw: number;
    confidence_level: string;
    satellite: string;
    instrument: string;
    daynight: string;
  };
};

export type InfrastructureNode = {
  id?: string;
  observation_id?: string;
  entity_id: string;
  canonical_name: string;
  measure?: string;
  value?: number;
  unit?: string;
  truth_class: TruthClass;
  observed_at: string;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Geometry;
  evidence_locator?: string;
  evidence_content_hash?: string;
  source_slug: string;
  source_name: string;
  confidence?: number;
  attributes: {
    node_id: string;
    node_type: "airport" | "port" | "spaceport";
    country: string;
    elevation_m: number;
    operator: string;
    status: string;
    primary_code: string;
    secondary_code?: string | null;
    capabilities: string[];
  };
};

export type AircraftTrackPoint = {
  observation_id: string;
  entity_id: string;
  canonical_name: string;
  measure: string;
  value: number;
  unit: string;
  observed_at: string;
  longitude: number;
  latitude: number;
  evidence_locator: string;
  evidence_content_hash?: string;
  source_slug: string;
  attributes: Record<string, any>;
};

export type SourceHealth = {
  source_slug: string;
  source_name: string;
  publisher?: string;
  last_run_status?: string | null;
  last_successful_ingest?: string | null;
  freshness_observed_at?: string | null;
  total_runs?: number;
  total_records_persisted?: number;
  is_healthy?: boolean;
  status?: 'healthy' | 'degraded' | 'unhealthy';
  source_kind?: string;
  last_polled_at?: string | null;
  last_observation_at?: string | null;
  records_count?: number;
};

export type Alert = {
  id: string;
  rule_id: string;
  rule_name?: string;
  event_id?: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  status: "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED" | "SUPPRESSED";
  title?: string;
  summary?: string;
  context_summary?: Record<string, any>;
  created_at: string;
  evidence_id?: string;
  point?: [number, number];
  truth_class?: TruthClass;
  source?: string;
  description?: string;
};

export type WorldContext = {
  query_scope: {
    spatial?: { bounding_box?: BoundingBox; filter_type?: string };
    temporal?: { valid_at?: string; starts_at?: string; ends_at?: string; precision?: string };
    entity_ids?: string[];
    entity_kind?: string;
    limit?: number;
  };
  entities: Array<{
    id: string;
    canonical_name: string;
    entity_kind: string;
    attributes?: Record<string, any>;
  }>;
  observations: Observation[];
  events: Event[];
  geometries: GeometryFeature[];
  relationships: Array<{
    id: string;
    subject_entity_id: string;
    predicate: string;
    object_entity_id: string;
    confidence?: number;
    evidence_id?: string;
  }>;
  claims: Array<{
    id: string;
    entity_id: string;
    claim_type: string;
    truth_class: TruthClass;
    content: string;
    confidence?: number;
  }>;
  evidence: EvidenceCitation[];
  assumptions_or_limitations: string[];
};

export type AnomalyFindingSummary = {
  id: string;
  entity_id: string;
  entity_name: string;
  metric: string;
  unit: string;
  observed_value: number;
  observed_at: string;
  expected_value: number | null;
  deviation: number;
  anomaly_score: number;
  detection_method: string;
  severity: "INFO" | "WARNING" | "HIGH" | "CRITICAL";
  status: "NEW" | "ACTIVE" | "RESOLVED" | "SUPPRESSED";
  explanation: string;
  evidence_references?: string[];
};

export type PredictionPointSummary = {
  id: string;
  step_index: number;
  forecast_timestamp: string;
  predicted_value: number;
  lower_bound: number | null;
  upper_bound: number | null;
  confidence_level: number | null;
  method: string;
  truth_class: string;
};

export type PredictionRunSummary = {
  id: string;
  entity_id: string;
  metric: string;
  unit: string;
  status: "CREATED" | "RUNNING" | "COMPLETED" | "FAILED" | "INSUFFICIENT_DATA";
  selected_method: string;
  observations_count: number;
  trajectory_points_count: number;
  created_at: string;
};

const apiBase = import.meta.env.VITE_WORLDOS_API ?? "http://localhost:8000";

export async function populationObservations(): Promise<Observation[]> {
  const response = await fetch(`${apiBase}/observations?measure=population.total`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function geometryFeatures(geometryKind: string = "country_boundary"): Promise<GeometryFeature[]> {
  const query = geometryKind ? `?geometry_kind=${encodeURIComponent(geometryKind)}` : "";
  const response = await fetch(`${apiBase}/geometries${query}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function fetchWorldContext(params: {
  bbox?: BoundingBox;
  valid_at?: string;
  start?: string;
  end?: string;
  entity_kind?: string;
  limit?: number;
  signal?: AbortSignal;
}): Promise<WorldContext> {
  // Handle antimeridian-crossing bounds (min_lon > max_lon) across 180th meridian
  if (params.bbox && params.bbox.min_lon > params.bbox.max_lon) {
    const boxA: BoundingBox = {
      min_lon: params.bbox.min_lon,
      min_lat: params.bbox.min_lat,
      max_lon: 180,
      max_lat: params.bbox.max_lat,
    };
    const boxB: BoundingBox = {
      min_lon: -180,
      min_lat: params.bbox.min_lat,
      max_lon: params.bbox.max_lon,
      max_lat: params.bbox.max_lat,
    };
    const [resA, resB] = await Promise.all([
      fetchWorldContext({ ...params, bbox: boxA }),
      fetchWorldContext({ ...params, bbox: boxB }),
    ]);

    const dedupe = <T extends Record<string, any>>(listA: T[] = [], listB: T[] = []): T[] => {
      const seen = new Set<string>();
      const out: T[] = [];
      for (const item of [...listA, ...listB]) {
        const key = item.id || item.entity_id || item.evidence_id || item.claim_id || item.geometry_id || JSON.stringify(item);
        if (!seen.has(key)) {
          seen.add(key);
          out.push(item);
        }
      }
      return out;
    };

    return {
      query_scope: resA.query_scope,
      entities: dedupe(resA.entities, resB.entities),
      observations: dedupe(resA.observations, resB.observations),
      events: dedupe(resA.events, resB.events),
      geometries: dedupe(resA.geometries, resB.geometries),
      relationships: dedupe(resA.relationships, resB.relationships),
      claims: dedupe(resA.claims, resB.claims),
      evidence: dedupe(resA.evidence, resB.evidence),
      assumptions_or_limitations: Array.from(new Set([...(resA.assumptions_or_limitations || []), ...(resB.assumptions_or_limitations || [])])),
    };
  }

  const searchParams = new URLSearchParams();
  if (params.bbox) {
    searchParams.set("min_lon", params.bbox.min_lon.toFixed(5));
    searchParams.set("min_lat", params.bbox.min_lat.toFixed(5));
    searchParams.set("max_lon", params.bbox.max_lon.toFixed(5));
    searchParams.set("max_lat", params.bbox.max_lat.toFixed(5));
  }
  if (params.valid_at) searchParams.set("valid_at", params.valid_at);
  if (params.start) searchParams.set("start", params.start);
  if (params.end) searchParams.set("end", params.end);
  if (params.entity_kind) searchParams.set("entity_kind", params.entity_kind);
  if (params.limit) searchParams.set("limit", String(params.limit));

  const query = searchParams.toString() ? `?${searchParams.toString()}` : "";
  const response = await fetch(`${apiBase}/context${query}`, { signal: params.signal });
  if (!response.ok) throw new Error(`API error ${response.status} fetching context`);
  return response.json();
}

export async function fetchSourceHealth(): Promise<SourceHealth[]> {
  const response = await fetch(`${apiBase}/sources/health`);
  if (!response.ok) throw new Error(`API error ${response.status} fetching source health`);
  return response.json();
}

export async function fetchAlerts(status?: string, severity?: string, limit: number = 50): Promise<Alert[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (severity) params.set("severity", severity);
  params.set("limit", String(limit));
  const response = await fetch(`${apiBase}/alerts?${params.toString()}`);
  if (!response.ok) throw new Error(`API error ${response.status} fetching alerts`);
  return response.json();
}

export async function fetchEvents(limit: number = 100): Promise<Event[]> {
  const response = await fetch(`${apiBase}/events?limit=${limit}`);
  if (!response.ok) throw new Error(`API error ${response.status} fetching events`);
  return response.json();
}

export async function fetchLiveEvents(): Promise<LiveEventsResponse> {
  const response = await fetch(`${apiBase}/events/live`);
  if (!response.ok) throw new Error(`API error ${response.status} fetching live events`);
  return response.json();
}

export async function fetchLiveContext(): Promise<LiveContextResponse> {
  const response = await fetch(`${apiBase}/context/live`);
  if (!response.ok) throw new Error(`API error ${response.status} fetching live context`);
  return response.json();
}

export async function getAssistantSessionToken(): Promise<string> {
  const response = await fetch(`${apiBase}/assistant/elevenlabs/session`, { method: 'POST' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Voice assistant unavailable (${response.status})`);
  if (typeof body.conversation_token !== 'string') throw new Error('Voice assistant returned an invalid session token');
  return body.conversation_token;
}

export async function fetchAssistantMapContext(context: AssistantContext): Promise<AssistantMapContext> {
  const response = await fetch(`${apiBase}/assistant/map-context`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(context),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Map context unavailable (${response.status})`);
  }
  return response.json();
}

export async function fetchEntityContext(entityId: string): Promise<WorldContext> {
  const response = await fetch(`${apiBase}/entities/${encodeURIComponent(entityId)}/context`);
  if (!response.ok) throw new Error(`API error ${response.status} fetching entity context`);
  return response.json();
}

export async function anomalyFindings(metric?: string): Promise<AnomalyFindingSummary[]> {
  const query = metric ? `?metric=${encodeURIComponent(metric)}` : "";
  const response = await fetch(`${apiBase}/anomalies/findings${query}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function predictionRuns(metric?: string): Promise<PredictionRunSummary[]> {
  const query = metric ? `?metric=${encodeURIComponent(metric)}` : "";
  const response = await fetch(`${apiBase}/predictions/runs${query}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function fetchDecisions(limit: number = 50): Promise<any[]> {
  const response = await fetch(`${apiBase}/decisions?limit=${limit}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function fetchScenarios(limit: number = 50): Promise<any[]> {
  const response = await fetch(`${apiBase}/scenarios?limit=${limit}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function fetchSimulations(limit: number = 50): Promise<any[]> {
  const response = await fetch(`${apiBase}/simulations?limit=${limit}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function fetchClaims(limit: number = 50): Promise<any[]> {
  const response = await fetch(`${apiBase}/claims?limit=${limit}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}


export async function predictionTrajectory(runId: string): Promise<PredictionPointSummary[]> {
  const response = await fetch(`${apiBase}/predictions/runs/${encodeURIComponent(runId)}/trajectory`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function fetchAircraftStates(
  bbox?: BoundingBox,
  limit: number = 20_000,
  signal?: AbortSignal
): Promise<AircraftState[]> {
  const params = new URLSearchParams();
  if (bbox) {
    params.set("min_lon", bbox.min_lon.toFixed(4));
    params.set("min_lat", bbox.min_lat.toFixed(4));
    params.set("max_lon", bbox.max_lon.toFixed(4));
    params.set("max_lat", bbox.max_lat.toFixed(4));
  }
  params.set("limit", String(limit));
  const response = await fetch(`${apiBase}/aircraft/states?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`API returned ${response.status} fetching aircraft states`);
  return response.json();
}

export async function fetchAircraftTrack(icao24: string, limit: number = 100): Promise<AircraftTrackPoint[]> {
  const response = await fetch(`${apiBase}/aircraft/states/${encodeURIComponent(icao24)}/track?limit=${limit}`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching aircraft track`);
  return response.json();
}

export async function fetchMaritimeVessels(
  bbox?: BoundingBox,
  limit: number = 200,
  signal?: AbortSignal
): Promise<VesselState[]> {
  const params = new URLSearchParams();
  if (bbox) {
    params.set("min_lon", bbox.min_lon.toFixed(4));
    params.set("min_lat", bbox.min_lat.toFixed(4));
    params.set("max_lon", bbox.max_lon.toFixed(4));
    params.set("max_lat", bbox.max_lat.toFixed(4));
  }
  params.set("limit", String(limit));
  const response = await fetch(`${apiBase}/maritime/vessels?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`API returned ${response.status} fetching maritime vessels`);
  return response.json();
}

export async function fetchSatellites(
  limit: number = 20_000,
  signal?: AbortSignal
): Promise<SatelliteState[]> {
  const response = await fetch(`${apiBase}/space/satellites?limit=${limit}`, { signal });
  if (!response.ok) throw new Error(`API returned ${response.status} fetching satellites`);
  return response.json();
}

export async function fetchSatelliteGroundTrack(noradId: string): Promise<[number, number][]> {
  const response = await fetch(`${apiBase}/space/satellites/${encodeURIComponent(noradId)}/ground-track`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching satellite ground track`);
  const payload: { points: [number, number][] } = await response.json();
  return payload.points;
}

export function splitTrackAtAntimeridian(track: [number, number][]): [number, number][][] {
  const segments: [number, number][][] = [];
  let segment: [number, number][] = [];
  for (const point of track) {
    if (segment.length && Math.abs(point[0] - segment[segment.length - 1][0]) > 180) {
      if (segment.length > 1) segments.push(segment);
      segment = [];
    }
    segment.push(point);
  }
  if (segment.length > 1) segments.push(segment);
  return segments;
}

export async function fetchCameras(bbox?: BoundingBox, limit: number = 100): Promise<CameraEntity[]> {
  const params = new URLSearchParams();
  if (bbox) {
    params.set("min_lon", bbox.min_lon.toFixed(4));
    params.set("min_lat", bbox.min_lat.toFixed(4));
    params.set("max_lon", bbox.max_lon.toFixed(4));
    params.set("max_lat", bbox.max_lat.toFixed(4));
  }
  params.set("limit", String(limit));
  const response = await fetch(`${apiBase}/cameras?${params.toString()}`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching cameras`);
  return response.json();
}

export async function fetchThermalEvents(bbox?: BoundingBox, limit: number = 200): Promise<ThermalAnomalyEvent[]> {
  const params = new URLSearchParams();
  if (bbox) {
    params.set("min_lon", bbox.min_lon.toFixed(4));
    params.set("min_lat", bbox.min_lat.toFixed(4));
    params.set("max_lon", bbox.max_lon.toFixed(4));
    params.set("max_lat", bbox.max_lat.toFixed(4));
  }
  params.set("limit", String(limit));
  const response = await fetch(`${apiBase}/events/thermal?${params.toString()}`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching thermal events`);
  return response.json();
}

export async function fetchInfrastructure(nodeType?: string, limit: number = 100): Promise<InfrastructureNode[]> {
  const params = new URLSearchParams();
  if (nodeType) params.set("node_type", nodeType);
  params.set("limit", String(limit));
  const response = await fetch(`${apiBase}/infrastructure?${params.toString()}`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching infrastructure`);
  return response.json();
}

// -----------------------------------------------------------------------------
// Strategic Multi-Modal Route Planning (Phase 1)
// -----------------------------------------------------------------------------

export interface HubLocation {
  id: string;
  name: string;
  code: string;
  category: 'airport' | 'seaport' | 'intermodal';
  city: string;
  country: string;
  latitude: number;
  longitude: number;
  runway_or_draft_info?: string;
}

export interface ConflictZone {
  id: string;
  name: string;
  category: string;
  threat_level: 'LOW' | 'ELEVATED' | 'HIGH' | 'CRITICAL';
  description: string;
  active: boolean;
  polygon: [number, number][];
}

export interface RoutePoint {
  lat: number;
  lon: number;
  altitude_m: number;
  distance_km: number;
  distance_nm: number;
  segment_note?: string;
}

export interface RoutePlanRequest {
  origin_id: string;
  destination_id: string;
  mode: 'air' | 'sea' | 'multimodal';
  avoid_conflict_zones?: boolean;
  cruise_speed_kts?: number;
}

export interface RoutePlanResponse {
  route_id: string;
  mode: 'air' | 'sea' | 'multimodal';
  origin: HubLocation;
  destination: HubLocation;
  total_distance_km: number;
  total_distance_nm: number;
  estimated_duration_hours: number;
  estimated_duration_formatted: string;
  fuel_estimate_tons: number;
  co2_estimate_tons: number;
  threat_level: 'LOW' | 'ELEVATED' | 'HIGH' | 'CRITICAL';
  conflict_zones_avoided: string[];
  waypoints: RoutePoint[];
  altitude_profile: { dist_km: number; alt_m: number; lat: number; lon: number }[];
  geojson: any;
  summary: string;
}

export async function fetchRoutingHubs(): Promise<{ airports: HubLocation[]; seaports: HubLocation[] }> {
  const response = await fetch(`${apiBase}/routing/hubs`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching routing hubs`);
  return response.json();
}

export async function fetchConflictZones(): Promise<ConflictZone[]> {
  const response = await fetch(`${apiBase}/routing/conflict-zones`);
  if (!response.ok) throw new Error(`API returned ${response.status} fetching conflict zones`);
  return response.json();
}

export async function planStrategicRoute(req: RoutePlanRequest): Promise<RoutePlanResponse> {
  const response = await fetch(`${apiBase}/routing/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Failed to plan route' }));
    throw new Error(err.detail || `Route planning error (${response.status})`);
  }
  return response.json();
}


