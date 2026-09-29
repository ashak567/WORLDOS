import { useEffect, useRef, useState } from "react";
import { Cartesian3, GeoJsonDataSource, Ion, Viewer } from "cesium";
import { GeometryFeature, Observation, geometryFeatures, populationObservations } from "./api";
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./styles.css";

// This viewer renders query results; it does not own, infer, or mutate world facts.
window.CESIUM_BASE_URL = "/cesium/";
Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? "";

export default function App() {
  const globe = useRef<HTMLDivElement>(null);
  const viewer = useRef<Viewer | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [error, setError] = useState<string>();

  useEffect(() => {
    viewer.current = new Viewer(globe.current!, { animation: false, timeline: false, baseLayerPicker: false });
    viewer.current.camera.setView({ destination: Cartesian3.fromDegrees(78.9629, 20.5937, 8_000_000) });
    return () => { viewer.current?.destroy(); };
  }, []);

  useEffect(() => {
    populationObservations().then(setObservations).catch((reason: unknown) => setError(String(reason)));
  }, []);

  useEffect(() => {
    let source: GeoJsonDataSource | undefined;
    geometryFeatures().then((features: GeometryFeature[]) => GeoJsonDataSource.load({
      type: "FeatureCollection",
      features: features.map(feature => ({ type: "Feature", geometry: feature.geometry, properties: {
        name: feature.canonical_name, geometry_kind: feature.geometry_kind,
      }})),
    })).then(loaded => {
      source = loaded;
      return viewer.current?.dataSources.add(loaded);
    }).catch((reason: unknown) => setError(String(reason)));
    return () => { if (source) viewer.current?.dataSources.remove(source, true); };
  }, []);

  return <main>
    <section className="panel">
      <p className="eyebrow">WORLDOS · deterministic context</p>
      <h1>Evidence before intelligence.</h1>
      <p>Population observations from the World Bank, kept with their source locator and queryable time interval.</p>
      {error && <p className="error">{error}</p>}
      <ol>{observations.slice(0, 20).map(item => <li key={`${item.entity_id}-${item.starts_at}`}>
        <strong>{item.canonical_name}</strong> — {item.value.toLocaleString()} {item.unit} ({new Date(item.starts_at).getUTCFullYear()})
        <a href={item.evidence_locator} target="_blank" rel="noreferrer"> evidence</a>
      </li>)}</ol>
    </section>
    <div ref={globe} className="globe" aria-label="3D world map" />
  </main>;
}

