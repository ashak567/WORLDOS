import React, { useEffect, useRef } from 'react';
import {
  Cartesian3,
  Color,
  GeoJsonDataSource,
  Ion,
  Math as CesiumMath,
  PolylineGlowMaterialProperty,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Viewer,
  defined,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
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
} from '../api';
import { BasemapMode, LayerDefinition } from '../types/layers';
import { SelectedItemPayload } from './MapEngine2D';

// Cesium asset base path configuration
(window as any).CESIUM_BASE_URL = '/cesium/';
Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? '';

interface GlobeEngine3DProps {
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
  targetLocation?: { center: [number, number]; zoom?: number } | null;
  onViewportChange: (bbox: BoundingBox) => void;
  onSelectItem: (item: SelectedItemPayload) => void;
}

export const GlobeEngine3D: React.FC<GlobeEngine3DProps> = ({
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
  targetLocation,
  onViewportChange,
  onSelectItem,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const geojsonSourceRef = useRef<GeoJsonDataSource | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);

  const applyImageryLayers = (viewer: Viewer, mode: BasemapMode) => {
    try {
      viewer.imageryLayers.removeAll();

      if (mode === 'satellite-hybrid') {
        const satImagery = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 18,
        });
        viewer.imageryLayers.addImageryProvider(satImagery);

        const refOverlay = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 18,
        });
        viewer.imageryLayers.addImageryProvider(refOverlay);
        viewer.scene.globe.baseColor = Color.fromCssColorString('#020617');
        return;
      }

      if (mode === 'oceanic') {
        const oceanBase = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 16,
        });
        viewer.imageryLayers.addImageryProvider(oceanBase);

        const oceanRef = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 16,
        });
        viewer.imageryLayers.addImageryProvider(oceanRef);
        viewer.scene.globe.baseColor = Color.fromCssColorString('#031024');
        return;
      }

      // Default 'dark-tactical'
      const darkImagery = new UrlTemplateImageryProvider({
        url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 16,
      });
      viewer.imageryLayers.addImageryProvider(darkImagery);

      const darkRef = new UrlTemplateImageryProvider({
        url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 16,
      });
      viewer.imageryLayers.addImageryProvider(darkRef);
      viewer.scene.globe.baseColor = Color.fromCssColorString('#0a0e17');
    } catch {
      // Graceful fallback
    }
  };

  // Initialize Cesium Globe Viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    const viewer = new Viewer(containerRef.current, {
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      infoBox: false,
      selectionIndicator: false,
    });

    applyImageryLayers(viewer, basemapMode);

    // Initial camera view
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(20.0, 20.0, 18_000_000),
    });

    const emitCameraBounds = () => {
      try {
        const rectangle = viewer.camera.computeViewRectangle();
        if (rectangle) {
          const west = CesiumMath.toDegrees(rectangle.west);
          const south = CesiumMath.toDegrees(rectangle.south);
          const east = CesiumMath.toDegrees(rectangle.east);
          const north = CesiumMath.toDegrees(rectangle.north);
          onViewportChange({
            min_lon: Math.max(-180, Math.min(180, west)),
            min_lat: Math.max(-85, Math.min(85, south)),
            max_lon: Math.max(-180, Math.min(180, east)),
            max_lat: Math.max(-85, Math.min(85, north)),
          });
        }
      } catch {
        // computeViewRectangle may return undefined if camera looking away from horizon
      }
    };

    viewer.camera.moveEnd.addEventListener(emitCameraBounds);
    emitCameraBounds();

    // Screen-space click picking handler
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((movement: { position: any }) => {
      const picked = viewer.scene.pick(movement.position);
      if (defined(picked) && picked.id) {
        const entity = picked.id;
        if (entity._worldosType && entity._worldosData) {
          onSelectItem({
            type: entity._worldosType,
            data: entity._worldosData,
          });
        }
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    handlerRef.current = handler;
    viewerRef.current = viewer;

    return () => {
      viewer.camera.moveEnd.removeEventListener(emitCameraBounds);
      if (handlerRef.current) {
        handlerRef.current.destroy();
        handlerRef.current = null;
      }
      viewer.destroy();
      viewerRef.current = null;
    };
  }, []);

  // Update imagery provider on basemapMode changes
  useEffect(() => {
    if (viewerRef.current) {
      applyImageryLayers(viewerRef.current, basemapMode);
    }
  }, [basemapMode]);

  // Handle camera fly-to on targetLocation changes
  useEffect(() => {
    if (viewerRef.current && targetLocation) {
      const [lon, lat] = targetLocation.center;
      const zoom = targetLocation.zoom ?? 4.5;
      const height = Math.max(50_000, 20_000_000 / Math.pow(2, zoom - 1));
      viewerRef.current.camera.flyTo({
        destination: Cartesian3.fromDegrees(lon, lat, height),
        duration: 1.5,
      });
    }
  }, [targetLocation]);

  // Synchronize Sovereign Boundaries
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const boundariesEnabled = layers.find((l) => l.id === 'country-boundaries')?.enabled ?? true;

    if (!boundariesEnabled || geometries.length === 0) {
      if (geojsonSourceRef.current) {
        viewer.dataSources.remove(geojsonSourceRef.current, true);
        geojsonSourceRef.current = null;
      }
      return;
    }

    const boundaryGeoms = geometries.filter(
      (g) =>
        g.geometry &&
        (g.geometry.type === 'Polygon' || g.geometry.type === 'MultiPolygon') &&
        (g.geometry_kind === 'country_boundary' || g.geometry_kind === 'sovereign_state')
    );

    if (boundaryGeoms.length === 0) return;

    const featureCollection: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: boundaryGeoms.map((g) => ({
        type: 'Feature' as const,
        geometry: g.geometry,
        properties: {
          id: g.id,
          entity_id: g.entity_id,
          canonical_name: g.canonical_name,
          geometry_kind: g.geometry_kind,
          source_slug: g.source_slug,
        },
      })),
    };

    GeoJsonDataSource.load(featureCollection, {
      stroke: Color.fromCssColorString('#3d8bff'),
      strokeWidth: 1.5,
      fill: Color.fromCssColorString('#3d8bff').withAlpha(0.04),
      clampToGround: true,
    })
      .then((ds) => {
        if (geojsonSourceRef.current) {
          viewer.dataSources.remove(geojsonSourceRef.current, true);
        }
        for (const ent of ds.entities.values) {
          ent.billboard = undefined as any;
          if (ent.polygon) {
            ent.polygon.material = Color.fromCssColorString('#3d8bff').withAlpha(0.04) as any;
            ent.polygon.outlineColor = Color.fromCssColorString('#3d8bff') as any;
            ent.polygon.outlineWidth = 1.5 as any;
          }
        }
        geojsonSourceRef.current = ds;
        viewer.dataSources.add(ds);
      })
      .catch(() => {});
  }, [layers, geometries]);

  // Synchronize Multi-Domain 3D Entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    viewer.entities.removeAll();
    const layerMap = new Map(layers.map((l) => [l.id, l.enabled]));

    // 1. Aircraft: Placed at true barometric / geometric altitude in 3D
    if (layerMap.get('aircraft-states') && aircraft.length > 0) {
      for (const a of aircraft) {
        if (
          typeof a.longitude !== 'number' ||
          typeof a.latitude !== 'number' ||
          isNaN(a.longitude) ||
          isNaN(a.latitude)
        ) {
          continue;
        }

        // True altitude in meters (clamped between 150m and 15,000m)
        const altMeters = Math.max(
          150,
          Math.min(15000, a.attributes?.geo_altitude || a.attributes?.baro_altitude || 10000)
        );
        const position = Cartesian3.fromDegrees(a.longitude, a.latitude, altMeters);
        const isGround = a.attributes?.on_ground ?? false;

        const ent = viewer.entities.add({
          position,
          point: {
            pixelSize: isGround ? 6 : 8,
            color: isGround
              ? Color.fromCssColorString('#94a3b8')
              : Color.fromCssColorString('#38bdf8'),
            outlineColor: Color.WHITE,
            outlineWidth: 1.5,
          },
        });
        (ent as any)._worldosType = 'aircraft';
        (ent as any)._worldosData = a;
      }
    }

    // 2. Maritime Vessels: Water-clamped at altitude 0
    if (layerMap.get('maritime-vessels') && vessels.length > 0) {
      for (const v of vessels) {
        const position = Cartesian3.fromDegrees(v.longitude, v.latitude, 0);
        const ent = viewer.entities.add({
          position,
          point: {
            pixelSize: 8,
            color: Color.fromCssColorString('#06b6d4'),
            outlineColor: Color.WHITE,
            outlineWidth: 1.5,
          },
        });
        (ent as any)._worldosType = 'vessel';
        (ent as any)._worldosData = v;
      }
    }

    // 3. Space Satellites: True 3D Orbital Altitude (400 km to 20,200 km) + 3D Orbital Ring
    if (layerMap.get('space-satellites') && satellites.length > 0) {
      for (const s of satellites) {
        const altMeters = (s.attributes?.altitude_km || 420) * 1000;
        const position = Cartesian3.fromDegrees(s.longitude, s.latitude, altMeters);

        const ent = viewer.entities.add({
          position,
          point: {
            pixelSize: 10,
            color: Color.fromCssColorString('#a855f7'),
            outlineColor: Color.WHITE,
            outlineWidth: 2,
          },
        });
        (ent as any)._worldosType = 'satellite';
        (ent as any)._worldosData = s;

        // 3D Orbital ground track
        if (s.attributes?.ground_track && s.attributes.ground_track.length > 1) {
          const trackPositions = s.attributes.ground_track.map(([lon, lat]) =>
            Cartesian3.fromDegrees(lon, lat, altMeters)
          );
          viewer.entities.add({
            polyline: {
              positions: trackPositions,
              width: 1.5,
              material: Color.fromCssColorString('#a855f7').withAlpha(0.4),
            },
          });
        }
      }
    }

    // 4. Surveillance & Sensor Cameras: Ground-clamped
    if (layerMap.get('surveillance-cameras') && cameras.length > 0) {
      for (const c of cameras) {
        const position = Cartesian3.fromDegrees(c.longitude, c.latitude, 0);
        const ent = viewer.entities.add({
          position,
          point: {
            pixelSize: 8,
            color: Color.fromCssColorString('#10b981'),
            outlineColor: Color.WHITE,
            outlineWidth: 1.5,
          },
        });
        (ent as any)._worldosType = 'camera';
        (ent as any)._worldosData = c;
      }
    }

    // 5. Thermal Anomalies & Wildfires (NASA FIRMS): Ground-clamped with glowing size
    if (layerMap.get('thermal-fires') && thermalEvents.length > 0) {
      for (const f of thermalEvents) {
        const position = Cartesian3.fromDegrees(f.longitude, f.latitude, 0);
        const size = Math.min(18, Math.max(8, 6 + (f.attributes?.frp_mw || 10) * 0.08));
        const ent = viewer.entities.add({
          position,
          point: {
            pixelSize: size,
            color:
              f.attributes?.confidence_level === 'high'
                ? Color.fromCssColorString('#ef4444')
                : Color.fromCssColorString('#f97316'),
            outlineColor: Color.WHITE,
            outlineWidth: 1.5,
          },
        });
        (ent as any)._worldosType = 'fire';
        (ent as any)._worldosData = f;
      }
    }

    // 6. Seismic Events (USGS Earthquakes)
    if (layerMap.get('earthquake-events') && events.length > 0) {
      for (const e of events) {
        const coords = e.point || e.coordinates;
        if (!coords || coords.length < 2) continue;
        const [lon, lat] = coords;
        if (typeof lon !== 'number' || typeof lat !== 'number' || (lon === 0 && lat === 0)) continue;

        const mag = e.magnitude ?? (e.attributes && (e.attributes.mag || e.attributes.magnitude)) ?? 3.5;
        const color =
          mag >= 6.0
            ? Color.fromCssColorString('#ef4444')
            : mag >= 4.5
            ? Color.fromCssColorString('#f97316')
            : Color.fromCssColorString('#eab308');

        const ent = viewer.entities.add({
          position: Cartesian3.fromDegrees(lon, lat, 0),
          point: {
            pixelSize: Math.max(6, Math.min(22, mag * 3)),
            color,
            outlineColor: Color.WHITE,
            outlineWidth: 1.5,
          },
        });
        (ent as any)._worldosType = 'event';
        (ent as any)._worldosData = e;
      }
    }

    // 7. Critical Infrastructure (Airports, Seaports, Spaceports)
    if (layerMap.get('critical-infrastructure') && infrastructure.length > 0) {
      for (const node of infrastructure) {
        const position = Cartesian3.fromDegrees(node.longitude, node.latitude, Math.max(0, node.attributes?.elevation_m || 0));
        const type = node.attributes?.node_type;
        const color =
          type === 'spaceport'
            ? Color.fromCssColorString('#ec4899')
            : type === 'airport'
            ? Color.fromCssColorString('#eab308')
            : Color.fromCssColorString('#3b82f6');

        const ent = viewer.entities.add({
          position,
          point: {
            pixelSize: 9,
            color,
            outlineColor: Color.WHITE,
            outlineWidth: 1.5,
          },
        });
        (ent as any)._worldosType = 'infrastructure';
        (ent as any)._worldosData = node;
      }
    }

    // 8. Selected Entity Historical Track in 3D
    if (selectedTrack && selectedTrack.length > 1) {
      const trackPositions = selectedTrack.map((p) =>
        Cartesian3.fromDegrees(
          p.longitude,
          p.latitude,
          Math.max(150, p.attributes?.geo_altitude || p.attributes?.baro_altitude || 10000)
        )
      );
      viewer.entities.add({
        polyline: {
          positions: trackPositions,
          width: 3,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.3,
            color: Color.fromCssColorString('#38bdf8'),
          }),
        },
      });
    }
  }, [
    layers,
    aircraft,
    vessels,
    satellites,
    cameras,
    thermalEvents,
    events,
    observations,
    alerts,
    infrastructure,
    selectedTrack,
  ]);

  return <div ref={containerRef} className="globe-container-3d" />;
};
