export type Observation = {
  entity_id: string;
  canonical_name: string;
  measure: string;
  value: number;
  unit: string;
  starts_at: string;
  evidence_locator: string;
};

export type GeometryFeature = {
  id: string;
  entity_id: string;
  canonical_name: string;
  geometry_kind: string;
  geometry: GeoJSON.Geometry;
};

const apiBase = import.meta.env.VITE_WORLDOS_API ?? "http://localhost:8000";

export async function populationObservations(): Promise<Observation[]> {
  const response = await fetch(`${apiBase}/observations?measure=population.total`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

export async function geometryFeatures(): Promise<GeometryFeature[]> {
  const response = await fetch(`${apiBase}/geometries`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

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
};

export async function anomalyFindings(metric?: string): Promise<AnomalyFindingSummary[]> {
  const query = metric ? `?metric=${encodeURIComponent(metric)}` : "";
  const response = await fetch(`${apiBase}/anomalies/findings${query}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}
