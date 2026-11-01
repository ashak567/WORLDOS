import React, { useEffect, useRef } from 'react';
import {
  Cartesian3,
  BillboardCollection,
  Cesium3DTileset,
  Color,
  ConstantProperty,
  GeoJsonDataSource,
  Ion,
  IonGeocodeProviderType,
  Math as CesiumMath,
  NearFarScalar,
  PolylineGlowMaterialProperty,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Viewer,
  createGooglePhotorealistic3DTileset,
  createWorldTerrainAsync,
  defined,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import {
  AIRPLANE_ICON_BLUE,
  AIRPLANE_ICON_GROUND,
  VESSEL_ICON_CYAN,
  SATELLITE_ICON_PURPLE,
  CAMERA_ICON_EMERALD,
  FIRE_ICON_ORANGE,
  FIRE_ICON_RED,
  AIRPORT_ICON_BLUE,
  PORT_ICON_TEAL,
  SPACEPORT_ICON_ROSE,
} from '../utils/icons';
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
  splitTrackAtAntimeridian,
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
  naturalEvents?: Event[];
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
  onViewportChange: (bbox: BoundingBox, zoom?: number) => void;
  onSelectItem: (item: SelectedItemPayload) => void;
}

export const GlobeEngine3D: React.FC<GlobeEngine3DProps> = ({
  layers,
  basemapMode,
  geometries,
  events,
  naturalEvents = [],
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
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const googleTilesetRef = useRef<Cesium3DTileset | null>(null);
  const imageryRequestRef = useRef(0);
  const terrainPromiseRef = useRef<ReturnType<typeof createWorldTerrainAsync> | null>(null);
  const geojsonSourceRef = useRef<GeoJsonDataSource | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const selectedHighlightRef = useRef<{ entity: any; billboard?: any; width: number; height: number; tracks: any[] } | null>(null);
  const selectedAircraftTrackRef = useRef<any>(null);
  const aircraftBillboardsRef = useRef<BillboardCollection | null>(null);
  const satelliteBillboardsRef = useRef<BillboardCollection | null>(null);

  const applyImageryLayers = (viewer: Viewer, mode: BasemapMode, allowGoogleTiles = true) => {
    const requestId = ++imageryRequestRef.current;
    try {
      if (googleTilesetRef.current) {
        viewer.scene.primitives.remove(googleTilesetRef.current);
        googleTilesetRef.current = null;
      }
      viewer.imageryLayers.removeAll();

      if (mode === 'satellite-hybrid' && Ion.defaultAccessToken && allowGoogleTiles) {
        // Keep the raster globe visible while the photorealistic tileset loads.
        applyImageryLayers(viewer, mode, false);
        const googleRequestId = imageryRequestRef.current;
        createGooglePhotorealistic3DTileset(
          { onlyUsingWithGoogleGeocoder: true },
          { showCreditsOnScreen: true }
        ).then((tileset) => {
          if (viewer.isDestroyed() || googleRequestId !== imageryRequestRef.current) {
            tileset.destroy();
            return;
          }
          googleTilesetRef.current = tileset;
          viewer.scene.primitives.add(tileset);
          viewer.scene.requestRender();
        }).catch(() => {});
        return;
      }

      viewer.scene.globe.show = true;
      if (mode === 'satellite-hybrid') {
        viewer.imageryLayers.addImageryProvider(new UrlTemplateImageryProvider({
          url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          maximumLevel: 19,
          credit: '© OpenStreetMap contributors',
        }));
        const satImagery = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 20,
          credit: 'Esri, Maxar, Earthstar Geographics',
        });
        viewer.imageryLayers.addImageryProvider(satImagery);

        const refOverlay = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 20,
        });
        viewer.imageryLayers.addImageryProvider(refOverlay);
        viewer.scene.globe.baseColor = Color.fromCssColorString('#020617');
        viewer.scene.requestRender();
        return;
      }

      if (mode === 'oceanic') {
        viewer.imageryLayers.addImageryProvider(new UrlTemplateImageryProvider({
          url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          maximumLevel: 19,
          credit: '© OpenStreetMap contributors',
        }));
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
        viewer.scene.requestRender();
        return;
      }

      // Default 'dark-tactical'
      viewer.imageryLayers.addImageryProvider(new UrlTemplateImageryProvider({
        url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        maximumLevel: 19,
        credit: '© OpenStreetMap contributors',
      }));
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
      viewer.scene.requestRender();
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
      geocoder: IonGeocodeProviderType.GOOGLE,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      infoBox: false,
      selectionIndicator: false,
      targetFrameRate: 30,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
    });

    applyImageryLayers(viewer, basemapMode);
    viewer.scene.globe.enableLighting = true;

    // Initial camera view
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(20.0, 20.0, 18_000_000),
    });
    viewer.scene.requestRender();

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
          }, 1 + Math.log2(20_000_000 / Math.max(viewer.camera.positionCartographic.height, 1)));
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
      if (viewerRef.current === viewer) viewerRef.current = null;
      geojsonSourceRef.current = null;
      googleTilesetRef.current = null;
      selectedHighlightRef.current = null;
      selectedAircraftTrackRef.current = null;
      aircraftBillboardsRef.current = null;
      satelliteBillboardsRef.current = null;
      viewer.destroy();
    };
  }, []);

  // Update imagery provider on basemapMode changes
  useEffect(() => {
    if (viewerRef.current) {
      applyImageryLayers(viewerRef.current, basemapMode);
      if (basemapMode !== 'satellite-hybrid' && Ion.defaultAccessToken) {
        terrainPromiseRef.current ??= createWorldTerrainAsync();
        terrainPromiseRef.current
          .then((terrainProvider) => {
            const viewer = viewerRef.current;
            if (viewer && !viewer.isDestroyed()) {
              viewer.terrainProvider = terrainProvider;
              viewer.scene.requestRender();
            }
          })
          .catch(() => {});
      }
    }
  }, [basemapMode]);

  // Handle camera fly-to on targetLocation changes
  useEffect(() => {
    if (viewerRef.current && targetLocation) {
      const [lon, lat] = targetLocation.center;
      const zoom = targetLocation.zoom ?? 4.5;
      const height = Math.max(1_000, 20_000_000 / Math.pow(2, zoom - 1));
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
        viewer.scene.requestRender();
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
        if (viewer.isDestroyed() || viewerRef.current !== viewer) {
          ds.destroy();
          return;
        }
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
        viewer.scene.requestRender();
      })
      .catch(() => {});
  }, [layers, geometries]);

  // Synchronize Multi-Domain 3D Entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    viewer.entities.removeAll();
    const layerMap = new Map(layers.map((l) => [l.id, l.enabled]));

    const aircraftBillboards = aircraftBillboardsRef.current ?? viewer.scene.primitives.add(new BillboardCollection());
    const satelliteBillboards = satelliteBillboardsRef.current ?? viewer.scene.primitives.add(new BillboardCollection());
    aircraftBillboardsRef.current = aircraftBillboards;
    satelliteBillboardsRef.current = satelliteBillboards;
    aircraftBillboards.removeAll();
    satelliteBillboards.removeAll();

    // Batch the high-volume feeds into Cesium billboard collections instead of thousands of Entity objects.
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

        aircraftBillboards.add({
          id: { _worldosType: 'aircraft', _worldosData: a },
          position,
          image: isGround ? AIRPLANE_ICON_GROUND : AIRPLANE_ICON_BLUE,
          rotation: CesiumMath.toRadians(360 - (a.attributes?.true_track || 0)),
          width: 24,
          height: 24,
          scaleByDistance: new NearFarScalar(1.5e2, 1.2, 1.5e7, 0.45),
        });
      }
    }

    // 2. Maritime Vessels: Water-clamped at altitude 0 with Heading Rotation
    if (layerMap.get('maritime-vessels') && vessels.length > 0) {
      for (const v of vessels) {
        const position = Cartesian3.fromDegrees(v.longitude, v.latitude, 0);
        const heading = v.attributes?.heading_degrees ?? v.attributes?.cog_degrees ?? 0;
        const ent = viewer.entities.add({
          position,
          billboard: {
            image: VESSEL_ICON_CYAN,
            rotation: CesiumMath.toRadians(360 - heading),
            width: 22,
            height: 22,
            scaleByDistance: new NearFarScalar(1.5e2, 1.2, 1.0e7, 0.5),
          },
        });
        (ent as any)._worldosType = 'vessel';
        (ent as any)._worldosData = v;
      }
    }

    // 3. Space Satellites: True 3D Orbital Altitude (400 km to 20,200 km)
    if (layerMap.get('space-satellites') && satellites.length > 0) {
      for (const s of satellites) {
        const altitudeKm = s.attributes?.altitude_km;
        if (!Number.isFinite(altitudeKm)) continue;
        const altMeters = altitudeKm * 1000;
        const position = Cartesian3.fromDegrees(s.longitude, s.latitude, altMeters);

        satelliteBillboards.add({
          id: { _worldosType: 'satellite', _worldosData: s },
          position,
          image: SATELLITE_ICON_PURPLE,
          width: 5,
          height: 5,
          scaleByDistance: new NearFarScalar(5.0e5, 1.3, 5.0e7, 0.65),
        });
      }
    }

    if (layerMap.get('natural-hazards') && naturalEvents.length > 0) {
      for (const event of naturalEvents) {
        const point = event.point || event.coordinates;
        if (!point || point.length < 2 || !point.every(Number.isFinite)) continue;
        const categories = `${event.category || ''} ${(event.attributes?.categories || []).join(' ')}`.toLowerCase();
        const alertLevel = String(event.attributes?.alert_level || '').toLowerCase();
        const color = alertLevel === 'red' ? Color.RED
          : alertLevel === 'orange' ? Color.ORANGE
          : alertLevel === 'green' ? Color.LIME
          : categories.includes('tsunami') ? Color.CYAN
          : categories.includes('storm') ? Color.DEEPSKYBLUE
          : categories.includes('fire') ? Color.ORANGE
            : categories.includes('volcano') ? Color.RED
              : categories.includes('flood') ? Color.CYAN
                : Color.HOTPINK;
        const ent = viewer.entities.add({
          position: Cartesian3.fromDegrees(point[0], point[1], 0),
          point: { pixelSize: 8, color, outlineColor: Color.WHITE, outlineWidth: 1 },
        });
        (ent as any)._worldosType = 'event';
        (ent as any)._worldosData = event;
      }
    }

    // 4. Surveillance & Sensor Cameras: Ground-clamped with Camera Icon
    if (layerMap.get('surveillance-cameras') && cameras.length > 0) {
      for (const c of cameras) {
        const position = Cartesian3.fromDegrees(c.longitude, c.latitude, 0);
        const ent = viewer.entities.add({
          position,
          billboard: {
            image: CAMERA_ICON_EMERALD,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(1.5e2, 1.3, 2.0e7, 0.55),
          },
        });
        (ent as any)._worldosType = 'camera';
        (ent as any)._worldosData = c;
      }
    }

    // 5. Thermal Anomalies & Wildfires (NASA FIRMS): Ground-clamped Flame Icon
    if (layerMap.get('thermal-fires') && thermalEvents.length > 0) {
      for (const f of thermalEvents) {
        const position = Cartesian3.fromDegrees(f.longitude, f.latitude, 0);
        const ent = viewer.entities.add({
          position,
          billboard: {
            image: f.attributes?.confidence_level === 'high' ? FIRE_ICON_RED : FIRE_ICON_ORANGE,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(1.5e2, 1.2, 8.0e6, 0.45),
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
        const icon =
          type === 'spaceport'
            ? SPACEPORT_ICON_ROSE
            : type === 'airport'
            ? AIRPORT_ICON_BLUE
            : PORT_ICON_TEAL;

        const ent = viewer.entities.add({
          position,
          billboard: {
            image: icon,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(1.5e2, 1.2, 1.0e7, 0.45),
          },
        });
        (ent as any)._worldosType = 'infrastructure';
        (ent as any)._worldosData = node;
      }
    }

    // 9. Strategic Multi-Modal Route in 3D Geodesic Space (Phase 1)
    if (activeRoute && activeRoute.waypoints.length > 1) {
      const routePositions = activeRoute.waypoints.map((w) =>
        Cartesian3.fromDegrees(w.lon, w.lat, Math.max(100, w.altitude_m))
      );
      const glowColor =
        activeRoute.mode === 'air'
          ? Color.fromCssColorString('#06b6d4') // Neon Cyan
          : activeRoute.mode === 'sea'
          ? Color.fromCssColorString('#10b981') // Emerald
          : Color.fromCssColorString('#f59e0b'); // Amber

      viewer.entities.add({
        name: `Strategic Route ${activeRoute.origin.code} - ${activeRoute.destination.code}`,
        polyline: {
          positions: routePositions,
          width: activeRoute.mode === 'air' ? 5 : 4,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.35,
            color: glowColor,
          }),
        },
      });

      // Origin Point
      viewer.entities.add({
        position: Cartesian3.fromDegrees(activeRoute.origin.longitude, activeRoute.origin.latitude, 500),
        point: {
          pixelSize: 12,
          color: Color.fromCssColorString('#06b6d4'),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
      });

      // Destination Point
      viewer.entities.add({
        position: Cartesian3.fromDegrees(activeRoute.destination.longitude, activeRoute.destination.latitude, 500),
        point: {
          pixelSize: 12,
          color: Color.fromCssColorString('#10b981'),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
      });
    }
    viewer.scene.requestRender();
  }, [
    layers,
    aircraft,
    vessels,
    satellites,
    cameras,
    thermalEvents,
    events,
    naturalEvents,
    observations,
    alerts,
    infrastructure,
    activeRoute,
  ]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    if (selectedAircraftTrackRef.current) viewer.entities.remove(selectedAircraftTrackRef.current);
    selectedAircraftTrackRef.current = null;
    if (selectedTrack && selectedTrack.length > 1) {
      const positions = selectedTrack.map((point) => Cartesian3.fromDegrees(
        point.longitude,
        point.latitude,
        Math.max(150, point.attributes?.geo_altitude || point.attributes?.baro_altitude || 10000),
      ));
      selectedAircraftTrackRef.current = viewer.entities.add({
        polyline: {
          positions,
          width: 3,
          material: new PolylineGlowMaterialProperty({ glowPower: 0.3, color: Color.fromCssColorString('#38bdf8') }),
        },
      });
    }
    viewer.scene.requestRender();
  }, [selectedTrack]);

  // Update only the selected icon and its orbit path; do not rebuild thousands of entities on every click.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const previous = selectedHighlightRef.current;
    if (previous) {
      if (previous.billboard) {
        previous.billboard.width = previous.width;
        previous.billboard.height = previous.height;
      } else if (previous.entity?.billboard) {
        previous.entity.billboard.width = new ConstantProperty(previous.width);
        previous.entity.billboard.height = new ConstantProperty(previous.height);
      }
      previous.tracks.forEach((track) => viewer.entities.remove(track));
      selectedHighlightRef.current = null;
    }

    if (selectedItem?.type === 'satellite') {
      const noradId = selectedItem.data?.attributes?.norad_id;
      const satellite = satellites.find((item) => item.entity_id === selectedItem.data?.entity_id ||
        (noradId && item.attributes?.norad_id === noradId));
      const satelliteIcons = satelliteBillboardsRef.current;
      const billboard = satelliteIcons && Array.from({ length: satelliteIcons.length }, (_, index) => satelliteIcons.get(index))
        .find((item: any) => item.id?._worldosData?.entity_id === satellite?.entity_id ||
          (noradId && item.id?._worldosData?.attributes?.norad_id === noradId));
      if (billboard) {
        selectedHighlightRef.current = { entity: null, billboard, width: 5, height: 5, tracks: [] };
        billboard.width = 18;
        billboard.height = 18;
      }
      const groundTrack = selectedItem.data?.attributes?.ground_track || satellite?.attributes?.ground_track;
      if (groundTrack && groundTrack.length > 1) {
        const highlight = selectedHighlightRef.current ?? { entity: null, width: 0, height: 0, tracks: [] };
        splitTrackAtAntimeridian(groundTrack).forEach((segment) => {
          highlight.tracks.push(viewer.entities.add({
            polyline: {
              positions: segment.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 0)),
              width: 2.5,
              material: Color.fromCssColorString('#c084fc').withAlpha(0.7),
            },
          }));
        });
        selectedHighlightRef.current = highlight;
      }
    } else if (selectedItem?.type === 'camera') {
      const entity = viewer.entities.values.find((item) => (item as any)._worldosType === 'camera' &&
        (item as any)._worldosData?.entity_id === selectedItem.data?.entity_id);
      if (entity?.billboard) {
        selectedHighlightRef.current = { entity, width: 24, height: 24, tracks: [] };
        entity.billboard.width = new ConstantProperty(32);
        entity.billboard.height = new ConstantProperty(32);
      }
    }
    viewer.scene.requestRender();
  }, [selectedItem, satellites]);

  return <div ref={containerRef} className="globe-container-3d" />;
};
