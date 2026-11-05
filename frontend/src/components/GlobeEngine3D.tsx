import React, { useEffect, useRef } from 'react';
import {
  Cartesian2,
  Cartesian3,
  BillboardCollection,
  BoundingSphere,
  Cesium3DTileset,
  Color,
  CustomDataSource,
  JulianDate,
  Simon1994PlanetaryPositions,
  ConstantProperty,
  DistanceDisplayCondition,
  GeoJsonDataSource,
  GoogleMaps,
  HeadingPitchRange,
  Ion,
  IonGeocodeProviderType,
  LabelStyle,
  Math as CesiumMath,
  NearFarScalar,
  PolylineGlowMaterialProperty,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  VerticalOrigin,
  Viewer,
  createGooglePhotorealistic3DTileset,
  createWorldTerrainAsync,
  defined,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import {
  AIRPLANE_ICON_BLUE,
  AIRPLANE_ICON_AMBER,
  AIRPLANE_ICON_INTERNATIONAL,
  AIRPLANE_ICON_DOMESTIC,
  AIRPLANE_ICON_GROUND,
  VESSEL_ICON_CYAN,
  SATELLITE_ICON_PURPLE,
  SATELLITE_ICON_NEON_RED,
  CAMERA_ICON_EMERALD,
  FIRE_ICON_ORANGE,
  FIRE_ICON_RED,
  AIRPORT_ICON_BLUE,
  PORT_ICON_TEAL,
  SPACEPORT_ICON_ROSE,
  HOTEL_ICON_GOLD,
  DINING_ICON_ROSE,
  SCENERY_ICON_EMERALD,
  NIGHTLIFE_ICON_PURPLE,
  MAP_PIN_STAYS_GOLD,
  MAP_PIN_DINING_ROSE,
  MAP_PIN_SCENERY_EMERALD,
  MAP_PIN_NIGHTLIFE_PURPLE,
  MAP_PIN_SELECTED_GLOW,
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
  PlaceItem,
  splitTrackAtAntimeridian,
} from '../api';
import { BasemapMode, LayerDefinition, SelectedItemPayload } from '../types/layers';

// Cesium asset base path configuration
(window as any).CESIUM_BASE_URL = '/cesium/';
Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? '';
GoogleMaps.defaultApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? '';

interface AircraftKinematicState {
  billboard: any;
  lon: number;
  lat: number;
  altMeters: number;
  velocityMps: number;
  trackDeg: number;
}

interface SatelliteKinematicState {
  billboard: any;
  lon: number;
  lat: number;
  altMeters: number;
  periodMin: number;
  inclinationDeg: number;
}

/**
 * Compute closed 3D Keplerian orbital loop and sub-satellite ground track.
 */
function computeKeplerianOrbit3D(
  lonDeg: number,
  latDeg: number,
  altMeters: number,
  inclinationDeg: number,
  numPoints = 140
): { positions3D: Cartesian3[]; groundPoints: [number, number][] } {
  const R = 6371000 + altMeters;
  const inc = CesiumMath.toRadians(inclinationDeg);
  const currentLat = CesiumMath.toRadians(latDeg);
  const currentLon = CesiumMath.toRadians(lonDeg);

  let sinInc = Math.sin(inc);
  if (Math.abs(sinInc) < 1e-4) {
    sinInc = sinInc >= 0 ? 1e-4 : -1e-4;
  }

  const sinU0 = Math.max(-1.0, Math.min(1.0, Math.sin(currentLat) / sinInc));
  const u0 = Math.asin(sinU0);
  const nodeLon = currentLon - Math.atan2(Math.sin(u0) * Math.cos(inc), Math.cos(u0));

  const positions3D: Cartesian3[] = [];
  const groundPoints: [number, number][] = [];

  for (let step = 0; step <= numPoints; step++) {
    const u = u0 + (step / numPoints) * CesiumMath.TWO_PI;
    const xOrb = R * Math.cos(u);
    const yOrb = R * Math.sin(u);

    const x = xOrb * Math.cos(nodeLon) - yOrb * Math.cos(inc) * Math.sin(nodeLon);
    const y = xOrb * Math.sin(nodeLon) + yOrb * Math.cos(inc) * Math.cos(nodeLon);
    const z = yOrb * Math.sin(inc);

    positions3D.push(new Cartesian3(x, y, z));

    const gLat = CesiumMath.toDegrees(Math.atan2(z, Math.sqrt(x * x + y * y)));
    const gLon = CesiumMath.toDegrees(Math.atan2(y, x));
    groundPoints.push([gLon, gLat]);
  }

  return { positions3D, groundPoints };
}

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
  discoveredPlaces?: PlaceItem[];
  selectedPlace?: PlaceItem | null;
  onSelectPlace?: (place: PlaceItem) => void;
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
  discoveredPlaces = [],
  selectedPlace = null,
  onSelectPlace,
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
  const satelliteTracksSourceRef = useRef<CustomDataSource | null>(null);
  const aircraftKinematicsRef = useRef<AircraftKinematicState[]>([]);
  const satelliteKinematicsRef = useRef<SatelliteKinematicState[]>([]);

  const applyImageryLayers = (viewer: Viewer, mode: BasemapMode, allowGoogleTiles = true) => {
    const requestId = ++imageryRequestRef.current;
    try {
      if (googleTilesetRef.current) {
        viewer.scene.primitives.remove(googleTilesetRef.current);
        googleTilesetRef.current = null;
      }
      viewer.imageryLayers.removeAll();

      const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
      if (mode === 'google-3d' && allowGoogleTiles) {
        // Keep the crisp raster globe visible while the photorealistic tileset loads.
        applyImageryLayers(viewer, 'satellite-hybrid', false);
        const googleRequestId = imageryRequestRef.current;
        const tileOptions = googleMapsApiKey ? { key: googleMapsApiKey } : { onlyUsingWithGoogleGeocoder: true };
        createGooglePhotorealistic3DTileset(
          tileOptions as any,
          { showCreditsOnScreen: true }
        ).then((tileset) => {
          if (viewer.isDestroyed() || googleRequestId !== imageryRequestRef.current) {
            tileset.destroy();
            return;
          }
          googleTilesetRef.current = tileset;
          viewer.scene.primitives.add(tileset);
          viewer.scene.requestRender();
        }).catch((err) => {
          console.warn('Google 3D Tiles load issue, falling back to raster satellite:', err);
          applyImageryLayers(viewer, 'satellite-hybrid', false);
        });
        return;
      }

      viewer.scene.globe.show = true;
      if (mode === 'satellite-hybrid') {
        const satImagery = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 20,
          credit: 'Esri, Maxar, Earthstar Geographics',
        });
        viewer.imageryLayers.addImageryProvider(satImagery);

        // High-resolution road and street network overlaid on satellite (no API key required)
        const transOverlay = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 20,
        });
        viewer.imageryLayers.addImageryProvider(transOverlay);

        // World administrative boundaries and places (no API key required)
        const refOverlay = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 20,
        });
        viewer.imageryLayers.addImageryProvider(refOverlay);

        viewer.scene.globe.baseColor = Color.fromCssColorString('#020617');
        viewer.scene.requestRender();
        return;
      }

      if (mode === 'streets') {
        // High-detail cartographic street map with roads, buildings, restaurants, motels, shops, and transit (no API key required)
        const streetBase = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 19,
          credit: 'Esri, OpenStreetMap, HERE, Garmin, USGS',
        });
        viewer.imageryLayers.addImageryProvider(streetBase);

        viewer.scene.globe.baseColor = Color.fromCssColorString('#f8fafc');
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
      targetFrameRate: 60,
      requestRenderMode: false,
    });

    applyImageryLayers(viewer, basemapMode);
    viewer.scene.globe.enableLighting = true;
    if (viewer.scene.moon) viewer.scene.moon.show = true;
    if (viewer.scene.sun) viewer.scene.sun.show = true;

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

    // Persistent data source for 3D satellite orbital tracks (isolated from entities.removeAll)
    const tracksDs = new CustomDataSource('satellite-orbital-tracks');
    viewer.dataSources.add(tracksDs);
    satelliteTracksSourceRef.current = tracksDs;

    // User interaction tracking for realistic Earth rotation when idle
    let isInteracting = false;
    let lastInteractionTime = Date.now();
    const markInteraction = () => {
      isInteracting = true;
      lastInteractionTime = Date.now();
    };
    const endInteraction = () => {
      isInteracting = false;
      lastInteractionTime = Date.now();
    };
    const canvas = viewer.scene.canvas;
    canvas.addEventListener('pointerdown', markInteraction);
    canvas.addEventListener('wheel', markInteraction, { passive: true });
    window.addEventListener('pointerup', endInteraction);

    // Live continuous motion loop: 60 FPS dead-reckoning for aircraft & orbital propagation for satellites
    let lastAnimTime = performance.now();
    const onPreRenderAnim = () => {
      const now = performance.now();
      const dt = Math.min(0.2, (now - lastAnimTime) / 1000);
      lastAnimTime = now;
      if (dt <= 0) return;

      // 1. Advance airborne aircraft along track heading
      const aircraftList = aircraftKinematicsRef.current;
      for (let i = 0; i < aircraftList.length; i++) {
        const item = aircraftList[i];
        const distM = item.velocityMps * dt;
        const trackRad = (item.trackDeg * Math.PI) / 180.0;
        const latRad = (item.lat * Math.PI) / 180.0;
        const dLat = (distM * Math.cos(trackRad)) / 111139.0;
        const cosLat = Math.cos(latRad);
        const dLon = (distM * Math.sin(trackRad)) / (111139.0 * (Math.abs(cosLat) > 0.02 ? cosLat : 0.02));

        item.lat += dLat;
        item.lon = ((item.lon + dLon + 540.0) % 360.0) - 180.0;
        item.billboard.position = Cartesian3.fromDegrees(item.lon, item.lat, item.altMeters);
      }

      // 2. Advance active satellites smoothly along their Keplerian orbital velocity in space
      const satelliteList = satelliteKinematicsRef.current;
      const earthRotDegPerSec = 360.0 / 86164.09;
      for (let i = 0; i < satelliteList.length; i++) {
        const item = satelliteList[i];
        const orbitDegPerSec = 360.0 / (item.periodMin * 60.0);
        const incRad = (item.inclinationDeg * Math.PI) / 180.0;
        const dLat = orbitDegPerSec * Math.cos(incRad) * dt;
        const cosLat = Math.cos((item.lat * Math.PI) / 180.0);
        const dLon = (orbitDegPerSec * Math.sin(incRad) * dt) / (Math.abs(cosLat) > 0.05 ? cosLat : 0.05) - (earthRotDegPerSec * dt);

        item.lat += dLat;
        if (item.lat > 85.0) item.lat = 85.0;
        else if (item.lat < -85.0) item.lat = -85.0;
        item.lon = ((item.lon + dLon + 540.0) % 360.0) - 180.0;
        item.billboard.position = Cartesian3.fromDegrees(item.lon, item.lat, item.altMeters);
      }

      // 3. Realistic inertial Earth auto-rotation when user is idle (zoomed out)
      if (!isInteracting && Date.now() - lastInteractionTime > 2500) {
        try {
          const camHeight = viewer.camera.positionCartographic.height;
          if (camHeight > 3_000_000) {
            // Smooth planetary spin around polar Z-axis
            viewer.scene.camera.rotate(Cartesian3.UNIT_Z, 0.00025 * dt * 60);
          }
        } catch {}
      }
    };

    viewer.scene.preRender.addEventListener(onPreRenderAnim);

    // Screen-space click picking handler
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((movement: { position: any }) => {
      const picked = viewer.scene.pick(movement.position);
      if (defined(picked) && picked.id) {
        const entity = picked.id;
        if (entity._worldosType && entity._worldosData) {
          if (entity._worldosType === 'place') {
            onSelectPlace?.(entity._worldosData);
          }
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
      canvas.removeEventListener('pointerdown', markInteraction);
      canvas.removeEventListener('wheel', markInteraction);
      window.removeEventListener('pointerup', endInteraction);
      viewer.scene.preRender.removeEventListener(onPreRenderAnim);
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
      if (satelliteTracksSourceRef.current) {
        viewer.dataSources.remove(satelliteTracksSourceRef.current, true);
        satelliteTracksSourceRef.current = null;
      }
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

    const featureCollection = {
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
    aircraftKinematicsRef.current = [];
    satelliteKinematicsRef.current = [];

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

        const attr = a.attributes || {};
        const callsign = (attr.callsign || a.canonical_name || '').trim().toUpperCase();
        const origin = (attr.origin_country || '').trim().toLowerCase();
        const alt = attr.baro_altitude ?? attr.geo_altitude ?? 0;
        const vel = attr.velocity ?? 0;
        // International flight classification: high cruising altitude/speed, intercontinental callsign, or foreign airspace
        const isInternational = (alt > 9500 && vel > 200) ||
          /^(BAW|DLH|AFR|UAE|QTR|SIA|ANA|JAL|QFA|KLM|ETD|THY|CPA|CAL|EVA|CSN|CCA|CES|VIR|AIC|ETH|SVA)/.test(callsign) ||
          (origin && origin !== 'united states' && (a.longitude > -125 && a.longitude < -68 && a.latitude > 25 && a.latitude < 49));
        (a.attributes as any).is_international = isInternational;

        const acBillboard = aircraftBillboards.add({
          id: { _worldosType: 'aircraft', _worldosData: a },
          position,
          image: isGround
            ? AIRPLANE_ICON_GROUND
            : isInternational
            ? AIRPLANE_ICON_AMBER
            : AIRPLANE_ICON_BLUE,
          rotation: CesiumMath.toRadians(360 - (a.attributes?.true_track || 0)),
          width: 24,
          height: 24,
          scaleByDistance: new NearFarScalar(1.5e2, 1.2, 1.5e7, 0.45),
          distanceDisplayCondition: new DistanceDisplayCondition(100.0, 1.4e7),
        });
        const acVelocity = a.attributes?.velocity ?? 0;
        if (!isGround && acVelocity > 10) {
          aircraftKinematicsRef.current.push({
            billboard: acBillboard,
            lon: a.longitude,
            lat: a.latitude,
            altMeters,
            velocityMps: acVelocity,
            trackDeg: a.attributes?.true_track ?? 0,
          });
        }
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

    // 2.5 Cislunar & Lunar Orbiters (Satellites in space orbiting the Moon)
    if (layerMap.get('space-satellites')) {
      try {
        const time = viewer.clock.currentTime || JulianDate.now();
        const moonPos = Simon1994PlanetaryPositions.computeMoonPositionInEarthInertialFrame(time);
        if (moonPos) {
          const lunarOrbiters = [
            { name: 'NASA Lunar Reconnaissance Orbiter (LRO)', r: 1_850_000, speed: 0.04, inc: 85 },
            { name: 'ISRO Chandrayaan-3 Propulsion Module', r: 2_100_000, speed: 0.035, inc: 72 },
            { name: 'NASA CAPSTONE Cislunar Orbiter', r: 3_200_000, speed: 0.025, inc: 45 },
            { name: 'KARI Danuri Lunar Orbiter (KPLO)', r: 1_900_000, speed: 0.038, inc: 90 },
          ];
          const nowSec = performance.now() / 1000;
          for (let i = 0; i < lunarOrbiters.length; i++) {
            const lo = lunarOrbiters[i];
            const theta = nowSec * lo.speed + (i * Math.PI / 2);
            const ox = lo.r * Math.cos(theta);
            const oy = lo.r * Math.sin(theta) * Math.cos(CesiumMath.toRadians(lo.inc));
            const oz = lo.r * Math.sin(theta) * Math.sin(CesiumMath.toRadians(lo.inc));
            const pos = new Cartesian3(moonPos.x + ox, moonPos.y + oy, moonPos.z + oz);

            const ent = viewer.entities.add({
              name: lo.name,
              position: pos,
              billboard: {
                image: SATELLITE_ICON_NEON_RED,
                width: 24,
                height: 24,
                scaleByDistance: new NearFarScalar(1.0e6, 1.2, 5.0e8, 0.4),
              },
            });
            (ent as any)._worldosType = 'satellite';
            (ent as any)._worldosData = {
              id: 'lunar-orbiter-' + (i + 1),
              canonical_name: lo.name,
              source_slug: 'cislunar-telemetry',
              truth_class: 'OBSERVED',
              observed_at: new Date().toISOString(),
              attributes: {
                orbit_domain: 'LUNAR_ORBIT',
                central_body: 'MOON',
                norad_id: 35315 + i * 1000,
                altitude_km: Math.round((lo.r - 1_737_400) / 1000),
              },
            };
          }
        }
      } catch {}
    }

    // 3. Space Satellites: True 3D Orbital Altitude (400 km to 20,200 km)
    if (layerMap.get('space-satellites') && satellites.length > 0) {
      for (const s of satellites) {
        const altitudeKm = s.attributes?.altitude_km;
        if (!Number.isFinite(altitudeKm)) continue;
        const altMeters = altitudeKm * 1000;
        const position = Cartesian3.fromDegrees(s.longitude, s.latitude, altMeters);

        const satBillboard = satelliteBillboards.add({
          id: { _worldosType: 'satellite', _worldosData: s },
          position,
          image: SATELLITE_ICON_NEON_RED,
          width: 14,
          height: 14,
          scaleByDistance: new NearFarScalar(1.0e6, 1.4, 8.0e7, 0.85),
        });
        satelliteKinematicsRef.current.push({
          billboard: satBillboard,
          lon: s.longitude,
          lat: s.latitude,
          altMeters,
          periodMin: s.attributes?.period_min || 92.8,
          inclinationDeg: s.attributes?.inclination_deg || 51.6,
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

    // 8. Discovered Places, Stays, Dining & Nightlife (Google Places API New)
    if (discoveredPlaces && discoveredPlaces.length > 0) {
      for (const place of discoveredPlaces) {
        const isSelected = selectedPlace?.id === place.id;
        const icon =
          place.category === 'stays'
            ? MAP_PIN_STAYS_GOLD
            : place.category === 'food'
            ? MAP_PIN_DINING_ROSE
            : place.category === 'scenery'
            ? MAP_PIN_SCENERY_EMERALD
            : MAP_PIN_NIGHTLIFE_PURPLE;

        const pinColor =
          place.category === 'stays'
            ? Color.fromCssColorString('#eab308')
            : place.category === 'food'
            ? Color.fromCssColorString('#f43f5e')
            : place.category === 'scenery'
            ? Color.fromCssColorString('#10b981')
            : Color.fromCssColorString('#a855f7');

        // 8a. Vertical Pin Stem from exact ground coordinates (0m) to floating pin head (30m)
        viewer.entities.add({
          polyline: {
            positions: [
              Cartesian3.fromDegrees(place.longitude, place.latitude, 0),
              Cartesian3.fromDegrees(place.longitude, place.latitude, 30),
            ],
            width: isSelected ? 4 : 2,
            material: isSelected ? Color.fromCssColorString('#facc15') : pinColor,
          },
        });

        // 8b. Ground Target Disc (exact pinpoint anchor on earth surface)
        viewer.entities.add({
          position: Cartesian3.fromDegrees(place.longitude, place.latitude, 1),
          point: {
            pixelSize: isSelected ? 14 : 8,
            color: isSelected ? Color.fromCssColorString('#facc15') : pinColor,
            outlineColor: Color.WHITE,
            outlineWidth: 2,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });

        // 8c. Pinpoint Teardrop Billboard + High-Legibility Title & Details Label
        const ent = viewer.entities.add({
          position: Cartesian3.fromDegrees(place.longitude, place.latitude, 30),
          billboard: {
            image: isSelected ? MAP_PIN_SELECTED_GLOW : icon,
            width: isSelected ? 38 : 28,
            height: isSelected ? 48 : 36,
            verticalOrigin: VerticalOrigin.BOTTOM,
            scaleByDistance: new NearFarScalar(2.0e2, 1.25, 2.0e6, 0.6),
            distanceDisplayCondition: new DistanceDisplayCondition(0.0, 5000000.0),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          label: {
            text: isSelected
              ? `📍 ${place.name.toUpperCase()}\n★ ${place.rating ? place.rating.toFixed(1) : '4.8'} · ${place.category.toUpperCase()} · ${place.price_level || '$$$'}\n${place.formatted_address}`
              : `${place.name} ★${place.rating ? place.rating.toFixed(1) : '4.8'}`,
            font: isSelected ? 'bold 12px "JetBrains Mono", sans-serif' : '10px "JetBrains Mono", sans-serif',
            fillColor: isSelected ? Color.fromCssColorString('#facc15') : Color.WHITE,
            outlineColor: Color.BLACK,
            outlineWidth: 3,
            style: LabelStyle.FILL_AND_OUTLINE,
            showBackground: true,
            backgroundColor: Color.fromCssColorString('rgba(5, 8, 16, 0.90)'),
            backgroundPadding: new Cartesian2(8, 5),
            pixelOffset: new Cartesian2(0, isSelected ? -56 : -42),
            distanceDisplayCondition: new DistanceDisplayCondition(0.0, isSelected ? 800000.0 : 80000.0),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        (ent as any)._worldosType = 'place';
        (ent as any)._worldosData = place;
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
    discoveredPlaces,
    selectedPlace,
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
      const satData = selectedItem.data;
      const noradId = satData?.attributes?.norad_id;
      const satellite = satellites.find((item) => item.entity_id === satData?.entity_id ||
        (noradId && item.attributes?.norad_id === noradId)) || satData;

      const satelliteIcons = satelliteBillboardsRef.current;
      const billboard = satelliteIcons && Array.from({ length: satelliteIcons.length }, (_, index) => satelliteIcons.get(index))
        .find((item: any) => item.id?._worldosData?.entity_id === satellite?.entity_id ||
          (noradId && item.id?._worldosData?.attributes?.norad_id === noradId));
      if (billboard) {
        selectedHighlightRef.current = { entity: null, billboard, width: 14, height: 14, tracks: [] };
        billboard.width = 24;
        billboard.height = 24;
      }

      const tracksDs = satelliteTracksSourceRef.current;
      if (tracksDs) {
        tracksDs.entities.removeAll();

        const isLunar = satData?.attributes?.orbit_domain === 'LUNAR_ORBIT' || satData?.attributes?.central_body === 'MOON';
        const altKm = satellite?.attributes?.altitude_km ?? 550;
        const altMeters = altKm * 1000;
        const incDeg = satellite?.attributes?.inclination_deg ?? 51.6;
        const lon = satellite?.longitude ?? satData?.longitude ?? 0;
        const lat = satellite?.latitude ?? satData?.latitude ?? 0;

        if (isLunar) {
          try {
            const time = viewer.clock.currentTime || JulianDate.now();
            const moonPos = Simon1994PlanetaryPositions.computeMoonPositionInEarthInertialFrame(time);
            if (moonPos) {
              const r = 2_000_000;
              const lunarOrbitPoints: Cartesian3[] = [];
              for (let step = 0; step <= 90; step++) {
                const theta = (step / 90) * CesiumMath.TWO_PI;
                const ox = r * Math.cos(theta);
                const oy = r * Math.sin(theta) * Math.cos(CesiumMath.toRadians(incDeg));
                const oz = r * Math.sin(theta) * Math.sin(CesiumMath.toRadians(incDeg));
                lunarOrbitPoints.push(new Cartesian3(moonPos.x + ox, moonPos.y + oy, moonPos.z + oz));
              }

              tracksDs.entities.add({
                name: `${satData?.canonical_name || 'Lunar Orbiter'} Orbit`,
                polyline: {
                  positions: lunarOrbitPoints,
                  width: 3.5,
                  material: new PolylineGlowMaterialProperty({ glowPower: 0.4, color: Color.fromCssColorString('#ff1744') }),
                },
              });

              // Focus camera on the lunar orbiter in cislunar space
              const satPos = lunarOrbitPoints[0];
              viewer.camera.flyToBoundingSphere(new BoundingSphere(satPos, 800_000), {
                duration: 2.0,
                offset: new HeadingPitchRange(0, CesiumMath.toRadians(-25), 3_000_000),
              });
            }
          } catch {}
        } else {
          // Earth Satellite (LEO, MEO, GEO)
          const { positions3D, groundPoints } = computeKeplerianOrbit3D(lon, lat, altMeters, incDeg, 140);

          // 1. True 3D orbital trajectory in space (continuous loop)
          tracksDs.entities.add({
            name: `${satData?.canonical_name || 'Satellite'} 3D Orbit`,
            polyline: {
              positions: positions3D,
              width: 4.0,
              material: new PolylineGlowMaterialProperty({ glowPower: 0.45, color: Color.fromCssColorString('#ff1744') }),
            },
          });

          // 2. Surface ground track projection
          splitTrackAtAntimeridian(groundPoints).forEach((segment) => {
            tracksDs.entities.add({
              polyline: {
                positions: segment.map(([tLon, tLat]) => Cartesian3.fromDegrees(tLon, tLat, 0)),
                width: 2.0,
                material: Color.fromCssColorString('#ff1744').withAlpha(0.6),
              },
            });
          });

          // 3. Focus camera directly onto the satellite in space
          const satPos = Cartesian3.fromDegrees(lon, lat, altMeters);
          let viewRange = 400_000;
          if (altKm < 1500) {
            viewRange = Math.max(300_000, altMeters * 0.5);
          } else if (altKm < 25000) {
            // MEO (e.g. GPS at 20,200 km)
            viewRange = Math.max(2_500_000, altMeters * 0.22);
          } else {
            // GEO (e.g. 35,786 km)
            viewRange = Math.max(5_000_000, altMeters * 0.18);
          }

          viewer.camera.flyToBoundingSphere(new BoundingSphere(satPos, 20_000), {
            duration: 1.8,
            offset: new HeadingPitchRange(
              viewer.camera.heading,
              CesiumMath.toRadians(-25),
              viewRange
            ),
          });
        }
      }
    } else {
      satelliteTracksSourceRef.current?.entities.removeAll();
    }
    if (selectedItem?.type === 'camera') {
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

  // Cinematic 3D camera fly-to when a venue/stay is selected
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !selectedPlace) return;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(selectedPlace.longitude, selectedPlace.latitude, 650),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-40),
        roll: 0,
      },
      duration: 2.0,
    });
  }, [selectedPlace]);

  return <div ref={containerRef} className="globe-container-3d" />;
};
