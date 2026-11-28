import { loadCloudImage } from '../utils/cloudFrames';
import React, { useEffect, useRef, useState } from 'react';
import {
  ArcGISTiledElevationTerrainProvider,
  Cartesian2,
  Cartesian3,
  Billboard,
  BillboardCollection,
  BoundingSphere,
  Cesium3DTileset,
  Color,
  CustomDataSource,
  GeographicTilingScheme,
  JulianDate,
  Simon1994PlanetaryPositions,
  ConstantProperty,
  DistanceDisplayCondition,
  GeoJsonDataSource,
  GoogleMaps,
  HeadingPitchRange,
  HeightReference,
  SingleTileImageryProvider,
  Ion,
  LabelStyle,
  Math as CesiumMath,
  Matrix4,
  NearFarScalar,
  PerspectiveFrustum,
  PolylineGlowMaterialProperty,
  PolylineCollection,
  Material,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  ImageryLayer,
  VerticalOrigin,
  Viewer,
  createGooglePhotorealistic3DTileset,
  createWorldTerrainAsync,
  defined,
  PostProcessStage,
  TerrainProvider,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import {
  AIRPLANE_ICON_BLUE,
  AIRPLANE_ICON_AMBER,
  AIRPLANE_ICON_COMMERCIAL,
  AIRPLANE_ICON_MILITARY,
  AIRPLANE_ICON_PRIVATE,
  AIRPLANE_ICON_INTERNATIONAL,
  AIRPLANE_ICON_DOMESTIC,
  AIRPLANE_ICON_GROUND,
  VESSEL_ICON_CYAN,
  SATELLITE_ICON_LEO,
  SATELLITE_ICON_MEO,
  SATELLITE_ICON_GEO,
  SATELLITE_ICON_LUNAR,
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
  RoadRouteResponse,
  InboundFlightPlan,
  UserNavigationState,
  splitTrackAtAntimeridian,
  LiveRainfallData,
  fetchLiveRainfall,
} from '../api';
import { BasemapMode, LayerDefinition, SelectedItemPayload } from '../types/layers';
import {
  CloudFrameInfo,
  CloudBrightnessEstimate,
  sampleSatelliteCloudBrightness,
} from './SatelliteClouds';

// Cesium asset base path configuration
(window as any).CESIUM_BASE_URL = '/cesium/';
Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? '';
GoogleMaps.defaultApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? '';

function detectWebglSupport(): { supported: boolean; hasWebgl2: boolean; hasWebgl1: boolean } {
  if (typeof document === 'undefined') {
    return { supported: false, hasWebgl2: false, hasWebgl1: false };
  }
  try {
    const canvas = document.createElement('canvas');
    const gl2 = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: false });
    if (gl2) return { supported: true, hasWebgl2: true, hasWebgl1: true };
    const gl1 =
      canvas.getContext('webgl', { failIfMajorPerformanceCaveat: false }) ||
      canvas.getContext('experimental-webgl', { failIfMajorPerformanceCaveat: false });
    if (gl1) return { supported: true, hasWebgl2: false, hasWebgl1: true };
  } catch {
    // WebGL blocked or unavailable
  }
  return { supported: false, hasWebgl2: false, hasWebgl1: false };
}

function createBundledEarthProvider(): UrlTemplateImageryProvider {
  return new UrlTemplateImageryProvider({
    url: '/cesium/Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg',
    tilingScheme: new GeographicTilingScheme(),
    maximumLevel: 2,
    tileWidth: 256,
    tileHeight: 256,
    credit: 'Natural Earth II (Offline Fallback)',
  });
}

function computeSolarNoonJulianDate(lonDeg: number): JulianDate {
  const now = new Date();
  const utcHoursAtNoon = ((12 - lonDeg / 15) % 24 + 24) % 24;
  const h = Math.floor(utcHoursAtNoon);
  const m = Math.floor((utcHoursAtNoon - h) * 60);
  const solarNoon = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), h, m, 0));
  return JulianDate.fromDate(solarNoon);
}

// Major Strategic Deep-Water Seaports (Global Chokepoints and Maritime Gateways)
interface GlobalSeaport {
  id: string;
  name: string;
  code: string;
  city: string;
  country: string;
  latitude: number;
  longitude: number;
  teu: string;
}

const GLOBAL_SEAPORTS: GlobalSeaport[] = [
  { id: 'PORT-RTM', name: 'Port of Rotterdam', code: 'NLRTM', city: 'Rotterdam', country: 'Netherlands', latitude: 51.95, longitude: 4.13, teu: '14.5M TEU' },
  { id: 'PORT-SIN', name: 'Port of Singapore', code: 'SGSIN', city: 'Singapore', country: 'Singapore', latitude: 1.27, longitude: 103.77, teu: '37.3M TEU' },
  { id: 'PORT-SHA', name: 'Port of Shanghai / Ningbo', code: 'CNNGB', city: 'Shanghai', country: 'China', latitude: 29.89, longitude: 121.84, teu: '47.3M TEU' },
  { id: 'PORT-PUS', name: 'Port of Busan', code: 'KRPUS', city: 'Busan', country: 'South Korea', latitude: 35.10, longitude: 129.04, teu: '22.7M TEU' },
  { id: 'PORT-HKG', name: 'Port of Hong Kong', code: 'HKHKG', city: 'Hong Kong', country: 'Hong Kong SAR', latitude: 22.33, longitude: 114.12, teu: '17.8M TEU' },
  { id: 'PORT-LAX', name: 'Port of Los Angeles & Long Beach', code: 'USLAX', city: 'Los Angeles', country: 'USA', latitude: 33.74, longitude: -118.26, teu: '19.0M TEU' },
  { id: 'PORT-NYC', name: 'Port of New York & New Jersey', code: 'USNYC', city: 'New York', country: 'USA', latitude: 40.67, longitude: -74.12, teu: '9.0M TEU' },
  { id: 'PORT-DXB', name: 'Port of Jebel Ali', code: 'AEJEA', city: 'Dubai', country: 'UAE', latitude: 24.99, longitude: 55.06, teu: '14.0M TEU' },
  { id: 'PORT-ANR', name: 'Port of Antwerp-Bruges', code: 'BEANR', city: 'Antwerp', country: 'Belgium', latitude: 51.28, longitude: 4.33, teu: '13.5M TEU' },
  { id: 'PORT-HAM', name: 'Port of Hamburg', code: 'DEHAM', city: 'Hamburg', country: 'Germany', latitude: 53.54, longitude: 9.97, teu: '8.3M TEU' },
  { id: 'PORT-PSD', name: 'Suez Canal / Port Said', code: 'EGPSD', city: 'Port Said', country: 'Egypt', latitude: 31.26, longitude: 32.31, teu: '4.2M TEU' },
  { id: 'PORT-CMB', name: 'Port of Colombo', code: 'LKCMB', city: 'Colombo', country: 'Sri Lanka', latitude: 6.95, longitude: 79.85, teu: '7.2M TEU' },
  { id: 'PORT-SSZ', name: 'Port of Santos', code: 'BRSSZ', city: 'Santos', country: 'Brazil', latitude: -23.96, longitude: -46.30, teu: '4.8M TEU' },
  { id: 'PORT-YOK', name: 'Port of Yokohama & Tokyo', code: 'JPYOK', city: 'Yokohama', country: 'Japan', latitude: 35.45, longitude: 139.67, teu: '8.1M TEU' },
  { id: 'PORT-BLB', name: 'Panama Canal / Balboa', code: 'PABLB', city: 'Balboa', country: 'Panama', latitude: 8.95, longitude: -79.56, teu: '3.6M TEU' },
  { id: 'PORT-GIB', name: 'Strait of Gibraltar Marine Hub', code: 'GIJBS', city: 'Gibraltar', country: 'Gibraltar', latitude: 36.14, longitude: -5.35, teu: '3.0M TEU' },
  { id: 'PORT-CPT', name: 'Port of Cape Town', code: 'ZACPT', city: 'Cape Town', country: 'South Africa', latitude: -33.91, longitude: 18.44, teu: '1.2M TEU' },
  { id: 'PORT-BOM', name: 'Jawaharlal Nehru Port (JNPT)', code: 'INBOM', city: 'Mumbai', country: 'India', latitude: 18.95, longitude: 72.95, teu: '5.6M TEU' },
  { id: 'PORT-SYD', name: 'Port Botany / Sydney', code: 'AUBNE', city: 'Sydney', country: 'Australia', latitude: -33.97, longitude: 151.21, teu: '2.8M TEU' },
  { id: 'PORT-ALG', name: 'Port of Algeciras', code: 'ESALG', city: 'Algeciras', country: 'Spain', latitude: 36.13, longitude: -5.43, teu: '4.8M TEU' },
  { id: 'PORT-PIR', name: 'Port of Piraeus', code: 'GRPIR', city: 'Athens', country: 'Greece', latitude: 37.94, longitude: 23.63, teu: '5.3M TEU' },
  { id: 'PORT-TPP', name: 'Port of Tanjung Pelepas', code: 'MYTPP', city: 'Johor', country: 'Malaysia', latitude: 1.36, longitude: 103.55, teu: '10.5M TEU' },
  { id: 'PORT-MAN', name: 'Port of Manaus (Amazon River)', code: 'BRMAO', city: 'Manaus', country: 'Brazil', latitude: -3.14, longitude: -60.02, teu: 'Amazon Inland Terminal' },
];

