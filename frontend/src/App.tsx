import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  BoundingBox,
  GeometryFeature,
  Event,
  Observation,
  Alert,
  AircraftState,
  VesselState,
  SatelliteState,
  CameraEntity,
  ThermalAnomalyEvent,
  InfrastructureNode,
  AircraftTrackPoint,
  RoutePlanResponse,
  fetchWorldContext,
  fetchAlerts,
  fetchEvents,
  fetchAircraftStates,
  fetchAircraftTrack,
  fetchMaritimeVessels,
  fetchSatellites,
  fetchCameras,
  fetchThermalEvents,
  fetchInfrastructure,
  geometryFeatures,
  populationObservations,
} from './api';
import { BasemapMode, INITIAL_LAYERS, LayerDefinition, LayerId } from './types/layers';
import { MapEngine2D, SelectedItemPayload } from './components/MapEngine2D';
import { GlobeEngine3D } from './components/GlobeEngine3D';
import { HudBar } from './components/HudBar';
import { LayerDock } from './components/LayerDock';
import { CommandPalette } from './components/CommandPalette';
import { EntityDetailsPanel } from './components/EntityDetailsPanel';
import { SourceHealthModal } from './components/SourceHealthModal';
import { RoutePlannerModal } from './components/RoutePlannerModal';
import './styles.css';

