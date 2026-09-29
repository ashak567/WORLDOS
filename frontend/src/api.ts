export type Observation = {
  entity_id: string;
  canonical_name: string;
  measure: string;
  value: number;
  unit: string;
  starts_at: string;
  evidence_locator: string;
};

const apiBase = import.meta.env.VITE_WORLDOS_API ?? "http://localhost:8000";

export async function populationObservations(): Promise<Observation[]> {
  const response = await fetch(`${apiBase}/observations?measure=population.total`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

