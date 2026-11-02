import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  BoundingBox,
  GeometryFeature,
  Event,
  LiveEventsResponse,
  LiveContextResponse,
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
  fetchLiveEvents,
  fetchLiveContext,
  fetchAircraftStates,
  fetchAircraftTrack,
  fetchMaritimeVessels,
  fetchSatellites,
  fetchSatelliteGroundTrack,
  fetchCameras,
  fetchThermalEvents,
  fetchInfrastructure,
  geometryFeatures,
  populationObservations,
  AssistantAction,
} from './api';
import { BasemapMode, INITIAL_LAYERS, LayerDefinition, LayerId } from './types/layers';
import { SelectedItemPayload } from './types/layers';
import { GlobeEngine3D } from './components/GlobeEngine3D';
import { HudBar } from './components/HudBar';
import { LayerDock } from './components/LayerDock';
import { CommandPalette } from './components/CommandPalette';
import { EntityDetailsPanel } from './components/EntityDetailsPanel';
import { SourceHealthModal } from './components/SourceHealthModal';
import { RoutePlannerModal } from './components/RoutePlannerModal';
import { AssistantPanel } from './components/AssistantPanel';
import './styles.css';

function withLiveFeedHealth(layers: LayerDefinition[], sources: LiveEventsResponse['sources']): LayerDefinition[] {
  const naturalFeeds = [sources.nasa_eonet, sources.gdacs];
  const unavailable = naturalFeeds.filter((source) => source.status === 'unavailable').length;
  const status = unavailable === naturalFeeds.length ? 'unavailable'
    : unavailable ? 'partial'
      : naturalFeeds.some((source) => source.status === 'stale') ? 'stale' : 'fresh';
  const timestamps = naturalFeeds.flatMap((source) => source.retrieved_at ? [source.retrieved_at] : []).sort().reverse();
  return layers.map((layer) => {
    if (layer.id === 'earthquake-events') {
      const source = sources.usgs;
      return { ...layer, error: source.status === 'unavailable' ? 'Feed unavailable' : undefined, feedStatus: source.status, lastUpdated: source.retrieved_at };
    }
    if (layer.id === 'natural-hazards') {
      return {
        ...layer,
        error: unavailable ? 'One or more hazard feeds unavailable' : undefined,
        feedStatus: status,
        lastUpdated: timestamps[0],
      };
    }
    return layer;
  });
}

function withSatelliteFeedHealth(layers: LayerDefinition[], states: SatelliteState[] | null, error?: string): LayerDefinition[] {
  const first = states?.[0];
  const status = first?.attributes?.element_set_status;
  return layers.map((layer) => layer.id === 'space-satellites'
    ? {
        ...layer,
        error,
        feedStatus: error ? 'unavailable' : status === 'stale' ? 'stale' : states?.length ? 'fresh' : undefined,
        lastUpdated: first?.attributes?.elements_retrieved_at,
      }
    : layer);
}

function withSnapshotFeedHealth(
  layers: LayerDefinition[],
  layerId: 'aircraft-states' | 'maritime-vessels',
  observedAt: string[],
  staleAfterMs: number,
  unavailableMessage: string,
): LayerDefinition[] {
  const timestamps = observedAt.map(Date.parse).filter(Number.isFinite);
  const newest = timestamps.length ? Math.max(...timestamps) : undefined;
  const freshCount = timestamps.filter((timestamp) => Date.now() - timestamp <= staleAfterMs).length;
  const status = !timestamps.length ? 'unavailable' : freshCount === timestamps.length ? 'fresh' : freshCount ? 'partial' : 'stale';
  return layers.map((layer) => layer.id === layerId
    ? {
        ...layer,
        feedStatus: status,
        lastUpdated: newest === undefined ? undefined : new Date(newest).toISOString(),
        error: status === 'unavailable' ? unavailableMessage : undefined,
      }
    : layer);
}