// Atmospheric parallel wind streamline model (Harmonic Rossby planetary wave flow)
function getAtmosphericWindVector(lat: number, lon: number): { headingDeg: number; speed: number } {
  const absLat = Math.abs(lat);
  const wave = Math.sin((lon * Math.PI) / 60.0) * 16.0 + Math.cos((lat * Math.PI) / 25.0) * 10.0;
  if (absLat < 28) {
    // Tropical Trade Winds: flowing East -> West with slight equatorial convergence
    const heading = lat >= 0 ? 250 + wave * 0.4 : 290 - wave * 0.4;
    return { headingDeg: heading, speed: 0.12 };
  } else if (absLat < 62) {
    // Mid-Latitude Westerlies & Jet Stream: flowing West -> East in smooth parallel streamlines
    const heading = 80 + wave;
    return { headingDeg: heading, speed: 0.22 };
  } else {
    // Polar Easterlies
    return { headingDeg: 260 + wave * 0.3, speed: 0.10 };
  }
}

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
  activeRoadRoute?: RoadRouteResponse | null;
  activeFlightPlan?: InboundFlightPlan | null;
  discoveredPlaces?: PlaceItem[];
  selectedPlace?: PlaceItem | null;
  onSelectPlace?: (place: PlaceItem) => void;
  targetLocation?: { center: [number, number]; zoom?: number } | null;
  selectedItem?: SelectedItemPayload | null;
  userNavState?: UserNavigationState | null;
  onUserPannedCamera?: () => void;
  rainFxEnabled?: boolean;
  onRainfallUpdate?: (data: LiveRainfallData, isZoomedIn: boolean) => void;
  cockpitAircraft?: AircraftState | null;
  onExitCockpit?: () => void;
  cloudFrame?: CloudFrameInfo | null;
  onCloudTileErrorChange?: (count: number) => void;
  onCockpitCloudEstimate?: (estimate: CloudBrightnessEstimate | null) => void;
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
  activeRoadRoute = null,
  activeFlightPlan = null,
  discoveredPlaces = [],
  selectedPlace = null,
  onSelectPlace,
  targetLocation,
  selectedItem = null,
  userNavState = null,
  onUserPannedCamera,
  rainFxEnabled = false,
  onRainfallUpdate,
  cockpitAircraft = null,
  onExitCockpit,
  cloudFrame = null,
  onCloudTileErrorChange,
  onCockpitCloudEstimate,
  onViewportChange,
  onSelectItem,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const rainPostProcessRef = useRef<PostProcessStage | null>(null);
  const cockpitAircraftRef = useRef<AircraftState | null>(null);
  const [webglStatus, setWebglStatus] = useState<'checking' | 'ready' | 'unavailable' | 'render-error'>('checking');
  const [webglErrorMessage, setWebglErrorMessage] = useState<string | null>(null);
  const [viewerResetCounter, setViewerResetCounter] = useState(0);
  const [forceWebgl1Retry, setForceWebgl1Retry] = useState(false);
  const [surfaceNotice, setSurfaceNotice] = useState<string | null>(null);
  const [basemapGeneration, setBasemapGeneration] = useState(0);
  const referenceOverlayLayersRef = useRef<ImageryLayer[]>([]);
  const onCloudTileErrorRef = useRef(onCloudTileErrorChange);
  onCloudTileErrorRef.current = onCloudTileErrorChange;
  const onCockpitCloudEstimateRef = useRef(onCockpitCloudEstimate);
  onCockpitCloudEstimateRef.current = onCockpitCloudEstimate;
  const cloudFrameRef = useRef<CloudFrameInfo | null>(cloudFrame);
  cloudFrameRef.current = cloudFrame;

  const isMobileRef = useRef(false);
  if (typeof window !== 'undefined') {
    isMobileRef.current = /Android/i.test(navigator.userAgent) || window.innerWidth <= 768;
  }

  useEffect(() => {
    cockpitAircraftRef.current = cockpitAircraft;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    const cloudsEnabled = layers.find((l) => l.id === 'live-clouds')?.enabled ?? true;
    const windEnabled = layers.find((l) => l.id === 'wind-streamlines')?.enabled ?? true;

    if (cockpitAircraft) {
      const ac = cockpitAircraft;
      const kine = aircraftKinematicsRef.current.find(
        (k) => k.billboard?.id?._worldosData?.id === ac.id || k.billboard?.id?._worldosData?.canonical_name === ac.canonical_name
      );
      const lon = kine ? kine.lon : (ac.longitude ?? 0);
      const lat = kine ? kine.lat : (ac.latitude ?? 0);
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        const rawAlt = kine ? kine.altMeters : (ac.attributes?.geo_altitude || ac.attributes?.baro_altitude || 10500);
        const alt = Math.max(200, Math.min(18000, Number.isFinite(rawAlt) ? rawAlt : 10500));
        const track = Number.isFinite(kine?.trackDeg) ? kine!.trackDeg : (ac.attributes?.true_track || 0);

        // Cancel any competing flyTo animations before locking pilot cockpit camera
        try {
          viewer.camera.cancelFlight();
          viewer.camera.lookAtTransform(Matrix4.IDENTITY);
        } catch {}

        // Hide wind streaks, oversized aircraft icons, satellite tracks, borders, and map labels from windshield
        if (satelliteBillboardsRef.current) satelliteBillboardsRef.current.show = false;
        if (satelliteTracksSourceRef.current) satelliteTracksSourceRef.current.show = false;
        if (aircraftBillboardsRef.current) aircraftBillboardsRef.current.show = false;
        if (cameraBillboardsRef.current) cameraBillboardsRef.current.show = false;
        if (windPolylinesRef.current) windPolylinesRef.current.show = false;
        if (geojsonSourceRef.current) geojsonSourceRef.current.show = false;
        viewer.entities.show = false;

        // Hide 2D map label & road reference overlays in cockpit view for authentic natural terrain
        for (const refLayer of referenceOverlayLayersRef.current) {
          refLayer.show = false;
        }

        // Hide night lights overlay & illuminate aircraft's longitude at solar noon for clear daylight sky + terrain relief
        if (nightImageryLayerRef.current) nightImageryLayerRef.current.show = false;
        viewer.scene.globe.enableLighting = true;
        viewer.clock.currentTime = computeSolarNoonJulianDate(lon);

        // Maximize terrain/imagery sharpness & set realistic distant horizon haze (instead of thick obscuring fog)
        viewer.scene.globe.maximumScreenSpaceError = isMobileRef.current ? 1.8 : 1.35;
        viewer.scene.globe.preloadSiblings = true;
        viewer.scene.globe.preloadAncestors = true;
        if (viewer.scene.fog) {
          viewer.scene.fog.density = 0.000016;
          viewer.scene.fog.visualDensityScalar = 0.12;
          viewer.scene.fog.screenSpaceErrorFactor = 1.0;
          viewer.scene.fog.minimumBrightness = 0.25;
        }
        if (viewer.camera.frustum instanceof PerspectiveFrustum) {
          viewer.camera.frustum.fov = CesiumMath.toRadians(68);
        }

        // Lock camera controller to prevent stray touch/mouse drags while in pilot view
        viewer.scene.screenSpaceCameraController.enableRotate = false;
        viewer.scene.screenSpaceCameraController.enableTranslate = false;
        viewer.scene.screenSpaceCameraController.enableZoom = false;
        viewer.scene.screenSpaceCameraController.enableTilt = false;
        viewer.scene.screenSpaceCameraController.enableLook = false;

        // Immediately jump to pilot view without starting a competing flyTo animation
        viewer.camera.setView({
          destination: Cartesian3.fromDegrees(lon, lat, alt + 3.0),
          orientation: {
            heading: CesiumMath.toRadians(track),
            pitch: CesiumMath.toRadians(-8.0),
            roll: 0.0,
          },
        });

        // Estimate local 3D clouds based on EUMETSAT IR satellite brightness at aircraft coordinates
        if (cloudsEnabled) {
          void sampleSatelliteCloudBrightness(lon, lat, cloudFrameRef.current?.rawTime).then((estimate) => {
            if (!cockpitAircraftRef.current) return;
            onCockpitCloudEstimateRef.current?.(estimate);
            if (cloudBillboardsRef.current) {
              const shouldShow = estimate ? estimate.hasClouds : true;
              cloudBillboardsRef.current.show = shouldShow;
              if (shouldShow) {
                const cloudTexture = getCloudTexture();
                cloudBillboardsRef.current.removeAll();
                const list: typeof cloudsListRef.current = [];
                const baseM = estimate?.estimatedBaseMeters ?? 3800;
                const topM = estimate?.estimatedTopMeters ?? 7800;
                const densityCount = estimate ? Math.max(12, Math.round(estimate.brightness * 36)) : 20;
                for (let i = 0; i < densityCount; i++) {
                  const trackRad = CesiumMath.toRadians(track);
                  const fwd = 0.06 + Math.random() * 0.35;
                  const latOff = (Math.random() - 0.5) * 0.28;
                  const cLon = lon + Math.sin(trackRad) * fwd - Math.cos(trackRad) * latOff;
                  const cLat = lat + Math.cos(trackRad) * fwd + Math.sin(trackRad) * latOff;
                  const cAlt = baseM + Math.random() * Math.max(1200, topM - baseM);
                  const b = cloudBillboardsRef.current.add({
                    position: Cartesian3.fromDegrees(cLon, cLat, cAlt),
                    image: cloudTexture,
                    width: 4500 + Math.random() * 9000,
                    height: 2200 + Math.random() * 4500,
                    sizeInMeters: true,
                    color: Color.WHITE.withAlpha(0.38 + (estimate?.brightness ?? 0.5) * 0.32),
                  });
                  list.push({ billboard: b, lon: cLon, lat: cLat, altMeters: cAlt, isLocal: true });
                }
                cloudsListRef.current = list;
              }
            }
          });
        } else {
          onCockpitCloudEstimateRef.current?.(null);
          if (cloudBillboardsRef.current) cloudBillboardsRef.current.show = false;
        }
      }
    } else {
      onCockpitCloudEstimateRef.current?.(null);
      if (!viewer.isDestroyed()) {
        try {
          viewer.camera.cancelFlight();
          viewer.clock.currentTime = JulianDate.now();
        } catch {}
        viewer.scene.globe.maximumScreenSpaceError = isMobileRef.current ? 2.5 : 2.0;
        viewer.scene.globe.preloadSiblings = false;
        viewer.scene.globe.preloadAncestors = false;
        if (viewer.scene.fog) {
          viewer.scene.fog.density = 0.000035;
          viewer.scene.fog.visualDensityScalar = 0.15;
          viewer.scene.fog.screenSpaceErrorFactor = 2.0;
        }
        if (viewer.camera.frustum instanceof PerspectiveFrustum) {
          viewer.camera.frustum.fov = CesiumMath.toRadians(60);
        }
        if (cloudBillboardsRef.current) {
          cloudBillboardsRef.current.show = false;
          cloudBillboardsRef.current.removeAll();
          cloudsListRef.current = [];
        }
        if (satelliteBillboardsRef.current) satelliteBillboardsRef.current.show = true;
        if (satelliteTracksSourceRef.current) satelliteTracksSourceRef.current.show = true;
        if (aircraftBillboardsRef.current) aircraftBillboardsRef.current.show = true;
        if (cameraBillboardsRef.current) cameraBillboardsRef.current.show = true;
        if (windPolylinesRef.current) windPolylinesRef.current.show = windEnabled;
        if (geojsonSourceRef.current) geojsonSourceRef.current.show = true;
        viewer.entities.show = true;
        for (const refLayer of referenceOverlayLayersRef.current) {
          refLayer.show = true;
        }
        viewer.scene.screenSpaceCameraController.enableRotate = true;
        viewer.scene.screenSpaceCameraController.enableTranslate = true;
        viewer.scene.screenSpaceCameraController.enableZoom = true;
        viewer.scene.screenSpaceCameraController.enableTilt = true;
        viewer.scene.screenSpaceCameraController.enableLook = true;
      }
    }
  }, [cockpitAircraft]);
  const onRainfallUpdateRef = useRef(onRainfallUpdate);
  useEffect(() => {
    onRainfallUpdateRef.current = onRainfallUpdate;
  }, [onRainfallUpdate]);
  const lastRainQueryTimeRef = useRef<number>(0);
  const googleTilesetRef = useRef<Cesium3DTileset | null>(null);
  const userNavSourceRef = useRef<CustomDataSource | null>(null);
  const isCameraLockedToNavRef = useRef<boolean>(false);
  const onUserPannedCameraRef = useRef(onUserPannedCamera);
  useEffect(() => {
    onUserPannedCameraRef.current = onUserPannedCamera;
  }, [onUserPannedCamera]);
  const imageryRequestRef = useRef(0);
  const terrainPromiseRef = useRef<Promise<TerrainProvider> | null>(null);
  const geojsonSourceRef = useRef<GeoJsonDataSource | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const selectedHighlightRef = useRef<{ entity: any; billboard?: any; width: number; height: number; tracks: any[] } | null>(null);
  const selectedAircraftTrackRef = useRef<any>(null);
  const aircraftBillboardsRef = useRef<BillboardCollection | null>(null);
  const satelliteBillboardsRef = useRef<BillboardCollection | null>(null);
  const satelliteTracksSourceRef = useRef<CustomDataSource | null>(null);
  const aircraftKinematicsRef = useRef<AircraftKinematicState[]>([]);
  const satelliteKinematicsRef = useRef<SatelliteKinematicState[]>([]);
  const cameraBillboardsRef = useRef<BillboardCollection | null>(null);
  const radarImageryLayerRef = useRef<ImageryLayer | null>(null);
  const radarFramePathRef = useRef<string | null>(null);
  const windPolylinesRef = useRef<PolylineCollection | null>(null);
  const windParticlesRef = useRef<Array<{
    line: any;
    lon: number;
    lat: number;
    altMeters: number;
    speed: number;
    headingDeg: number;
    age: number;
    maxAge: number;
  }>>([]);
  const nightImageryLayerRef = useRef<ImageryLayer | null>(null);
  const cloudBillboardsRef = useRef<BillboardCollection | null>(null);
  const cloudImageryLayerRef = useRef<ImageryLayer | null>(null);
  const cloudsListRef = useRef<Array<{
    billboard: Billboard;
    lon: number;
    lat: number;
    altMeters: number;
    isLocal?: boolean;
  }>>([]);
  const streamCancelRef = useRef<(() => void) | null>(null);

  // High-performance procedural volumetric cloud texture (100% watermark-free, beautiful billowing cumulus lobes)
  const getCloudTexture = (): string => {
    if (typeof document === 'undefined') return '';
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');
    if (!ctx) return '';
    ctx.clearRect(0, 0, 512, 256);

    const lobes = [
      { x: 160, y: 140, r: 90, a: 0.92 },
      { x: 256, y: 110, r: 115, a: 0.96 },
      { x: 350, y: 135, r: 95, a: 0.92 },
      { x: 105, y: 165, r: 75, a: 0.82 },
      { x: 405, y: 160, r: 80, a: 0.85 },
      { x: 210, y: 165, r: 85, a: 0.94 },
      { x: 300, y: 160, r: 88, a: 0.94 },
      { x: 256, y: 160, r: 90, a: 0.96 },
    ];

    for (const lobe of lobes) {
      const grad = ctx.createRadialGradient(lobe.x, lobe.y, lobe.r * 0.15, lobe.x, lobe.y, lobe.r);
      grad.addColorStop(0.0, `rgba(255, 255, 255, ${lobe.a})`);
      grad.addColorStop(0.55, `rgba(244, 248, 255, ${lobe.a * 0.78})`);
      grad.addColorStop(0.85, `rgba(220, 235, 255, ${lobe.a * 0.35})`);
      grad.addColorStop(1.0, 'rgba(255, 255, 255, 0.0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(lobe.x, lobe.y, lobe.r, 0, Math.PI * 2);
      ctx.fill();
    }

    return canvas.toDataURL('image/png');
  };

  const surfaceMode: BasemapMode = cockpitAircraft && basemapMode !== 'google-3d' ? 'satellite-hybrid' : basemapMode;

  const applyImageryLayers = (viewer: Viewer, mode: BasemapMode, allowGoogleTiles = true) => {
    ++imageryRequestRef.current;
    setSurfaceNotice(null);
    try {
      if (googleTilesetRef.current) {
        viewer.scene.primitives.remove(googleTilesetRef.current);
        googleTilesetRef.current = null;
      }
      viewer.imageryLayers.removeAll();
      radarImageryLayerRef.current = null;
      cloudImageryLayerRef.current = null;
      nightImageryLayerRef.current = null;
      referenceOverlayLayersRef.current = [];

      // Always keep the bundled offline Natural Earth II layer as Layer 0 so Earth appears instantaneously
      // even if external tiles are slow or blocked on mobile connections.
      viewer.imageryLayers.addImageryProvider(createBundledEarthProvider());

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
          if (viewer.isDestroyed() || googleRequestId !== imageryRequestRef.current) return;
          console.warn('Google 3D Tiles load issue, falling back to raster satellite:', err);
          setSurfaceNotice('Photorealistic 3D tiles unavailable · showing satellite terrain');
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
        const transLayer = viewer.imageryLayers.addImageryProvider(transOverlay);

        // World administrative boundaries and places (no API key required)
        const refOverlay = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 20,
        });
        const refLayer = viewer.imageryLayers.addImageryProvider(refOverlay);
        referenceOverlayLayersRef.current = [transLayer, refLayer];
        if (cockpitAircraftRef.current) {
          transLayer.show = false;
          refLayer.show = false;
        }

        // NASA Earth at Night: VIIRS Black Marble City Lights (Auto-blends onto night side of Earth in space only)
        const nightLights = new UrlTemplateImageryProvider({
          url: 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_CityLights_2012/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpg',
          maximumLevel: 8,
          credit: 'NASA Earth at Night / VIIRS Black Marble City Lights',
        });
        const nightLayer = viewer.imageryLayers.addImageryProvider(nightLights);
        nightLayer.dayAlpha = 0.0;
        nightLayer.nightAlpha = 0.95;
        nightLayer.brightness = 2.0;
        nightLayer.show = !cockpitAircraftRef.current;
        nightImageryLayerRef.current = nightLayer;

        viewer.scene.globe.baseColor = Color.fromCssColorString('#020617');
        setBasemapGeneration((g) => g + 1);
        viewer.scene.requestRender();
        return;
      }

      if (mode === 'streets') {
        const streetBase = new UrlTemplateImageryProvider({
          url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 19,
          credit: 'Esri, OpenStreetMap, HERE, Garmin, USGS',
        });
        viewer.imageryLayers.addImageryProvider(streetBase);

        viewer.scene.globe.baseColor = Color.fromCssColorString('#f8fafc');
        setBasemapGeneration((g) => g + 1);
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
        const oceanRefLayer = viewer.imageryLayers.addImageryProvider(oceanRef);
        referenceOverlayLayersRef.current = [oceanRefLayer];
        viewer.scene.globe.baseColor = Color.fromCssColorString('#031024');
        setBasemapGeneration((g) => g + 1);
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
      const darkRefLayer = viewer.imageryLayers.addImageryProvider(darkRef);
      referenceOverlayLayersRef.current = [darkRefLayer];
      viewer.scene.globe.baseColor = Color.fromCssColorString('#0a0e17');
      setBasemapGeneration((g) => g + 1);
      viewer.scene.requestRender();
    } catch {
      // Graceful fallback — offline Natural Earth II remains available
    }
  };

  // Initialize Cesium Globe Viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    const webglCheck = detectWebglSupport();
    if (!webglCheck.supported) {
      setWebglStatus('unavailable');
      setWebglErrorMessage('Hardware 3D WebGL acceleration is disabled or unavailable on this browser.');
      return;
    }

    const isMobile = isMobileRef.current;
    let viewer: Viewer;
    try {
      viewer = new Viewer(containerRef.current, {
        animation: false,
        timeline: false,
        baseLayerPicker: false,
        baseLayer: new ImageryLayer(createBundledEarthProvider()),
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        infoBox: false,
        selectionIndicator: false,
        targetFrameRate: isMobile ? 45 : 60,
        requestRenderMode: false,
        msaaSamples: isMobile ? 1 : 4,
        useBrowserRecommendedResolution: true,
        contextOptions: {
          requestWebgl1: forceWebgl1Retry || !webglCheck.hasWebgl2,
          webgl: {
            alpha: false,
            depth: true,
            stencil: false,
            antialias: !isMobile,
            powerPreference: isMobile ? 'low-power' : 'high-performance',
            failIfMajorPerformanceCaveat: false,
          },
        },
      });
    } catch (initErr) {
      console.error('Cesium Viewer initialization error:', initErr);
      if (!forceWebgl1Retry && webglCheck.hasWebgl1 && webglCheck.hasWebgl2) {
        setForceWebgl1Retry(true);
        setViewerResetCounter((c) => c + 1);
        return;
      }
      setWebglStatus('unavailable');
      setWebglErrorMessage(
        initErr instanceof Error ? initErr.message : 'Unable to initialize WebGL 3D globe.'
      );
      return;
    }

    setWebglStatus('ready');
    setWebglErrorMessage(null);

    viewer.resolutionScale = isMobile
      ? Math.min(window.devicePixelRatio || 1, 1.0)
      : Math.min(window.devicePixelRatio || 1, 1.5);
    viewer.scene.globe.tileCacheSize = isMobile ? 250 : 1000;
    viewer.scene.globe.maximumScreenSpaceError = isMobile ? 2.5 : 2.0;

    const triggerGraphicsFallback = (reason: string) => {
      if (!forceWebgl1Retry && webglCheck.hasWebgl1) {
        setForceWebgl1Retry(true);
        setViewerResetCounter((c) => c + 1);
        return;
      }
      setWebglStatus('render-error');
      setWebglErrorMessage(reason);
    };

    const onWebglContextLost = (event: globalThis.Event) => {
      event.preventDefault();
      triggerGraphicsFallback('Browser WebGL graphics session was lost.');
    };
    viewer.canvas.addEventListener('webglcontextlost', onWebglContextLost);

    // Catch runtime WebGL / shader compilation errors cleanly inside the map viewport
    const onSceneRenderError = (_scene: any, error: any) => {
      console.error('Cesium scene renderError:', error);
      triggerGraphicsFallback(
        error instanceof Error ? error.message : 'WebGL shader or rendering failure occurred.'
      );
    };
    viewer.scene.renderError.addEventListener(onSceneRenderError);

    applyImageryLayers(viewer, surfaceMode);
    viewer.scene.globe.enableLighting = true;
    if (viewer.scene.moon) viewer.scene.moon.show = !isMobile;
    if (viewer.scene.sun) viewer.scene.sun.show = true;

    // Non-blocking world terrain loading (Cesium World Terrain with ArcGIS Elevation3D fallback)
    const loadEsriTerrain = () =>
      ArcGISTiledElevationTerrainProvider.fromUrl(
        'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer'
      );
    terrainPromiseRef.current ??= Ion.defaultAccessToken
      ? createWorldTerrainAsync().catch(loadEsriTerrain)
      : loadEsriTerrain();
    terrainPromiseRef.current
      .then((terrainProvider) => {
        if (!viewer.isDestroyed()) {
          viewer.terrainProvider = terrainProvider;
          viewer.scene.requestRender();
        }
      })
      .catch(() => {
        if (!viewer.isDestroyed()) {
          setSurfaceNotice('Elevation unavailable · showing satellite imagery');
        }
      });

    // Cinematic Earth Atmosphere: Rayleigh Blue Light Scattering & Gentle Horizon Haze
    viewer.scene.globe.showGroundAtmosphere = true;
    viewer.scene.globe.atmosphereLightIntensity = 10.0;
    viewer.scene.globe.atmosphereRayleighCoefficient = new Cartesian3(5.5e-6, 13.0e-6, 22.4e-6);
    viewer.scene.globe.atmosphereMieCoefficient = new Cartesian3(21e-6, 21e-6, 21e-6);
    if (viewer.scene.skyAtmosphere) {
      viewer.scene.skyAtmosphere.show = true;
      viewer.scene.skyAtmosphere.atmosphereLightIntensity = 10.0;
      viewer.scene.skyAtmosphere.brightnessShift = 0.15;
    }
    if (viewer.scene.fog) {
      viewer.scene.fog.enabled = true;
      viewer.scene.fog.density = 0.000035;
      viewer.scene.fog.visualDensityScalar = 0.15;
      viewer.scene.fog.screenSpaceErrorFactor = 2.0;
    }

    // Initial camera view
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(20.0, 20.0, 18_000_000),
    });
    viewer.scene.requestRender();

    // Real-Time 3D Falling Rain Post-Processing FX
    const rainFragmentShader = `
      uniform sampler2D colorTexture;
      in vec2 v_textureCoordinates;
      float hashRain(float x) {
        return fract(sin(x * 133.3) * 43758.5453123);
      }
      void main() {
        vec4 color = texture(colorTexture, v_textureCoordinates);
        vec2 p = v_textureCoordinates;
        // Natural atmospheric wind-slanted vector
        p.x += p.y * 0.16;
        // Frame-rate advected vertical streak drop
        p.y += czm_frameNumber * 0.038;
        vec2 grid = vec2(floor(p.x * 260.0), floor(p.y * 36.0));
        float rnd = hashRain(grid.x + grid.y * 57.0);
        if (rnd > 0.976) {
          float streak = clamp((fract(p.y * 36.0) - 0.22) * 1.9, 0.0, 1.0);
          vec3 rainColor = vec3(0.75, 0.88, 1.0);
          color.rgb = mix(color.rgb, rainColor, streak * 0.60);
        }
        out_FragColor = color;
      }
    `;
    try {
      const rainStage = new PostProcessStage({
        name: 'czm_rainfall_fx',
        fragmentShader: rainFragmentShader,
      });
      rainStage.enabled = false;
      viewer.scene.postProcessStages.add(rainStage);
      rainPostProcessRef.current = rainStage;
    } catch (e) {
      console.warn('Cesium PostProcessStage rain init:', e);
    }

    const emitCameraBounds = () => {
      // Guard: do not compute or emit bounds if in Cockpit Mode or following navigation
      if (cockpitAircraftRef.current) return;
      if (isCameraLockedToNavRef.current) return;

      try {
        const rectangle = viewer.camera.computeViewRectangle();
        const camHeight = viewer.camera.positionCartographic.height;
        const isZoomed = camHeight < 500_000;
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
          }, 1 + Math.log2(20_000_000 / Math.max(camHeight, 1)));
        }

        // Live Rainfall Detection when zoomed into region / city (< 500 km altitude)
        const centerLon = CesiumMath.toDegrees(viewer.camera.positionCartographic.longitude);
        const centerLat = CesiumMath.toDegrees(viewer.camera.positionCartographic.latitude);
        const now = Date.now();
        if (isZoomed && now - lastRainQueryTimeRef.current > 3500) {
          lastRainQueryTimeRef.current = now;
          fetchLiveRainfall(centerLat, centerLon)
            .then((data) => {
              onRainfallUpdateRef.current?.(data, isZoomed);
              if (rainPostProcessRef.current) {
                // If live precipitation > 0.1 mm/h, automatically activate falling rain particles
                if (data.precipitation_mm_h > 0.1) {
                  rainPostProcessRef.current.enabled = true;
                }
              }
            })
            .catch(() => {});
        } else if (!isZoomed && rainPostProcessRef.current && !rainFxEnabled) {
          rainPostProcessRef.current.enabled = false;
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

    // Persistent data source for User Live Navigation Tracking Puck (isolated from entities.removeAll)
    const userNavDs = new CustomDataSource('user-navigation-track');
    viewer.dataSources.add(userNavDs);
    userNavSourceRef.current = userNavDs;

    // User interaction tracking for realistic Earth rotation when idle
    let isInteracting = false;
    let lastInteractionTime = Date.now();
    const markInteraction = () => {
      isInteracting = true;
      lastInteractionTime = Date.now();
      if (isCameraLockedToNavRef.current) {
        viewer.camera.lookAtTransform(Matrix4.IDENTITY);
        isCameraLockedToNavRef.current = false;
        onUserPannedCameraRef.current?.();
      }
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

      // Live First-Person Cockpit Camera Locking (Pilot View at 60 FPS)
      if (cockpitAircraftRef.current) {
        try {
          const ac = cockpitAircraftRef.current;
          const kine = aircraftKinematicsRef.current.find(
            (k) => k.billboard?.id?._worldosData?.id === ac.id || k.billboard?.id?._worldosData?.canonical_name === ac.canonical_name
          );
          const lon = kine ? kine.lon : (ac.longitude ?? 0);
          const lat = kine ? kine.lat : (ac.latitude ?? 0);
          if (Number.isFinite(lon) && Number.isFinite(lat)) {
            const rawAlt = kine ? kine.altMeters : (ac.attributes?.geo_altitude || ac.attributes?.baro_altitude || 10500);
            const alt = Math.max(200, Math.min(18000, Number.isFinite(rawAlt) ? rawAlt : 10500));
            const track = Number.isFinite(kine?.trackDeg) ? kine!.trackDeg : (ac.attributes?.true_track || 0);

            // Position camera inside the aircraft cockpit looking forward over the terrain and landscape
            const eyePos = Cartesian3.fromDegrees(lon, lat, alt + 3.0);
            viewer.camera.setView({
              destination: eyePos,
              orientation: {
                heading: CesiumMath.toRadians(track),
                pitch: CesiumMath.toRadians(-8.0),
                roll: 0.0,
              },
            });
          }
        } catch (e) {
          console.warn('Cockpit camera tracking:', e);
        }
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

      // NASA Earth at Night: STRICTLY visible only in outer space (> 1,800,000 meters / 1,800 km)!
      // When zoomed into countries, cities, or cockpit mode, keep map 100% crystal clear with full roads, labels, and terrain.
      if (nightImageryLayerRef.current) {
        if (cockpitAircraftRef.current) {
          nightImageryLayerRef.current.show = false;
        } else {
          try {
            const camHeight = viewer.camera.positionCartographic.height;
            if (camHeight < 1_800_000) {
              nightImageryLayerRef.current.show = false;
            } else {
              nightImageryLayerRef.current.show = true;
              const t = Math.max(0.0, Math.min(1.0, (camHeight - 1_800_000) / 1_700_000));
              nightImageryLayerRef.current.nightAlpha = t * 0.95;
            }
          } catch {
            nightImageryLayerRef.current.show = false;
          }
        }
      }

      // 4. Illustrative Prevailing Wind Model (Thin flowing streamlines without bright dots)
      const windList = windParticlesRef.current;
      for (let i = 0; i < windList.length; i++) {
        const p = windList[i];
        p.age += dt;
        if (p.age >= p.maxAge) {
          p.age = 0;
          p.lon = (Math.random() - 0.5) * 360;
          p.lat = (Math.random() - 0.5) * 150;
          const vec = getAtmosphericWindVector(p.lat, p.lon);
          p.headingDeg = vec.headingDeg;
          p.speed = vec.speed;
        } else {
          // Continuously track curved streamline vector along prevailing atmospheric currents
          const vec = getAtmosphericWindVector(p.lat, p.lon);
          p.headingDeg = vec.headingDeg;
          p.speed = vec.speed;
          const rad = (p.headingDeg * Math.PI) / 180.0;
          p.lon += Math.sin(rad) * p.speed * dt * 22.0;
          p.lat += Math.cos(rad) * p.speed * dt * 22.0;
          p.lon = ((p.lon + 540.0) % 360.0) - 180.0;
        }

        const rad = (p.headingDeg * Math.PI) / 180.0;
        const tailDeg = Math.min(2.2, 0.7 + p.speed * 2.4);
        const tailLon = p.lon - Math.sin(rad) * tailDeg;
        const tailLat = p.lat - Math.cos(rad) * tailDeg;

        // Anti-wrapping guard: suppress when crossing antimeridian (-180°/+180°) or in cockpit windshield
        if (cockpitAircraftRef.current || Math.abs(p.lon - tailLon) > 4.0 || Math.abs(p.lat - tailLat) > 4.0) {
          p.line.show = false;
          continue;
        }

        p.line.show = true;
        const midLon = (p.lon + tailLon) / 2.0;
        const midLat = (p.lat + tailLat) / 2.0;

        p.line.positions = [
          Cartesian3.fromDegrees(p.lon, p.lat, p.altMeters),
          Cartesian3.fromDegrees(midLon, midLat, p.altMeters),
          Cartesian3.fromDegrees(tailLon, tailLat, p.altMeters),
        ];

        // Subtle smooth fade-in and fade-out opacity for natural flowing streamlines
        const lifecycleRatio = p.age / p.maxAge;
        const alpha = Math.max(0.06, Math.sin(lifecycleRatio * Math.PI) * 0.48);
        if (p.line.material?.uniforms?.color) {
          p.line.material.uniforms.color = Color.fromCssColorString('#bae6fd').withAlpha(alpha);
        }
      }

      // 5. Active Live Atmospheric Clouds: majestic planetary drift along prevailing wind currents
      const cloudList = cloudsListRef.current;
      const ac = cockpitAircraftRef.current;
      for (let i = 0; i < cloudList.length; i++) {
        const c = cloudList[i];
        const vec = getAtmosphericWindVector(c.lat, c.lon);
        const rad = (vec.headingDeg * Math.PI) / 180.0;
        c.lon += Math.sin(rad) * vec.speed * dt * 6.5;
        c.lat += Math.cos(rad) * vec.speed * dt * 6.5;
        c.lon = ((c.lon + 540.0) % 360.0) - 180.0;

        // In Cockpit View: keep local clouds streaming around and alongside the aircraft
        if (ac && c.isLocal && typeof ac.longitude === 'number' && typeof ac.latitude === 'number') {
          const dLon = c.lon - ac.longitude;
          const dLat = c.lat - ac.latitude;
          const distDeg = Math.sqrt(dLon * dLon + dLat * dLat);
          // If cloud drifted behind aircraft by more than 0.40 deg (~40 km), recycle ahead of the plane
          if (distDeg > 0.40) {
            const trackRad = ((ac.attributes?.true_track || 0) * Math.PI) / 180.0;
            const forwardDistDeg = 0.15 + Math.random() * 0.25;
            const lateralOffsetDeg = (Math.random() - 0.5) * 0.22;
            c.lon = ac.longitude + Math.sin(trackRad) * forwardDistDeg - Math.cos(trackRad) * lateralOffsetDeg;
            c.lat = ac.latitude + Math.cos(trackRad) * forwardDistDeg + Math.sin(trackRad) * lateralOffsetDeg;
            const rawAlt = ac.attributes?.geo_altitude || ac.attributes?.baro_altitude || 10500;
            c.altMeters = Math.max(1500, rawAlt + (Math.random() - 0.5) * 4000);
          }
        }

        c.billboard.position = Cartesian3.fromDegrees(c.lon, c.lat, c.altMeters);
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
      canvas.removeEventListener('webglcontextlost', onWebglContextLost);
      canvas.removeEventListener('pointerdown', markInteraction);
      canvas.removeEventListener('wheel', markInteraction);
      window.removeEventListener('pointerup', endInteraction);
      viewer.scene.renderError.removeEventListener(onSceneRenderError);
      viewer.scene.preRender.removeEventListener(onPreRenderAnim);
      viewer.camera.moveEnd.removeEventListener(emitCameraBounds);
      if (handlerRef.current) {
        handlerRef.current.destroy();
        handlerRef.current = null;
      }
      if (rainPostProcessRef.current && !viewer.isDestroyed()) {
        try {
          viewer.scene.postProcessStages.remove(rainPostProcessRef.current);
        } catch {}
        rainPostProcessRef.current = null;
      }
      if (cloudImageryLayerRef.current && !viewer.isDestroyed()) {
        try {
          viewer.imageryLayers.remove(cloudImageryLayerRef.current);
        } catch {}
        cloudImageryLayerRef.current = null;
      }
      if (cloudBillboardsRef.current && !viewer.isDestroyed()) {
        try {
          viewer.scene.primitives.remove(cloudBillboardsRef.current);
        } catch {}
        cloudBillboardsRef.current = null;
      }
      if (windPolylinesRef.current && !viewer.isDestroyed()) {
        try {
          viewer.scene.primitives.remove(windPolylinesRef.current);
        } catch {}
        windPolylinesRef.current = null;
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
      if (userNavSourceRef.current) {
        viewer.dataSources.remove(userNavSourceRef.current, true);
        userNavSourceRef.current = null;
      }
      viewer.destroy();
    };
  }, [viewerResetCounter]);

  // Sync 3D Falling Rain Post-Processing FX with State
  useEffect(() => {
    if (rainPostProcessRef.current) {
      rainPostProcessRef.current.enabled = rainFxEnabled;
    }
  }, [rainFxEnabled]);

  // Switch to photographic satellite ground in Cockpit View and restore user basemap on exit
  useEffect(() => {
    if (viewerRef.current) {
      applyImageryLayers(viewerRef.current, surfaceMode);
    }
  }, [surfaceMode]);

  // Handle camera fly-to on targetLocation changes (suppressed while locked inside Cockpit View)
  useEffect(() => {
    if (cockpitAircraftRef.current) return;
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
        ds.show = !cockpitAircraftRef.current;
        viewer.dataSources.add(ds);
        viewer.scene.requestRender();
      })
      .catch(() => {});
  }, [layers, geometries, webglStatus]);

  const cloudsEnabled = layers.find((l) => l.id === 'live-clouds')?.enabled ?? true;

  // Synchronize the latest complete EUMETSAT IR image; retain the previous image on failure
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    onCloudTileErrorRef.current?.(0);

    if (!cloudsEnabled || !cloudFrame) {
      if (cloudImageryLayerRef.current) {
        try {
          if (viewer.imageryLayers.contains(cloudImageryLayerRef.current)) {
            viewer.imageryLayers.remove(cloudImageryLayerRef.current);
          }
        } catch {}
        cloudImageryLayerRef.current = null;
        viewer.scene.requestRender();
      }
      return;
    }

    let cancelled = false;
    void loadCloudImage(cloudFrame).then(async ({ url }) => {
      const provider = await SingleTileImageryProvider.fromUrl(url, {
        credit: 'Contains modified EUMETSAT / multimission infrared data ' + cloudFrame.utcIso.slice(0, 4),
      });
      if (cancelled || viewer.isDestroyed()) return;
      const previous = cloudImageryLayerRef.current;
      const next = viewer.imageryLayers.addImageryProvider(provider);
      next.alpha = 0.78;
      cloudImageryLayerRef.current = next;
      if (previous && previous !== next && viewer.imageryLayers.contains(previous)) {
        viewer.imageryLayers.remove(previous);
      }
      viewer.scene.requestRender();
    }).catch(() => {
      if (!cancelled) onCloudTileErrorRef.current?.(1);
    });
    return () => { cancelled = true; };
  }, [cloudsEnabled, cloudFrame, basemapGeneration, webglStatus]);

  // Keep RainViewer radar metadata updated
  useEffect(() => {
    let active = true;
    const updateRadarMetadata = () => {
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then((res) => res.json())
        .then((data) => {
          if (!active) return;
          const past = data?.radar?.past;
          if (past && past.length > 0) {
            radarFramePathRef.current = past[past.length - 1].path;
          }
        })
        .catch(() => {});
    };
    updateRadarMetadata();
    const timer = setInterval(updateRadarMetadata, 10 * 60 * 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  // Synchronize Multi-Domain 3D Entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    if (streamCancelRef.current) {
      streamCancelRef.current();
      streamCancelRef.current = null;
    }
    let isCancelled = false;
    streamCancelRef.current = () => {
      isCancelled = true;
    };

    viewer.entities.removeAll();
    viewer.entities.show = !cockpitAircraftRef.current;
    const layerMap = new Map(layers.map((l) => [l.id, l.enabled]));

    // Weather Radar Layer (RainViewer Live Doppler Radar)
    const radarEnabled = layerMap.get('weather-radar') ?? true;
    if (radarEnabled) {
      if (
        !radarImageryLayerRef.current ||
        !viewer.imageryLayers.contains(radarImageryLayerRef.current)
      ) {
        radarImageryLayerRef.current = null;
        const framePath = radarFramePathRef.current || '/v2/radar/ce6b5686c092';
        try {
          const radarProvider = new UrlTemplateImageryProvider({
            url: `https://tilecache.rainviewer.com${framePath}/512/{z}/{x}/{y}/2/1_1.png`,
            maximumLevel: 7,
            credit: 'RainViewer Live Doppler Radar',
          });
          const rLayer = viewer.imageryLayers.addImageryProvider(radarProvider);
          rLayer.alpha = 0.70;
          radarImageryLayerRef.current = rLayer;
        } catch (err) {
          console.warn('Could not add RainViewer radar layer:', err);
        }
      }
    } else if (radarImageryLayerRef.current) {
      viewer.imageryLayers.remove(radarImageryLayerRef.current);
      radarImageryLayerRef.current = null;
    }

    // 1. Live EUMETSAT Infrared Satellite Clouds (Cockpit local cloud estimate)
    const cloudsEnabled = layerMap.get('live-clouds') ?? true;
    const cloudBillboards = cloudBillboardsRef.current ?? viewer.scene.primitives.add(new BillboardCollection());
    cloudBillboardsRef.current = cloudBillboards;
    cloudBillboards.show = Boolean(cloudsEnabled && cockpitAircraftRef.current);

    if (!cloudsEnabled) {
      cloudBillboards.removeAll();
      cloudsListRef.current = [];
    }

    // 2. Illustrative Prevailing Wind Model (Thin flowing streamlines without dots or glow)
    const windEnabled = layerMap.get('wind-streamlines') ?? true;
    const windPolylines = windPolylinesRef.current ?? viewer.scene.primitives.add(new PolylineCollection());
    windPolylinesRef.current = windPolylines;
    windPolylines.show = Boolean(windEnabled && !cockpitAircraftRef.current);

    if (!windEnabled) {
      windPolylines.removeAll();
      windParticlesRef.current = [];
    } else if (windParticlesRef.current.length === 0) {
      const particles = [];
      const particleCount = isMobileRef.current ? 220 : 360;
      const lineWidth = isMobileRef.current ? 1.1 : 1.4;
      for (let i = 0; i < particleCount; i++) {
        const lon = (Math.random() - 0.5) * 360;
        const lat = (Math.random() - 0.5) * 150;
        const altMeters = 5000 + Math.random() * 12000;
        const { headingDeg, speed } = getAtmosphericWindVector(lat, lon);
        const rad = (headingDeg * Math.PI) / 180.0;

        const tailDeg = Math.min(2.2, 0.7 + speed * 2.4);
        const tailLon = lon - Math.sin(rad) * tailDeg;
        const tailLat = lat - Math.cos(rad) * tailDeg;
        const midLon = (lon + tailLon) / 2.0;
        const midLat = (lat + tailLat) / 2.0;

        const initialCart = [
          Cartesian3.fromDegrees(lon, lat, altMeters),
          Cartesian3.fromDegrees(midLon, midLat, altMeters),
          Cartesian3.fromDegrees(tailLon, tailLat, altMeters),
        ];

        const line = windPolylines.add({
          positions: initialCart,
          width: lineWidth,
          material: Material.fromType('Color', {
            color: Color.fromCssColorString('#bae6fd').withAlpha(0.42),
          }),
        });

        particles.push({
          line,
          lon,
          lat,
          altMeters,
          speed,
          headingDeg,
          age: Math.random() * 6.0,
          maxAge: 4.5 + Math.random() * 3.5,
        });
      }
      windParticlesRef.current = particles;
    }

    const aircraftBillboards = aircraftBillboardsRef.current ?? viewer.scene.primitives.add(new BillboardCollection());
    const satelliteBillboards = satelliteBillboardsRef.current ?? viewer.scene.primitives.add(new BillboardCollection());
    const cameraBillboards = cameraBillboardsRef.current ?? viewer.scene.primitives.add(new BillboardCollection());
    aircraftBillboardsRef.current = aircraftBillboards;
    satelliteBillboardsRef.current = satelliteBillboards;
    cameraBillboardsRef.current = cameraBillboards;

    cameraBillboards.removeAll();

    // Differential kinematic tracking for Aircraft: Re-use billboards and soft-blend coordinates to eliminate 15s snapping/jerkiness
    const existingAircraftMap = new Map<string, typeof aircraftKinematicsRef.current[0]>();
    for (const item of aircraftKinematicsRef.current) {
      const id = item.billboard.id?._worldosData?.entity_id || item.billboard.id?._worldosData?.id || item.billboard.id?._worldosData?.canonical_name;
      if (id) existingAircraftMap.set(id, item);
    }

    if (layerMap.get('aircraft-states') && aircraft.length > 0) {
      const activeIds = new Set<string>();
      const nextKinematics: typeof aircraftKinematicsRef.current = [];

      for (let i = 0; i < aircraft.length; i++) {
        const a = aircraft[i];
        if (
          typeof a.longitude !== 'number' ||
          typeof a.latitude !== 'number' ||
          isNaN(a.longitude) ||
          isNaN(a.latitude)
        ) {
          continue;
        }

        const acId = a.entity_id || a.id || a.canonical_name || `ac-${i}`;
        activeIds.add(acId);

        const altMeters = Math.max(
          150,
          Math.min(15000, a.attributes?.geo_altitude || a.attributes?.baro_altitude || 10000)
        );
        const isGround = a.attributes?.on_ground ?? false;

        const attr = a.attributes || {};
        const callsign = (attr.callsign || a.canonical_name || '').trim().toUpperCase();
        const origin = (attr.origin_country || '').trim().toLowerCase();
        const alt = attr.baro_altitude ?? attr.geo_altitude ?? 0;
        const vel = attr.velocity ?? 0;
        const isInternational = (alt > 9500 && vel > 200) ||
          /^(BAW|DLH|AFR|UAE|QTR|SIA|ANA|JAL|QFA|KLM|ETD|THY|CPA|CAL|EVA|CSN|CCA|CES|VIR|AIC|ETH|SVA)/.test(callsign) ||
          (origin && origin !== 'united states' && (a.longitude > -125 && a.longitude < -68 && a.latitude > 25 && a.latitude < 49));
        (a.attributes as any).is_international = isInternational;

        // 3-Part Division: Military (Amber), Commercial (Sky Blue), Private / Other (Emerald Mint)
        const classification = attr.classification || (isInternational ? 'commercial' : 'private');
        const acImage = isGround
          ? AIRPLANE_ICON_GROUND
          : classification === 'military'
          ? AIRPLANE_ICON_MILITARY
          : classification === 'commercial'
          ? AIRPLANE_ICON_COMMERCIAL
          : AIRPLANE_ICON_PRIVATE;

        const acVelocity = a.attributes?.velocity ?? 0;
        const trueTrack = a.attributes?.true_track ?? 0;

        const existing = existingAircraftMap.get(acId);
        if (existing) {
          // In-place reconciliation: update metadata and soft-blend coordinates
          existing.billboard.id = { _worldosType: 'aircraft', _worldosData: a };
          existing.billboard.image = acImage;
          existing.billboard.rotation = CesiumMath.toRadians(360 - trueTrack);

          const dLon = Math.abs(existing.lon - a.longitude);
          const dLat = Math.abs(existing.lat - a.latitude);
          if (dLon < 0.25 && dLat < 0.25) {
            existing.lon = existing.lon * 0.82 + a.longitude * 0.18;
            existing.lat = existing.lat * 0.82 + a.latitude * 0.18;
          } else {
            existing.lon = a.longitude;
            existing.lat = a.latitude;
          }
          existing.altMeters = altMeters;
          existing.velocityMps = acVelocity;
          existing.trackDeg = trueTrack;
          existing.billboard.position = Cartesian3.fromDegrees(existing.lon, existing.lat, altMeters);
          nextKinematics.push(existing);
        } else {
          const position = Cartesian3.fromDegrees(a.longitude, a.latitude, altMeters);
          const acBillboard = aircraftBillboards.add({
            id: { _worldosType: 'aircraft', _worldosData: a },
            position,
            image: acImage,
            rotation: CesiumMath.toRadians(360 - trueTrack),
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(1.5e2, 1.2, 1.5e7, 0.45),
            distanceDisplayCondition: new DistanceDisplayCondition(100.0, 1.4e7),
          });
          if (!isGround && acVelocity > 10) {
            nextKinematics.push({
              billboard: acBillboard,
              lon: a.longitude,
              lat: a.latitude,
              altMeters,
              velocityMps: acVelocity,
              trackDeg: trueTrack,
            });
          }
        }
      }

      // Remove stale aircraft billboards
      for (const [id, item] of existingAircraftMap) {
        if (!activeIds.has(id)) {
          aircraftBillboards.remove(item.billboard);
        }
      }
      aircraftKinematicsRef.current = nextKinematics;
    } else {
      aircraftBillboards.removeAll();
      aircraftKinematicsRef.current = [];
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

    // 2.2 Global Marine Deep-Water Seaports & Gateways
    if (layerMap.get('maritime-vessels')) {
      for (const port of GLOBAL_SEAPORTS) {
        const position = Cartesian3.fromDegrees(port.longitude, port.latitude, 0);
        const ent = viewer.entities.add({
          position,
          billboard: {
            image: PORT_ICON_TEAL,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(1.5e2, 1.2, 8.0e6, 0.4),
            distanceDisplayCondition: new DistanceDisplayCondition(100.0, 1.2e7),
          },
          label: {
            text: `⚓ ${port.name}`,
            font: '10px "JetBrains Mono", sans-serif',
            fillColor: Color.fromCssColorString('#14b8a6'),
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian2(0, -16),
            distanceDisplayCondition: new DistanceDisplayCondition(100.0, 3.5e6),
          },
        });
        (ent as any)._worldosType = 'place';
        (ent as any)._worldosData = {
          entity_id: port.id,
          canonical_name: port.name,
          category: 'seaport',
          latitude: port.latitude,
          longitude: port.longitude,
          attributes: {
            country: port.country,
            city: port.city,
            code: port.code,
            annual_teu: port.teu,
          },
        };
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
                image: SATELLITE_ICON_LUNAR,
                width: 22,
                height: 22,
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

    // 3. Space Satellites: Differential update with soft-blending (eliminates 15s jumping & jerkiness)
    const existingSatMap = new Map<string, typeof satelliteKinematicsRef.current[0]>();
    for (const item of satelliteKinematicsRef.current) {
      const id = item.billboard.id?._worldosData?.entity_id || item.billboard.id?._worldosData?.id || item.billboard.id?._worldosData?.canonical_name;
      if (id) existingSatMap.set(id, item);
    }

    if (layerMap.get('space-satellites') && satellites.length > 0) {
      const activeSatIds = new Set<string>();
      const nextSatKinematics: typeof satelliteKinematicsRef.current = [];

      for (let i = 0; i < satellites.length; i++) {
        const s = satellites[i];
        const altitudeKm = s.attributes?.altitude_km;
        if (!Number.isFinite(altitudeKm)) continue;
        const satId = s.entity_id || s.id || s.canonical_name || `sat-${i}`;
        activeSatIds.add(satId);

        const altMeters = (altitudeKm as number) * 1000;
        const incDeg = s.attributes?.inclination_deg || 51.6;
        const periodMin = s.attributes?.period_min || 92.8;

        // Differentiated by Orbit Tier:
        // LEO (< 2000 km) -> Electric Cyan (#00e5ff)
        // MEO (2000 - 30000 km, GPS/Nav) -> Amber Gold (#fbbf24)
        // GEO (> 30000 km, Weather/Telecom) -> Emerald Green (#10b981)
        const satImage =
          (altitudeKm as number) < 2000
            ? SATELLITE_ICON_LEO
            : (altitudeKm as number) < 30000
            ? SATELLITE_ICON_MEO
            : SATELLITE_ICON_GEO;

        const existing = existingSatMap.get(satId);
        if (existing) {
          existing.billboard.id = { _worldosType: 'satellite', _worldosData: s };
          existing.billboard.image = satImage;
          existing.billboard.rotation = CesiumMath.toRadians(360 - incDeg);

          const dLon = Math.abs(existing.lon - s.longitude);
          const dLat = Math.abs(existing.lat - s.latitude);
          if (dLon < 2.0 && dLat < 2.0) {
            existing.lon = existing.lon * 0.82 + s.longitude * 0.18;
            existing.lat = existing.lat * 0.82 + s.latitude * 0.18;
          } else {
            existing.lon = s.longitude;
            existing.lat = s.latitude;
          }
          existing.altMeters = altMeters;
          existing.periodMin = periodMin;
          existing.inclinationDeg = incDeg;
          existing.billboard.position = Cartesian3.fromDegrees(existing.lon, existing.lat, altMeters);
          nextSatKinematics.push(existing);
        } else {
          const position = Cartesian3.fromDegrees(s.longitude, s.latitude, altMeters);
          const satBillboard = satelliteBillboards.add({
            id: { _worldosType: 'satellite', _worldosData: s },
            position,
            image: satImage,
            rotation: CesiumMath.toRadians(360 - incDeg),
            width: 20,
            height: 20,
            scaleByDistance: new NearFarScalar(1.0e6, 1.3, 8.0e7, 0.75),
            // SATELLITES ONLY VISIBLE IN SPACE (> 400 KM ALTITUDE)!
            distanceDisplayCondition: new DistanceDisplayCondition(400_000.0, 1.0e8),
          });
          nextSatKinematics.push({
            billboard: satBillboard,
            lon: s.longitude,
            lat: s.latitude,
            altMeters,
            periodMin,
            inclinationDeg: incDeg,
          });
        }
      }

      // Remove stale satellites
      for (const [id, item] of existingSatMap) {
        if (!activeSatIds.has(id)) {
          satelliteBillboards.remove(item.billboard);
        }
      }
      satelliteKinematicsRef.current = nextSatKinematics;
    } else {
      satelliteBillboards.removeAll();
      satelliteKinematicsRef.current = [];
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
          point: { heightReference: HeightReference.CLAMP_TO_GROUND, pixelSize: 8, color, outlineColor: Color.WHITE, outlineWidth: 1 },
        });
        (ent as any)._worldosType = 'event';
        (ent as any)._worldosData = event;
      }
    }

    // 4. Surveillance & Sensor Cameras: GTA 6 Time-Sliced Streaming (60 per animation frame)
    if (layerMap.get('surveillance-cameras') && cameras.length > 0) {
      let camIdx = 0;
      const camBatch = 60;
      const streamCameras = () => {
        if (isCancelled || !viewer || viewer.isDestroyed()) return;
        const end = Math.min(camIdx + camBatch, cameras.length);
        for (; camIdx < end; camIdx++) {
          const c = cameras[camIdx];
          const position = Cartesian3.fromDegrees(c.longitude, c.latitude, 0);
          cameraBillboards.add({
            id: { _worldosType: 'camera', _worldosData: c },
            position,
            image: CAMERA_ICON_EMERALD,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(1.5e2, 1.3, 2.0e7, 0.55),
          });
        }
        if (camIdx < cameras.length) {
          requestAnimationFrame(streamCameras);
        }
      };
      streamCameras();
    }

    // 5. Thermal Anomalies & Wildfires (NASA FIRMS): Ground-clamped Flame Icon
    if (layerMap.get('thermal-fires') && thermalEvents.length > 0) {
      for (const f of thermalEvents) {
        // Filter out South Atlantic Anomaly (SAA) cosmic radiation ocean glitches
        if (
          (f.latitude >= 5.0 && f.latitude <= 35.0 && f.longitude >= -50.0 && f.longitude <= -22.0) ||
          (f.latitude >= 0.0 && f.latitude < 5.0 && f.longitude >= -45.0 && f.longitude <= -22.0) ||
          (f.latitude >= -35.0 && f.latitude < 0.0 && f.longitude >= -34.0 && f.longitude <= -12.0)
        ) {
          continue;
        }
        const position = Cartesian3.fromDegrees(f.longitude, f.latitude, 0);
        const ent = viewer.entities.add({
          position,
          billboard: {
            heightReference: HeightReference.CLAMP_TO_GROUND,
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
            heightReference: HeightReference.CLAMP_TO_GROUND,
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

    // 7. Discovered Places, Stays, Dining & Nightlife (Google Places API New)
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
              ? `📍 ${place.name.toUpperCase()}\n${typeof place.rating === 'number' ? `★ ${place.rating.toFixed(1)} · ` : ''}${place.category.toUpperCase()}${place.price_level ? ` · ${place.price_level}` : ''}\n${place.formatted_address}`
              : `${place.name}${typeof place.rating === 'number' ? ` ★${place.rating.toFixed(1)}` : ''}`,
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

    // 10. Turn-by-Turn Road Route on 3D Surface
    if (activeRoadRoute && activeRoadRoute.polyline.length > 1) {
      const roadPositions = activeRoadRoute.polyline.map((p) =>
        Cartesian3.fromDegrees(p[0], p[1], 15)
      );

      viewer.entities.add({
        name: `Road Route: ${activeRoadRoute.origin_name} -> ${activeRoadRoute.destination_name}`,
        polyline: {
          positions: roadPositions,
          width: 6,
          clampToGround: true,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.45,
            color: Color.fromCssColorString('#00f0ff'), // Vibrant Neon Cyan
          }),
        },
      });

      // Road Origin Pin (Emerald)
      viewer.entities.add({
        position: Cartesian3.fromDegrees(
          activeRoadRoute.origin_coords[0],
          activeRoadRoute.origin_coords[1],
          20
        ),
        point: {
          pixelSize: 14,
          color: Color.fromCssColorString('#10b981'),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `START: ${activeRoadRoute.origin_name}`,
          font: 'bold 12px monospace',
          fillColor: Color.fromCssColorString('#10b981'),
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(0, -18),
        },
      });

      // Road Destination Pin (Rose)
      viewer.entities.add({
        position: Cartesian3.fromDegrees(
          activeRoadRoute.destination_coords[0],
          activeRoadRoute.destination_coords[1],
          20
        ),
        point: {
          pixelSize: 14,
          color: Color.fromCssColorString('#f43f5e'),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `DEST: ${activeRoadRoute.destination_name}`,
          font: 'bold 12px monospace',
          fillColor: Color.fromCssColorString('#f43f5e'),
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(0, -18),
        },
      });
    }

    // 11. Inbound International Flight Plan Corridor in 3D Geodesic Space
    if (activeFlightPlan && activeFlightPlan.waypoints_3d.length > 1) {
      const flightPositions = activeFlightPlan.waypoints_3d.map((w) =>
        Cartesian3.fromDegrees(w[0], w[1], Math.max(100, w[2]))
      );

      viewer.entities.add({
        name: `Flight ${activeFlightPlan.flight_number}: ${activeFlightPlan.origin_airport.iata} -> ${activeFlightPlan.destination_airport.iata}`,
        polyline: {
          positions: flightPositions,
          width: 5,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.45,
            color: Color.fromCssColorString('#38bdf8'), // Sky Blue
          }),
        },
      });

      // Flight Origin Airport Pin
      viewer.entities.add({
        position: Cartesian3.fromDegrees(
          activeFlightPlan.origin_airport.longitude,
          activeFlightPlan.origin_airport.latitude,
          500
        ),
        point: {
          pixelSize: 13,
          color: Color.fromCssColorString('#38bdf8'),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `🛫 ${activeFlightPlan.origin_airport.iata} (${activeFlightPlan.origin_city})`,
          font: 'bold 12px monospace',
          fillColor: Color.fromCssColorString('#38bdf8'),
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(0, -16),
        },
      });

      // Flight Destination Airport Pin
      viewer.entities.add({
        position: Cartesian3.fromDegrees(
          activeFlightPlan.destination_airport.longitude,
          activeFlightPlan.destination_airport.latitude,
          500
        ),
        point: {
          pixelSize: 13,
          color: Color.fromCssColorString('#10b981'),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `🛬 ${activeFlightPlan.destination_airport.iata} (${activeFlightPlan.destination_city})`,
          font: 'bold 12px monospace',
          fillColor: Color.fromCssColorString('#10b981'),
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(0, -16),
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
    activeRoadRoute,
    activeFlightPlan,
    discoveredPlaces,
    selectedPlace,
    basemapGeneration,
    webglStatus,
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

    if (selectedItem?.type === 'aircraft') {
      const plane = selectedItem.data;
      const attr = plane?.attributes || {};
      const dep = attr.departure_airport;
      const dest = attr.destination_airport;
      const planeLon = plane?.longitude ?? attr.longitude;
      const planeLat = plane?.latitude ?? attr.latitude;
      const planeAlt = attr.baro_altitude ?? (plane?.value || 10000);

      const tracks: any[] = [];

      if (dep && dest && typeof planeLon === 'number' && typeof planeLat === 'number') {
        // 1. Departed flight segment (origin airport -> current aircraft position)
        const flownLine = viewer.entities.add({
          polyline: {
            positions: [
              Cartesian3.fromDegrees(dep.longitude, dep.latitude, 20),
              Cartesian3.fromDegrees(planeLon, planeLat, Math.max(planeAlt, 500)),
            ],
            width: 4.0,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.35,
              color: Color.fromCssColorString('#38bdf8'),
            }),
          },
        });
        tracks.push(flownLine);

        // 2. Remaining flight segment (current aircraft position -> destination airport)
        const remainingLine = viewer.entities.add({
          polyline: {
            positions: [
              Cartesian3.fromDegrees(planeLon, planeLat, Math.max(planeAlt, 500)),
              Cartesian3.fromDegrees(dest.longitude, dest.latitude, 20),
            ],
            width: 3.5,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.25,
              color: Color.fromCssColorString('#10b981').withAlpha(0.85),
            }),
          },
        });
        tracks.push(remainingLine);

        // 3. Departure airport visual pin
        const depPin = viewer.entities.add({
          position: Cartesian3.fromDegrees(dep.longitude, dep.latitude, 10),
          point: {
            pixelSize: 10,
            color: Color.fromCssColorString('#38bdf8'),
            outlineColor: Color.BLACK,
            outlineWidth: 2,
          },
          label: {
            text: `DEP: ${dep.iata || dep.icao} (${dep.city || dep.name})`,
            font: '11px sans-serif',
            fillColor: Color.WHITE,
            showBackground: true,
            backgroundColor: Color.fromCssColorString('rgba(15, 23, 42, 0.9)'),
            pixelOffset: new Cartesian2(0, -18),
          },
        });
        tracks.push(depPin);

        // 4. Destination airport visual pin
        const destPin = viewer.entities.add({
          position: Cartesian3.fromDegrees(dest.longitude, dest.latitude, 10),
          point: {
            pixelSize: 10,
            color: Color.fromCssColorString('#10b981'),
            outlineColor: Color.BLACK,
            outlineWidth: 2,
          },
          label: {
            text: `ARR: ${dest.iata || dest.icao} (${dest.city || dest.name})`,
            font: '11px sans-serif',
            fillColor: Color.WHITE,
            showBackground: true,
            backgroundColor: Color.fromCssColorString('rgba(15, 23, 42, 0.9)'),
            pixelOffset: new Cartesian2(0, -18),
          },
        });
        tracks.push(destPin);

        selectedHighlightRef.current = {
          entity: null,
          width: 24,
          height: 24,
          tracks,
        };
      }
    }
    viewer.scene.requestRender();
  }, [selectedItem, satellites]);

  // Cinematic 3D camera fly-to when a venue/stay is selected (suppressed in Cockpit View)
  useEffect(() => {
    if (cockpitAircraftRef.current) return;
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

  // Live Google Maps-Style 3D User Navigation Puck & Driver Follow Camera
  useEffect(() => {
    const viewer = viewerRef.current;
    const navDs = userNavSourceRef.current;
    if (!viewer || !navDs) return;

    if (!userNavState || !userNavState.isActive) {
      navDs.entities.removeAll();
      if (isCameraLockedToNavRef.current) {
        viewer.camera.lookAtTransform(Matrix4.IDENTITY);
        isCameraLockedToNavRef.current = false;
      }
      return;
    }

    const [lon, lat] = userNavState.currentCoords;
    const heading = userNavState.heading;
    const accuracy = userNavState.accuracy_m || 20;

    navDs.entities.suspendEvents();
    navDs.entities.removeAll();

    // 1. Accuracy Halo on ground
    navDs.entities.add({
      name: 'User Accuracy Halo',
      position: Cartesian3.fromDegrees(lon, lat, 2),
      ellipse: {
        semiMinorAxis: accuracy,
        semiMajorAxis: accuracy,
        material: Color.fromCssColorString('#00d2ff').withAlpha(0.18),
        outline: true,
        outlineColor: Color.fromCssColorString('#00d2ff').withAlpha(0.6),
        outlineWidth: 2,
        height: 2,
      },
    });

    // 2. Forward Direction Indicator (Heading Beam)
    const headingRad = CesiumMath.toRadians(heading);
    const forwardDistM = 25;
    const dLat = (forwardDistM * Math.cos(headingRad)) / 111320;
    const dLon = (forwardDistM * Math.sin(headingRad)) / (111320 * Math.cos((lat * Math.PI) / 180));
    const aheadPos = Cartesian3.fromDegrees(lon + dLon, lat + dLat, 6);

    navDs.entities.add({
      name: 'User Heading Beam',
      polyline: {
        positions: [Cartesian3.fromDegrees(lon, lat, 5), aheadPos],
        width: 5,
        clampToGround: true,
        material: new PolylineGlowMaterialProperty({
          glowPower: 0.4,
          color: Color.fromCssColorString('#00f0ff'),
        }),
      },
    });

    // 3. User Location Puck (Glowing Cyan-Blue with Crisp White Border)
    navDs.entities.add({
      name: 'User Navigation Puck',
      position: Cartesian3.fromDegrees(lon, lat, 8),
      point: {
        pixelSize: 22,
        color: Color.fromCssColorString('#00d2ff'),
        outlineColor: Color.WHITE,
        outlineWidth: 3.5,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });

    navDs.entities.resumeEvents();

    // 4. Driver 3D Camera Follow Mode
    if (userNavState.isCameraFollowing) {
      isCameraLockedToNavRef.current = true;
      if (userNavState.hasArrived) {
        viewer.camera.lookAt(
          Cartesian3.fromDegrees(lon, lat, 10),
          new HeadingPitchRange(headingRad, CesiumMath.toRadians(-40), 200)
        );
      } else {
        const driverPitch = CesiumMath.toRadians(-26.0); // tilted 3D driver perspective
        const followRange = 75.0; // 75 meters behind vehicle
        viewer.camera.lookAt(
          Cartesian3.fromDegrees(lon, lat, 4),
          new HeadingPitchRange(headingRad, driverPitch, followRange)
        );
      }
    } else if (isCameraLockedToNavRef.current) {
      viewer.camera.lookAtTransform(Matrix4.IDENTITY);
      isCameraLockedToNavRef.current = false;
    }
    viewer.scene.requestRender();
  }, [userNavState]);

  const handleRetryGlobe = () => {
    setForceWebgl1Retry(false);
    setWebglStatus('checking');
    setWebglErrorMessage(null);
    setViewerResetCounter((c) => c + 1);
  };

  return (
    <div className="globe-stage-wrapper">
      <div ref={containerRef} className="globe-container-3d" />
      {surfaceNotice && (
        <div className="terrain-status" role="status">
          {surfaceNotice}
        </div>
      )}
      {(webglStatus === 'unavailable' || webglStatus === 'render-error') && (
        <div className="globe-recovery-overlay" role="alert" aria-live="polite">
          <div className="globe-recovery-card">
            <div className="globe-recovery-title">3D GLOBE RENDERING PAUSED</div>
            <p className="globe-recovery-msg">
              {webglErrorMessage ||
                'Your browser could not initialize a WebGL 3D graphics context.'}
            </p>
            <p className="globe-recovery-sub">
              Layer controls, place discovery, navigation, and Roger AI assistant remain fully usable.
            </p>
            <button
              type="button"
              className="globe-recovery-btn"
              onClick={handleRetryGlobe}
            >
              Retry 3D Globe
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
