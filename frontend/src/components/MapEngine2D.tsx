import React, { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import { MapboxOverlay } from '@deck.gl/mapbox';
import { GeoJsonLayer, ScatterplotLayer, IconLayer, PathLayer } from '@deck.gl/layers';
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
} from '../api';
import { BasemapMode, LayerDefinition } from '../types/layers';

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
    | 'infrastructure';
  data: any;
}

interface MapEngine2DProps {
  layers: LayerDefinition[];
  basemapMode: BasemapMode;
  geometries: GeometryFeature[];
  events: Event[];
  observations: Observation[];
  alerts: Alert[];
  aircraft?: AircraftState[];
  vessels?: VesselState[];
  satellites?: SatelliteState[];
  cameras?: CameraEntity[];
  thermalEvents?: ThermalAnomalyEvent[];
  infrastructure?: InfrastructureNode[];
  selectedTrack?: AircraftTrackPoint[] | null;
  activeRoute?: RoutePlanResponse | null;
  targetLocation?: { center: [number, number]; zoom?: number } | null;
  selectedItem?: SelectedItemPayload | null;
  onViewportChange: (bbox: BoundingBox) => void;
  onSelectItem: (item: SelectedItemPayload) => void;
}

// Vector SVG Data URLs for Heading-Aware Tactical Rendering
const AIRPLANE_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg>`;
const VESSEL_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M12 2L4 9v7l8 6 8-6V9l-8-7zm0 3.5l5 4.38v4.24l-5 3.75-5-3.75V9.88l5-4.38z"/></svg>`;
const SATELLITE_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><circle cx="12" cy="12" r="3.5"/><path d="M4 10h3v4H4zm13 0h3v4h-3zM10 4h4v3h-4zm0 13h4v3h-4zM2 11h2v2H2zm18 0h2v2h-2zM11 2h2v2h-2zm0 18h2v2h-2z"/></svg>`;
const CAMERA_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M12 15c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3zm0-4c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm9-2h-3.17l-1.83-2H8L6.17 9H3c-1.1 0-2 .9-2 2v9c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2v-9c0-1.1-.9-2-2-2zm0 11H3v-9h3.83l1.83-2h6.68l1.83 2H21v9z"/></svg>`;
const FIRE_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M12 2C8.13 4.57 6 8.65 6 13c0 3.31 2.69 6 6 6s6-2.69 6-6c0-4.35-2.13-8.43-6-11zm0 15c-1.66 0-3-1.34-3-3 0-1.57.88-3.08 2.25-3.83.39-.21.84.07.84.51v1.5c0 .83.67 1.5 1.5 1.5.44 0 .72.45.51.84A2.99 2.99 0 0 1 12 17z"/></svg>`;
const AIRPORT_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M22 16v-2l-8.5-5V3.5c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5V9L2 14v2l8.5-2.5V19L8 20.5V22l4-1 4 1v-1.5L13.5 19v-5.5L22 16z"/></svg>`;
const PORT_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M12 2c1.1 0 2 .9 2 2 0 .74-.4 1.38-1 1.72V7h4c1.1 0 2 .9 2 2v2h-2V9h-4v10.18c2.4-.41 4.38-2.12 4.88-4.48l1.96.42C21.14 20.31 17.02 23 12 23s-9.14-2.69-9.84-5.88l1.96-.42c.5 2.36 2.48 4.07 4.88 4.48V9H5v2H3V9c0-1.1.9-2 2-2h4V5.72C8.4 5.38 8 4.74 8 4c0-1.1.9-2 2-2zm0 2c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z"/></svg>`;
const SPACEPORT_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="%23ffffff"><path d="M13.13 22.19l-1.63-3.83c1.57-.58 3.04-1.5 4.31-2.77l2.55 3.32c-.57.88-1.28 1.68-2.11 2.37l-3.12.91zm-2.26 0l-3.12-.91c-.83-.69-1.54-1.49-2.11-2.37l2.55-3.32c1.27 1.27 2.74 2.19 4.31 2.77l-1.63 3.83zM12 2c3.5 3.5 5 7.5 5 12H7c0-4.5 1.5-8.5 5-12zm0 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/></svg>`;