export default function App() {
  const [basemapMode, setBasemapMode] = useState<BasemapMode>('satellite-hybrid');
  const [layers, setLayers] = useState<LayerDefinition[]>(INITIAL_LAYERS);
  const [viewportBbox, setViewportBbox] = useState<BoundingBox | null>(null);
  const [viewportZoom, setViewportZoom] = useState(0);
  const [streetViewCenter, setStreetViewCenter] = useState<[number, number] | null>(null);

  // Multi-domain intelligence collections
  const [geometries, setGeometries] = useState<GeometryFeature[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [naturalEvents, setNaturalEvents] = useState<Event[]>([]);
  const [liveContext, setLiveContext] = useState<LiveContextResponse | null>(null);
  const [liveContextError, setLiveContextError] = useState(false);
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
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
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

  const handleAssistantAction = useCallback((action: AssistantAction) => {
    if (action.type === 'set_layer_visibility') {
      if (!INITIAL_LAYERS.some((layer) => layer.id === action.layer_id)) return;
      setLayers((prev) => prev.map((layer) => layer.id === action.layer_id ? { ...layer, enabled: action.visible } : layer));
    } else if (action.type === 'fly_to') {
      setTargetLocation({
        center: action.center,
        zoom: action.zoom ?? 12,
      });
    }
  }, []);

  useEffect(() => {
    if (viewportZoom >= 15.5 && viewportBbox && !streetViewCenter) {
      setStreetViewCenter([
        (viewportBbox.min_lon + viewportBbox.max_lon) / 2,
        (viewportBbox.min_lat + viewportBbox.max_lat) / 2,
      ]);
    } else if (viewportZoom < 14.5 && streetViewCenter) {
      setStreetViewCenter(null);
    }
  }, [viewportBbox, viewportZoom, streetViewCenter]);

  useEffect(() => {
    const refreshSnapshotHealth = () => {
      setLayers((prev) => withSnapshotFeedHealth(prev, 'aircraft-states', aircraft.map((a) => a.observed_at), 5 * 60_000, 'No stored OpenSky observations; configure credentials and ingest a snapshot.'));
      setLayers((prev) => withSnapshotFeedHealth(prev, 'maritime-vessels', vessels.map((v) => v.observed_at), 10 * 60_000, 'No stored AIS observations; configure AISStream and ingest positions.'));
    };
    const interval = setInterval(refreshSnapshotHealth, 60_000);
    return () => clearInterval(interval);
  }, [aircraft, vessels]);

  // Update real-time counts on all layers
  useEffect(() => {
    setLayers((prev) =>
      prev.map((l) => {
        if (l.id === 'country-boundaries') return { ...l, count: geometries.length };
        if (l.id === 'earthquake-events') return { ...l, count: events.filter((event) => event.event_type === 'earthquake' || event.kind === 'earthquake' || event.source_slug === 'usgs-earthquakes').length };
        if (l.id === 'natural-hazards') return { ...l, count: naturalEvents.length };
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
    naturalEvents,
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
      fetchLiveEvents(),
      fetchAlerts(undefined, undefined, 30),
      fetchAircraftStates(undefined, 20_000),
      fetchMaritimeVessels(undefined, 1000),
      fetchSatellites(20_000),
      fetchCameras(undefined, 100),
      fetchThermalEvents(undefined, 1000),
      fetchInfrastructure(undefined, 100),
    ]).then(
      ([
        geoRes,
        popRes,
        evRes,
        liveRes,
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
        if (liveRes.status === 'fulfilled') {
          setEvents((current) => {
            const stored = evRes.status === 'fulfilled' ? evRes.value : current;
            return [...liveRes.value.earthquakes, ...stored.filter((event) => event.source_slug !== 'usgs-earthquakes')];
          });
          setNaturalEvents(liveRes.value.natural_events);
          setLayers((prev) => withLiveFeedHealth(prev, liveRes.value.sources));
        } else {
          setLayers((prev) => prev.map((layer) =>
            layer.id === 'earthquake-events' || layer.id === 'natural-hazards'
              ? { ...layer, error: 'Live event feeds unavailable', feedStatus: 'unavailable' }
              : layer
          ));
        }
        if (alRes.status === 'fulfilled' && alRes.value) setAlerts(alRes.value);
        if (acRes.status === 'fulfilled' && acRes.value) setAircraft(acRes.value);
        if (vesRes.status === 'fulfilled' && vesRes.value) setVessels(vesRes.value);
        setLayers((prev) => withSnapshotFeedHealth(
          prev,
          'aircraft-states',
          acRes.status === 'fulfilled' ? acRes.value.map((a) => a.observed_at) : [],
          5 * 60_000,
          'No stored OpenSky observations; configure credentials and ingest a snapshot.'
        ));
        setLayers((prev) => withSnapshotFeedHealth(prev, 'maritime-vessels', vesRes.status === 'fulfilled' ? vesRes.value.map((v) => v.observed_at) : [], 10 * 60_000, 'No stored AIS observations; configure AISStream and ingest positions.'));
        if (satRes.status === 'fulfilled' && satRes.value) setSatellites(satRes.value);
        setLayers((prev) => withSatelliteFeedHealth(
          prev,
          satRes.status === 'fulfilled' ? satRes.value : null,
          satRes.status === 'rejected' ? 'Satellite feed unavailable' : undefined,
        ));
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

  useEffect(() => {
    let mounted = true;
    const refreshSnapshots = async () => {
      const [aircraftResult, vesselResult, fireResult] = await Promise.allSettled([
        fetchAircraftStates(undefined, 20_000),
        fetchMaritimeVessels(undefined, 1000),
        fetchThermalEvents(undefined, 1000),
      ]);
      if (!mounted) return;
      if (aircraftResult.status === 'fulfilled') {
        setAircraft(aircraftResult.value);
        setLayers((prev) => withSnapshotFeedHealth(prev, 'aircraft-states', aircraftResult.value.map((a) => a.observed_at), 5 * 60_000, 'No stored OpenSky observations; configure credentials and ingest a snapshot.'));
      }
      if (vesselResult.status === 'fulfilled') {
        setVessels(vesselResult.value);
        setLayers((prev) => withSnapshotFeedHealth(prev, 'maritime-vessels', vesselResult.value.map((v) => v.observed_at), 10 * 60_000, 'No stored AIS observations; configure AISStream and ingest positions.'));
      }
      if (fireResult.status === 'fulfilled') setThermalEvents(fireResult.value);
    };
    const interval = setInterval(() => { void refreshSnapshots(); }, 5 * 60_000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  useEffect(() => {
    let mounted = true;
    const refresh = () => fetchLiveContext().then((value) => {
      if (mounted) { setLiveContext(value); setLiveContextError(false); }
    }).catch(() => { if (mounted) setLiveContextError(true); });
    refresh();
    const interval = setInterval(refresh, 5 * 60_000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchLiveEvents().then((live) => {
        setEvents((current) => [...live.earthquakes, ...current.filter((event) => event.source_slug !== 'usgs-earthquakes')]);
        setNaturalEvents(live.natural_events);
        setLayers((prev) => withLiveFeedHealth(prev, live.sources));
      }).catch(() => setLayers((prev) => prev.map((layer) =>
        layer.id === 'earthquake-events' || layer.id === 'natural-hazards'
          ? { ...layer, error: 'Live event feeds unavailable', feedStatus: 'unavailable' }
          : layer
      )));
    }, 60_000);
    return () => clearInterval(interval);
  }, []);

  // Refresh propagated positions from current orbital elements; the backend caches provider data.
  useEffect(() => {
    const refreshSatellites = () => {
      fetchSatellites(20_000)
        .then((states) => {
          setSatellites(states);
          setLayers((prev) => withSatelliteFeedHealth(prev, states));
        })
        .catch(() => setLayers((prev) => withSatelliteFeedHealth(prev, null, 'Satellite feed unavailable')));
    };
    const interval = setInterval(refreshSatellites, 60_000);
    return () => clearInterval(interval);
  }, []);

  // Handle entity selection and automatic historical track lookup
  const handleSelectItem = useCallback((item: SelectedItemPayload) => {
    setSelectedItem(item);
    setSelectedTrack(null);

    const coords = item.data?.point || item.data?.coordinates || item.data?.geometry?.coordinates;
    const longitude = item.data?.longitude ?? (Array.isArray(coords) ? coords[0] : undefined);
    const latitude = item.data?.latitude ?? (Array.isArray(coords) ? coords[1] : undefined);
    if (typeof longitude === 'number' && Number.isFinite(longitude) &&
      typeof latitude === 'number' && Number.isFinite(latitude)) {
      setTargetLocation({
        center: [longitude, latitude],
        zoom: item.type === 'camera' ? 15.5 : item.type === 'satellite' ? 4.5 : 9,
      });
    }

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
    if (item.type === 'satellite') {
      const noradId = item.data?.attributes?.norad_id;
      if (noradId) fetchSatelliteGroundTrack(String(noradId)).then((groundTrack) => {
        setSelectedItem((current) => current?.type === 'satellite' && current.data?.attributes?.norad_id === noradId
          ? { ...current, data: { ...current.data, attributes: { ...current.data.attributes, ground_track: groundTrack } } }
          : current);
      }).catch(() => {});
    }
  }, []);

  // Viewport-aware context querying with debouncing
  const handleViewportChange = useCallback((bbox: BoundingBox, zoom?: number) => {
    setViewportBbox(bbox);
    if (zoom !== undefined) setViewportZoom(zoom);

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
        const signal = abortControllerRef.current.signal;
        const [context, acStates, vesStates] = await Promise.all([
          fetchWorldContext({
            bbox,
            limit: 200,
            signal,
          }),
          fetchAircraftStates(bbox, 20_000, signal).catch((err) => {
            if (err?.name === 'AbortError') return null;
            return null;
          }),
          fetchMaritimeVessels(bbox, 1000, signal).catch((err) => {
            if (err?.name === 'AbortError') return null;
            return null;
          }),
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
        if (acStates) {
          setAircraft(acStates);
          setLayers((prev) => {
            if (bbox && acStates.length === 0) return prev;
            return withSnapshotFeedHealth(prev, 'aircraft-states', acStates.map((a) => a.observed_at), 5 * 60_000, 'No stored OpenSky observations; configure credentials and ingest a snapshot.');
          });
        } else {
          setLayers((prev) => withSnapshotFeedHealth(prev, 'aircraft-states', [], 5 * 60_000, 'Aircraft snapshot unavailable.'));
        }
        if (vesStates) {
          setVessels(vesStates);
          setLayers((prev) => {
            if (bbox && vesStates.length === 0) return prev;
            return withSnapshotFeedHealth(prev, 'maritime-vessels', vesStates.map((v) => v.observed_at), 10 * 60_000, 'No stored AIS observations; configure AISStream and ingest positions.');
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
        basemapMode={basemapMode}
        onSetBasemapMode={setBasemapMode}
        viewportBbox={viewportBbox}
        isLoading={isLoading}
        onOpenCommandPalette={() => setIsCommandOpen(true)}
        onOpenSourceHealth={() => setIsSourceHealthOpen(true)}
        onOpenRoutePlanner={() => setIsRoutePlannerOpen(true)}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        isAssistantOpen={isAssistantOpen}
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
        <GlobeEngine3D
          layers={layers}
          basemapMode={basemapMode}
          geometries={geometries}
          events={events}
          naturalEvents={naturalEvents}
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
      </main>

      {viewportZoom >= 14.5 && streetViewCenter && (
        <section className="street-view-panel" aria-label="Community street-level imagery">
          <header className="street-view-panel-header">
            <div>
              <strong>STREET LEVEL</strong>
              <span>Community photo coverage · Panoramax</span>
            </div>
          </header>
          <iframe
            title="Panoramax street-level photo map"
            src={`https://explore.panoramax.fr/?map=17/${streetViewCenter[1]}/${streetViewCenter[0]}&focus=map`}
            loading="lazy"
            allowFullScreen
          />
          <p>Zoom out to return to globe view. Street photos appear only where contributors have mapped them.</p>
        </section>
      )}

      {/* Floating Tactical Layer Dock */}
      <LayerDock
        layers={layers}
        liveContext={liveContext}
        contextError={liveContextError}
        onToggleLayer={handleToggleLayer}
        isCollapsed={isDockCollapsed}
        onToggleCollapse={() => setIsDockCollapsed((prev) => !prev)}
      />

      <AssistantPanel
        isOpen={isAssistantOpen}
        context={{
          ...(selectedItem?.data?.entity_id ? { selected_entity_id: String(selectedItem.data.entity_id) } : {}),
          ...(viewportBbox ? { map_bounds: viewportBbox } : {}),
        }}
        onClose={() => setIsAssistantOpen(false)}
        onAction={handleAssistantAction}
      />

      {/* Entity & Event Details Dossier Drawer */}
      <EntityDetailsPanel
        selectedItem={selectedItem}
        track={selectedTrack}
        onClose={() => {
          setSelectedItem(null);
          setSelectedTrack(null);
        }}
        onFlyTo={(coords, zoom) => setTargetLocation({ center: coords, zoom: zoom || 14 })}
      />

      {/* Keyboard-Accessible Command Palette (cmdk) */}
      <CommandPalette
        isOpen={isCommandOpen}
        onClose={() => setIsCommandOpen(false)}
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
        onFlyToRoute={(coords, zoom) => setTargetLocation({ center: coords, zoom: zoom || 5 })}
      />
    </div>
  );
}