export default function App() {
  const [viewMode, setViewMode] = useState<'2d' | '3d'>('2d');
  const [basemapMode, setBasemapMode] = useState<BasemapMode>('dark-tactical');
  const [layers, setLayers] = useState<LayerDefinition[]>(INITIAL_LAYERS);
  const [viewportBbox, setViewportBbox] = useState<BoundingBox | null>(null);

  // Multi-domain intelligence collections
  const [geometries, setGeometries] = useState<GeometryFeature[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [aircraft, setAircraft] = useState<AircraftState[]>([]);
  const [vessels, setVessels] = useState<VesselState[]>([]);
  const [satellites, setSatellites] = useState<SatelliteState[]>([]);
  const [cameras, setCameras] = useState<CameraEntity[]>([]);
  const [thermalEvents, setThermalEvents] = useState<ThermalAnomalyEvent[]>([]);
  const [infrastructure, setInfrastructure] = useState<InfrastructureNode[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<AircraftTrackPoint[] | null>(null);

  // UI state
  const [selectedItem, setSelectedItem] = useState<SelectedItemPayload | null>(null);
  const [targetLocation, setTargetLocation] = useState<{ center: [number, number]; zoom?: number } | null>(null);
  const [isCommandOpen, setIsCommandOpen] = useState(false);
  const [isSourceHealthOpen, setIsSourceHealthOpen] = useState(false);
  const [isRoutePlannerOpen, setIsRoutePlannerOpen] = useState(false);
  const [activeRoute, setActiveRoute] = useState<RoutePlanResponse | null>(null);
  const [isDockCollapsed, setIsDockCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Toggle layer visibility
  const handleToggleLayer = useCallback((id: LayerId) => {
    setLayers((prev) =>
      prev.map((layer) =>
        layer.id === id ? { ...layer, enabled: !layer.enabled } : layer
      )
    );
  }, []);

  // Update real-time counts on all layers
  useEffect(() => {
    setLayers((prev) =>
      prev.map((l) => {
        if (l.id === 'country-boundaries') return { ...l, count: geometries.length };
        if (l.id === 'earthquake-events') return { ...l, count: events.length };
        if (l.id === 'population-observations') return { ...l, count: observations.length };
        if (l.id === 'aircraft-states') return { ...l, count: aircraft.length };
        if (l.id === 'maritime-vessels') return { ...l, count: vessels.length };
        if (l.id === 'space-satellites') return { ...l, count: satellites.length };
        if (l.id === 'surveillance-cameras') return { ...l, count: cameras.length };
        if (l.id === 'thermal-fires') return { ...l, count: thermalEvents.length };
        if (l.id === 'critical-infrastructure') return { ...l, count: infrastructure.length };
        if (l.id === 'anomalies') {
          const anomCount = observations.filter((o) => o.is_anomaly).length;
          return { ...l, count: anomCount };
        }
        if (l.id === 'system-alerts') return { ...l, count: alerts.length };
        return l;
      })
    );
  }, [
    geometries,
    events,
    observations,
    alerts,
    aircraft,
    vessels,
    satellites,
    cameras,
    thermalEvents,
    infrastructure,
  ]);

  // Initial load of global geometries and multi-domain feeds
  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    Promise.allSettled([
      geometryFeatures(),
      populationObservations(),
      fetchEvents(100),
      fetchAlerts(undefined, undefined, 30),
      fetchAircraftStates(undefined, 1000),
      fetchMaritimeVessels(undefined, 200),
      fetchSatellites(50),
      fetchCameras(undefined, 100),
      fetchThermalEvents(undefined, 200),
      fetchInfrastructure(undefined, 100),
    ]).then(
      ([
        geoRes,
        popRes,
        evRes,
        alRes,
        acRes,
        vesRes,
        satRes,
        camRes,
        firRes,
        infRes,
      ]) => {
        if (!isMounted) return;
        if (geoRes.status === 'fulfilled' && geoRes.value) setGeometries(geoRes.value);
        if (popRes.status === 'fulfilled' && popRes.value) setObservations(popRes.value);
        if (evRes.status === 'fulfilled' && evRes.value) setEvents(evRes.value);
        if (alRes.status === 'fulfilled' && alRes.value) setAlerts(alRes.value);
        if (acRes.status === 'fulfilled' && acRes.value) setAircraft(acRes.value);
        if (vesRes.status === 'fulfilled' && vesRes.value) setVessels(vesRes.value);
        if (satRes.status === 'fulfilled' && satRes.value) setSatellites(satRes.value);
        if (camRes.status === 'fulfilled' && camRes.value) setCameras(camRes.value);
        if (firRes.status === 'fulfilled' && firRes.value) setThermalEvents(firRes.value);
        if (infRes.status === 'fulfilled' && infRes.value) setInfrastructure(infRes.value);
        setIsLoading(false);
      }
    );

    return () => {
      isMounted = false;
    };
  }, []);

  // Real-time Dead-Reckoning & Extrapolation Engine (60s physics propagation between snapshots)
  useEffect(() => {
    const interval = setInterval(() => {
      // 1. Advance aircraft along velocity vector (heading + ground speed)
      setAircraft((prev) =>
        prev.map((a) => {
          if (a.attributes?.on_ground) return a;
          const speedKnots = a.attributes?.velocity ? a.attributes.velocity * 1.94384 : 450;
          const trackDeg = a.attributes?.true_track ?? 0;
          const distKm = (speedKnots * 1.852) / 3600; // km in 1 second
          const trackRad = (trackDeg * Math.PI) / 180;
          const dLat = (distKm / 111.0) * Math.cos(trackRad);
          const cosLat = Math.cos((a.latitude * Math.PI) / 180);
          const dLon = cosLat !== 0 ? (distKm / (111.0 * cosLat)) * Math.sin(trackRad) : 0;
          return {
            ...a,
            latitude: Number((a.latitude + dLat).toFixed(5)),
            longitude: Number((a.longitude + dLon).toFixed(5)),
          };
        })
      );

      // 2. Advance maritime vessels along course over ground and speed
      setVessels((prev) =>
        prev.map((v) => {
          const speedKnots = v.attributes?.sog_knots ?? 15;
          const courseDeg = v.attributes?.heading_degrees || v.attributes?.cog_degrees || 0;
          const distKm = (speedKnots * 1.852) / 3600; // km in 1 second
          const courseRad = (courseDeg * Math.PI) / 180;
          const dLat = (distKm / 111.0) * Math.cos(courseRad);
          const cosLat = Math.cos((v.latitude * Math.PI) / 180);
          const dLon = cosLat !== 0 ? (distKm / (111.0 * cosLat)) * Math.sin(courseRad) : 0;
          return {
            ...v,
            latitude: Number((v.latitude + dLat).toFixed(5)),
            longitude: Number((v.longitude + dLon).toFixed(5)),
          };
        })
      );

      // 3. Advance satellites along orbital trajectory (~7.6 km/s orbital speed)
      setSatellites((prev) =>
        prev.map((s) => {
          const periodMin = s.attributes?.period_min || 92.5;
          const speedDegPerSec = 360 / (periodMin * 60);
          const incDeg = s.attributes?.inclination_deg || 51.6;
          const newLon = ((s.longitude + speedDegPerSec + 180) % 360) - 180;
          const theta = ((newLon + 180) * Math.PI) / 180;
          const newLat = incDeg * Math.sin(theta);
          return {
            ...s,
            longitude: Number(newLon.toFixed(4)),
            latitude: Number(newLat.toFixed(4)),
          };
        })
      );
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Handle entity selection and automatic historical track lookup
  const handleSelectItem = useCallback((item: SelectedItemPayload) => {
    setSelectedItem(item);
    setSelectedTrack(null);

    // If an aircraft is selected, query its historical observation track
    if (item.type === 'aircraft') {
      const icao24 =
        item.data?.attributes?.icao24 ||
        item.data?.source_key ||
        item.data?.canonical_name;
      if (icao24) {
        fetchAircraftTrack(icao24, 100)
          .then((trackPoints) => {
            if (trackPoints && trackPoints.length > 0) {
              setSelectedTrack(trackPoints);
            }
          })
          .catch(() => {});
      }
    }
  }, []);

  // Viewport-aware context querying with debouncing
  const handleViewportChange = useCallback((bbox: BoundingBox) => {
    setViewportBbox(bbox);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(async () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      try {
        setIsLoading(true);
        const [context, acStates, vesStates] = await Promise.all([
          fetchWorldContext({
            bbox,
            limit: 200,
            signal: abortControllerRef.current.signal,
          }),
          fetchAircraftStates(bbox, 500).catch(() => null),
          fetchMaritimeVessels(bbox, 100).catch(() => null),
        ]);

        if (context) {
          if (context.geometries && context.geometries.length > 0) {
            const boundaryGeoms = context.geometries.filter(
              (g) =>
                (g.geometry_kind === 'country_boundary' || g.geometry_kind === 'sovereign_state') &&
                (g.geometry && (g.geometry.type === 'Polygon' || g.geometry.type === 'MultiPolygon'))
            );
            if (boundaryGeoms.length > 0) {
              setGeometries((prev) => {
                const map = new Map(prev.map((g) => [g.id, g]));
                for (const bg of boundaryGeoms) {
                  map.set(bg.id, bg);
                }
                return Array.from(map.values());
              });
            }
          }
          if (context.events && context.events.length > 0) {
            setEvents(context.events);
          }
          if (context.observations && context.observations.length > 0) {
            setObservations(context.observations);
          }
        }
        if (acStates && acStates.length > 0) {
          setAircraft(acStates);
        }
        if (vesStates && vesStates.length > 0) {
          setVessels((prev) => {
            const map = new Map(prev.map((v) => [v.entity_id, v]));
            for (const v of vesStates) {
              map.set(v.entity_id, v);
            }
            return Array.from(map.values());
          });
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          // Keep existing data on error
        }
      } finally {
        setIsLoading(false);
      }
    }, 450);
  }, []);

  // Global keydown handler for palette
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  // Jump to specific street camera and open its live feed
  const handleJumpToCamera = useCallback((camera: CameraEntity) => {
    setLayers((prev) =>
      prev.map((l) => (l.id === 'surveillance-cameras' ? { ...l, enabled: true } : l))
    );
    setTargetLocation({ center: [camera.longitude, camera.latitude], zoom: 15.5 });
    setSelectedItem({ type: 'camera', data: camera });
    setSelectedTrack(null);
  }, []);

  return (
    <div className="worldos-app">
      {/* Background Tactical Grid */}
      <div className="tactical-grid-bg" />

      {/* Mission Control HUD Bar */}
      <HudBar
        viewMode={viewMode}
        onToggleViewMode={setViewMode}
        basemapMode={basemapMode}
        onSetBasemapMode={setBasemapMode}
        viewportBbox={viewportBbox}
        isLoading={isLoading}
        onOpenCommandPalette={() => setIsCommandOpen(true)}
        onOpenSourceHealth={() => setIsSourceHealthOpen(true)}
        onOpenRoutePlanner={() => setIsRoutePlannerOpen(true)}
        isRouteActive={activeRoute !== null}
        isDockCollapsed={isDockCollapsed}
        onToggleDock={() => setIsDockCollapsed((prev) => !prev)}
        aircraftCount={aircraft.length}
        vesselCount={vessels.length}
        satelliteCount={satellites.length}
        cameraCount={cameras.length}
        fireCount={thermalEvents.length}
        infraCount={infrastructure.length}
        cameras={cameras}
        onJumpToCamera={handleJumpToCamera}
      />

      {/* Master Geospatial Viewport Stage */}
      <main className="viewport-stage" aria-label="Geospatial Tactical Viewport">
        {viewMode === '2d' ? (
          <MapEngine2D
            layers={layers}
            basemapMode={basemapMode}
            geometries={geometries}
            events={events}
            observations={observations}
            alerts={alerts}
            aircraft={aircraft}
            vessels={vessels}
            satellites={satellites}
            cameras={cameras}
            thermalEvents={thermalEvents}
            infrastructure={infrastructure}
            selectedTrack={selectedTrack}
            activeRoute={activeRoute}
            targetLocation={targetLocation}
            selectedItem={selectedItem}
            onViewportChange={handleViewportChange}
            onSelectItem={handleSelectItem}
          />
        ) : (
          <GlobeEngine3D
            layers={layers}
            basemapMode={basemapMode}
            geometries={geometries}
            events={events}
            observations={observations}
            alerts={alerts}
            aircraft={aircraft}
            vessels={vessels}
            satellites={satellites}
            cameras={cameras}
            thermalEvents={thermalEvents}
            infrastructure={infrastructure}
            selectedTrack={selectedTrack}
            activeRoute={activeRoute}
            targetLocation={targetLocation}
            selectedItem={selectedItem}
            onViewportChange={handleViewportChange}
            onSelectItem={handleSelectItem}
          />
        )}
      </main>

      {/* Floating Tactical Layer Dock */}
      <LayerDock
        layers={layers}
        onToggleLayer={handleToggleLayer}
        isCollapsed={isDockCollapsed}
        onToggleCollapse={() => setIsDockCollapsed((prev) => !prev)}
      />

      {/* Entity & Event Details Dossier Drawer */}
      <EntityDetailsPanel
        selectedItem={selectedItem}
        track={selectedTrack}
        onClose={() => {
          setSelectedItem(null);
          setSelectedTrack(null);
        }}
        onFlyTo={(coords, zoom) => setTargetLocation({ center: coords, zoom: zoom || (viewMode === '3d' ? 14 : 15) })}
      />

      {/* Keyboard-Accessible Command Palette (cmdk) */}
      <CommandPalette
        isOpen={isCommandOpen}
        onClose={() => setIsCommandOpen(false)}
        viewMode={viewMode}
        onSetViewMode={setViewMode}
        layers={layers}
        onToggleLayer={handleToggleLayer}
        onOpenSourceHealth={() => setIsSourceHealthOpen(true)}
        onOpenRoutePlanner={() => setIsRoutePlannerOpen(true)}
        onToggleDock={() => setIsDockCollapsed((prev) => !prev)}
        onJumpToRegion={(coords, zoom) => setTargetLocation({ center: coords, zoom })}
        cameras={cameras}
        onSelectCamera={handleJumpToCamera}
      />

      {/* Data Source Health & Freshness Modal */}
      <SourceHealthModal
        isOpen={isSourceHealthOpen}
        onClose={() => setIsSourceHealthOpen(false)}
      />

      {/* Strategic Multi-Modal Route Planner (Phase 1) */}
      <RoutePlannerModal
        isOpen={isRoutePlannerOpen}
        onClose={() => setIsRoutePlannerOpen(false)}
        activeRoute={activeRoute}
        onSelectRoute={setActiveRoute}
        onFlyToRoute={(coords, zoom) => setTargetLocation({ center: coords, zoom: zoom || (viewMode === '3d' ? 5 : 4) })}
      />
    </div>
  );
}