const getBasemapStyle = (mode: BasemapMode): maplibregl.StyleSpecification => {
  if (mode === 'satellite-hybrid') {
    return {
      version: 8,
      sources: {
        'esri-imagery': {
          type: 'raster',
          tiles: [
            'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          attribution: 'Esri, Maxar, Earthstar Geographics',
        },
        'esri-reference': {
          type: 'raster',
          tiles: [
            'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
        },
      },
      layers: [
        { id: 'imagery-base', type: 'raster', source: 'esri-imagery', minzoom: 0, maxzoom: 20 },
        { id: 'imagery-ref', type: 'raster', source: 'esri-reference', minzoom: 0, maxzoom: 20 },
      ],
    };
  }

  if (mode === 'oceanic') {
    return {
      version: 8,
      sources: {
        'esri-ocean': {
          type: 'raster',
          tiles: [
            'https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          attribution: 'Esri, GEBCO, NOAA, National Geographic',
        },
        'esri-ocean-ref': {
          type: 'raster',
          tiles: [
            'https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
        },
      },
      layers: [
        { id: 'ocean-base', type: 'raster', source: 'esri-ocean', minzoom: 0, maxzoom: 20 },
        { id: 'ocean-ref', type: 'raster', source: 'esri-ocean-ref', minzoom: 0, maxzoom: 20 },
      ],
    };
  }

  // Default 'dark-tactical'
  return {
    version: 8,
    sources: {
      'esri-dark-base': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: 'Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
      },
      'esri-dark-reference': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
      },
    },
    layers: [
      { id: 'esri-dark-base-layer', type: 'raster', source: 'esri-dark-base', minzoom: 0, maxzoom: 20 },
      { id: 'esri-dark-reference-layer', type: 'raster', source: 'esri-dark-reference', minzoom: 0, maxzoom: 20 },
    ],
  };
};

export const MapEngine2D: React.FC<MapEngine2DProps> = ({
  layers,
  basemapMode,
  geometries,
  events,
  observations,
  alerts,
  aircraft = [],
  vessels = [],
  satellites = [],
  cameras = [],
  thermalEvents = [],
  infrastructure = [],
  selectedTrack = null,
  activeRoute = null,
  targetLocation,
  selectedItem = null,
  onViewportChange,
  onSelectItem,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

  // Initialize MapLibre GL JS map instance
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const initialStyle = getBasemapStyle(basemapMode);

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: initialStyle,
      center: [15.0, 20.0],
      zoom: 2.2,
      attributionControl: { compact: true },
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: true, showZoom: true }),
      'bottom-right'
    );

    const overlay = new MapboxOverlay({
      layers: [],
    });

    map.addControl(overlay as unknown as maplibregl.IControl);
    overlayRef.current = overlay;
    mapRef.current = map;

    const emitBounds = () => {
      const b = map.getBounds();
      onViewportChange({
        min_lon: Math.max(-180, Math.min(180, b.getWest())),
        min_lat: Math.max(-85, Math.min(85, b.getSouth())),
        max_lon: Math.max(-180, Math.min(180, b.getEast())),
        max_lat: Math.max(-85, Math.min(85, b.getNorth())),
      });
    };

    map.on('load', emitBounds);
    map.on('moveend', emitBounds);

    return () => {
      map.off('moveend', emitBounds);
      map.off('load', emitBounds);
      if (overlayRef.current) {
        try {
          map.removeControl(overlayRef.current as unknown as maplibregl.IControl);
        } catch {
          // ignore cleanup errors
        }
      }
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update basemap style when basemapMode changes
  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.setStyle(getBasemapStyle(basemapMode));
    }
  }, [basemapMode]);

  // Handle camera fly-to on targetLocation changes
  useEffect(() => {
    if (mapRef.current && targetLocation) {
      mapRef.current.flyTo({
        center: targetLocation.center,
        zoom: targetLocation.zoom ?? 4.5,
        essential: true,
      });
    }
  }, [targetLocation]);

  // Update Deck.gl layers whenever data or layer toggles change
  useEffect(() => {
    if (!overlayRef.current) return;

    const layerMap = new Map(layers.map((l) => [l.id, l.enabled]));
    const deckLayers: any[] = [];

    // 1. Sovereign Boundaries Layer (GeoJSON) - Strictly polygons/multipolygons
    if (layerMap.get('country-boundaries') && geometries.length > 0) {
      const boundaryGeoms = geometries.filter(
        (g) =>
          g.geometry &&
          (g.geometry.type === 'Polygon' || g.geometry.type === 'MultiPolygon') &&
          (g.geometry_kind === 'country_boundary' || g.geometry_kind === 'sovereign_state')
      );
      if (boundaryGeoms.length > 0) {
        deckLayers.push(
          new GeoJsonLayer({
            id: 'deck-boundaries',
            data: ({
              type: 'FeatureCollection',
              features: boundaryGeoms,
            } as any),
            pickable: true,
            stroked: true,
            filled: true,
            lineWidthMinPixels: 1.5,
            getLineColor: [61, 139, 255, 180],
            getFillColor: [61, 139, 255, 12],
            onClick: (info) => {
              if (info.object) {
                onSelectItem({ type: 'geometry', data: info.object });
              }
            },
          })
        );
      }
    }

    // Helper to safely extract verified coordinates
    const getEventCoords = (e: Event): [number, number] | null => {
      if (e.point && Array.isArray(e.point) && e.point.length >= 2) {
        const [lon, lat] = e.point;
        if (typeof lon === 'number' && typeof lat === 'number' && !isNaN(lon) && !isNaN(lat)) {
          if (lon !== 0 || lat !== 0) return [lon, lat];
        }
      }
      if (e.coordinates && Array.isArray(e.coordinates) && e.coordinates.length >= 2) {
        const [lon, lat] = e.coordinates;
        if (typeof lon === 'number' && typeof lat === 'number' && !isNaN(lon) && !isNaN(lat)) {
          if (lon !== 0 || lat !== 0) return [lon, lat];
        }
      }
      return null;
    };

    // 2. Seismic Events Layer (USGS Earthquakes)
    if (layerMap.get('earthquake-events') && events.length > 0) {
      const validSeismic = events.filter((e) => getEventCoords(e) !== null);
      if (validSeismic.length > 0) {
        deckLayers.push(
          new ScatterplotLayer({
            id: 'deck-earthquakes',
            data: validSeismic,
            pickable: true,
            opacity: 0.85,
            stroked: true,
            filled: true,
            radiusScale: 6,
            radiusMinPixels: 4,
            radiusMaxPixels: 22,
            lineWidthMinPixels: 1.5,
            getPosition: (d: Event) => getEventCoords(d)!,
            getRadius: (d: Event) => {
              const mag = d.magnitude ?? (d.attributes && (d.attributes.mag || d.attributes.magnitude)) ?? 3.5;
              return Math.max(12000, Math.pow(mag, 2.3) * 6000);
            },
            getFillColor: (d: Event) => {
              const mag = d.magnitude ?? (d.attributes && (d.attributes.mag || d.attributes.magnitude)) ?? 3.5;
              if (mag >= 6.0) return [239, 68, 68, 220]; // Red
              if (mag >= 4.5) return [249, 115, 22, 210]; // Orange
              return [234, 179, 8, 190]; // Yellow
            },
            getLineColor: [255, 255, 255, 220],
            onClick: (info) => {
              if (info.object) {
                onSelectItem({ type: 'event', data: info.object });
              }
            },
          })
        );
      }
    }

    // 3. Demographic Observations (Population)
    if (layerMap.get('population-observations') && observations.length > 0) {
      const popObs = observations.filter(
        (o) => o.measure?.includes('pop') || o.metric_name?.includes('pop')
      );
      if (popObs.length > 0) {
        deckLayers.push(
          new ScatterplotLayer({
            id: 'deck-population',
            data: popObs,
            pickable: true,
            opacity: 0.75,
            radiusScale: 8,
            radiusMinPixels: 3,
            radiusMaxPixels: 20,
            getPosition: (d: Observation) => {
              if (d.point && Array.isArray(d.point) && d.point.length >= 2) {
                return [d.point[0], d.point[1]];
              }
              return [0, 0];
            },
            getRadius: (d: Observation) => Math.sqrt(d.value_numeric || d.value || 10000) * 80,
            getFillColor: [43, 240, 200, 180],
            getLineColor: [11, 211, 211, 230],
            onClick: (info) => {
              if (info.object) {
                onSelectItem({ type: 'observation', data: info.object });
              }
            },
          })
        );
      }
    }

    // 4. Detected Anomalies
    if (layerMap.get('anomalies')) {
      const anomalyObs = observations.filter((o) => o.is_anomaly === true);
      if (anomalyObs.length > 0) {
        deckLayers.push(
          new ScatterplotLayer({
            id: 'deck-anomalies',
            data: anomalyObs,
            pickable: true,
            opacity: 0.9,
            stroked: true,
            lineWidthMinPixels: 2,
            radiusScale: 10,
            radiusMinPixels: 6,
            radiusMaxPixels: 28,
            getPosition: (d: Observation) => {
              if (d.point && Array.isArray(d.point) && d.point.length >= 2) {
                return [d.point[0], d.point[1]];
              }
              return [0, 0];
            },
            getRadius: 45000,
            getFillColor: [250, 204, 21, 190],
            getLineColor: [255, 255, 255, 240],
            onClick: (info) => {
              if (info.object) {
                onSelectItem({ type: 'observation', data: info.object });
              }
            },
          })
        );
      }
    }

    // 5. Tactical Alerts
    if (layerMap.get('system-alerts') && alerts.length > 0) {
      deckLayers.push(
        new ScatterplotLayer({
          id: 'deck-alerts',
          data: alerts,
          pickable: true,
          opacity: 0.95,
          stroked: true,
          lineWidthMinPixels: 2,
          radiusMinPixels: 7,
          radiusMaxPixels: 30,
          getPosition: (d: Alert) => {
            if (d.point && Array.isArray(d.point) && d.point.length >= 2) {
              return [d.point[0], d.point[1]];
            }
            return [0, 0];
          },
          getRadius: 60000,
          getFillColor: [244, 63, 94, 230],
          getLineColor: [255, 255, 255, 240],
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'alert', data: info.object });
            }
          },
        })
      );
    }

    // 6. Live Aircraft State Vectors with Heading-Aware Rotation
    if (layerMap.get('aircraft-states') && aircraft.length > 0) {
      const validAircraft = aircraft.filter(
        (a) =>
          typeof a.longitude === 'number' &&
          typeof a.latitude === 'number' &&
          !isNaN(a.longitude) &&
          !isNaN(a.latitude)
      );

      deckLayers.push(
        new IconLayer({
          id: 'deck-aircraft-icons',
          data: validAircraft,
          pickable: true,
          getPosition: (d: AircraftState) => [d.longitude, d.latitude],
          getIcon: () => ({
            url: AIRPLANE_SVG,
            width: 24,
            height: 24,
            mask: true,
          }),
          getSize: 22,
          getAngle: (d: AircraftState) => 360 - (d.attributes?.true_track || 0),
          getColor: (d: AircraftState) =>
            d.attributes?.on_ground ? [148, 163, 184, 230] : [56, 189, 248, 255],
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'aircraft', data: info.object });
            }
          },
        })
      );
    }

    // 7. Maritime Vessels with Course/Heading Rotation
    if (layerMap.get('maritime-vessels') && vessels.length > 0) {
      deckLayers.push(
        new IconLayer({
          id: 'deck-vessel-icons',
          data: vessels,
          pickable: true,
          getPosition: (d: VesselState) => [d.longitude, d.latitude],
          getIcon: () => ({
            url: VESSEL_SVG,
            width: 24,
            height: 24,
            mask: true,
          }),
          getSize: 22,
          getAngle: (d: VesselState) =>
            360 - (d.attributes?.heading_degrees || d.attributes?.cog_degrees || 0),
          getColor: [6, 182, 212, 255], // Cyan
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'vessel', data: info.object });
            }
          },
        })
      );
    }

    // 8. Space Satellites & Orbital Ground Tracks
    if (layerMap.get('space-satellites') && satellites.length > 0) {
      // ONLY predicted orbital ground tracks for selected satellite!
      // Suppresses disturbing multi-orbit purple grid across the map.
      if (selectedItem?.type === 'satellite') {
        const selectedSat = satellites.find(
          (s) =>
            s.entity_id === selectedItem.data?.entity_id ||
            (s.attributes?.norad_id && s.attributes.norad_id === selectedItem.data?.attributes?.norad_id)
        );
        if (selectedSat?.attributes?.ground_track && selectedSat.attributes.ground_track.length > 1) {
          deckLayers.push(
            new PathLayer({
              id: 'deck-satellite-ground-track-selected',
              data: [selectedSat],
              pickable: false,
              widthMinPixels: 2.5,
              getPath: (d: SatelliteState) => d.attributes.ground_track!,
              getColor: [192, 132, 252, 210], // Soft glowing purple
            })
          );
        }
      }

      deckLayers.push(
        new IconLayer({
          id: 'deck-satellite-icons',
          data: satellites,
          pickable: true,
          getPosition: (d: SatelliteState) => [d.longitude, d.latitude],
          getIcon: () => ({
            url: SATELLITE_SVG,
            width: 24,
            height: 24,
            mask: true,
          }),
          getSize: (d: SatelliteState) =>
            selectedItem?.type === 'satellite' && selectedItem.data?.entity_id === d.entity_id ? 28 : 22,
          getColor: [168, 85, 247, 255], // Purple
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'satellite', data: info.object });
            }
          },
        })
      );
    }

    // 9. Surveillance & Sensor Cameras
    if (layerMap.get('surveillance-cameras') && cameras.length > 0) {
      deckLayers.push(
        new IconLayer({
          id: 'deck-camera-icons',
          data: cameras,
          pickable: true,
          getPosition: (d: CameraEntity) => [d.longitude, d.latitude],
          getIcon: () => ({
            url: CAMERA_SVG,
            width: 24,
            height: 24,
            mask: true,
          }),
          getSize: (d: CameraEntity) =>
            selectedItem?.type === 'camera' && selectedItem.data?.entity_id === d.entity_id ? 28 : 22,
          getColor: [16, 185, 129, 255], // Emerald green
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'camera', data: info.object });
            }
          },
        })
      );
    }

    // 10. Thermal Anomalies & Wildfires (NASA FIRMS)
    if (layerMap.get('thermal-fires') && thermalEvents.length > 0) {
      deckLayers.push(
        new IconLayer({
          id: 'deck-fire-icons',
          data: thermalEvents,
          pickable: true,
          getPosition: (d: ThermalAnomalyEvent) => [d.longitude, d.latitude],
          getIcon: () => ({
            url: FIRE_SVG,
            width: 24,
            height: 24,
            mask: true,
          }),
          getSize: (d: ThermalAnomalyEvent) =>
            Math.min(32, Math.max(18, 14 + (d.attributes?.frp_mw || 10) * 0.15)),
          getColor: (d: ThermalAnomalyEvent) =>
            d.attributes?.confidence_level === 'high' ? [239, 68, 68, 255] : [249, 115, 22, 230],
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'fire', data: info.object });
            }
          },
        })
      );
    }

    // 11. Strategic Critical Infrastructure (Airports, Seaports, Spaceports)
    if (layerMap.get('critical-infrastructure') && infrastructure.length > 0) {
      deckLayers.push(
        new IconLayer({
          id: 'deck-infrastructure-icons',
          data: infrastructure,
          pickable: true,
          getPosition: (d: InfrastructureNode) => [d.longitude, d.latitude],
          getIcon: (d: InfrastructureNode) => {
            const type = d.attributes?.node_type;
            const url =
              type === 'airport'
                ? AIRPORT_SVG
                : type === 'spaceport'
                ? SPACEPORT_SVG
                : PORT_SVG;
            return { url, width: 24, height: 24, mask: true };
          },
          getSize: 22,
          getColor: (d: InfrastructureNode) => {
            const type = d.attributes?.node_type;
            if (type === 'spaceport') return [236, 72, 153, 255]; // Pink
            if (type === 'airport') return [234, 179, 8, 255]; // Yellow
            return [59, 130, 246, 255]; // Blue
          },
          onClick: (info) => {
            if (info.object) {
              onSelectItem({ type: 'infrastructure', data: info.object });
            }
          },
        })
      );
    }

    // 12. Selected Entity Historical Track Polyline
    if (selectedTrack && selectedTrack.length > 1) {
      deckLayers.push(
        new PathLayer({
          id: 'deck-selected-track-line',
          data: [{ path: selectedTrack.map((p) => [p.longitude, p.latitude]) }],
          pickable: false,
          widthMinPixels: 3,
          getPath: (d) => d.path,
          getColor: [56, 189, 248, 240], // Vivid sky-blue track
        })
      );
    }

    // 13. Strategic Multi-Modal Route (Phase 1)
    if (activeRoute && activeRoute.waypoints.length > 1) {
      const routeColor: [number, number, number, number] =
        activeRoute.mode === 'air'
          ? [6, 182, 212, 240] // Neon Cyan
          : activeRoute.mode === 'sea'
          ? [16, 185, 129, 240] // Emerald Green
          : [245, 158, 11, 240]; // Amber Gold

      deckLayers.push(
        new PathLayer({
          id: 'deck-strategic-route-path',
          data: [{ path: activeRoute.waypoints.map((w) => [w.lon, w.lat]) }],
          pickable: true,
          widthMinPixels: 4,
          getPath: (d) => d.path,
          getColor: routeColor,
        })
      );

      deckLayers.push(
        new ScatterplotLayer({
          id: 'deck-route-endpoints',
          data: [
            { pos: [activeRoute.origin.longitude, activeRoute.origin.latitude], isOrigin: true },
            { pos: [activeRoute.destination.longitude, activeRoute.destination.latitude], isOrigin: false },
          ],
          pickable: true,
          getPosition: (d: any) => d.pos,
          getRadius: 45000,
          radiusMinPixels: 7,
          radiusMaxPixels: 20,
          getFillColor: (d: any) => (d.isOrigin ? [6, 182, 212, 230] : [16, 185, 129, 230]),
          getLineColor: [255, 255, 255, 255],
          stroked: true,
          lineWidthMinPixels: 2,
        })
      );
    }

    overlayRef.current.setProps({
      layers: deckLayers,
    });
  }, [
    layers,
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
    selectedTrack,
    activeRoute,
    selectedItem,
    onSelectItem,
  ]);

  return <div ref={mapContainerRef} className="map-container-2d" />;
};
