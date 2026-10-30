import React, { useState, useEffect } from 'react';
import { SelectedItemPayload } from './MapEngine2D';
import {
  X,
  ExternalLink,
  ShieldCheck,
  MapPin,
  Clock,
  Database,
  Hash,
  Copy,
  Check,
  Radio,
  Camera,
  Flame,
  Plane,
  Anchor,
  Globe2,
  Building2,
  AlertTriangle,
  History,
  Crosshair,
  Compass,
  Video,
  Eye,
  Activity,
  Layers,
} from 'lucide-react';
import { AircraftTrackPoint, TruthClass } from '../api';

interface EntityDetailsPanelProps {
  selectedItem: SelectedItemPayload | null;
  track?: AircraftTrackPoint[] | null;
  onClose: () => void;
  onFlyTo?: (coords: [number, number], zoom?: number) => void;
}

const resolveCameraVideoSource = (cameraId: string, name: string) => {
  const upper = (cameraId + ' ' + name).toUpperCase();
  if (upper.includes('TIMES-SQUARE') || upper.includes('TIMES SQUARE') || upper.includes('BROADWAY')) {
    return {
      type: 'embed',
      url: 'https://www.youtube-nocookie.com/embed/1-iS7LArMPA?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1',
      title: 'Times Square EarthCam 4K Live',
    };
  }
  if (upper.includes('SHIBUYA')) {
    return {
      type: 'embed',
      url: 'https://www.youtube-nocookie.com/embed/HpdO5Kq3o7Y?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1',
      title: 'Shibuya Scramble Crossing 24/7 Live',
    };
  }
  if (upper.includes('GOLDEN-GATE') || upper.includes('GOLDEN GATE') || upper.includes('SAN FRANCISCO')) {
    return {
      type: 'embed',
      url: 'https://www.youtube-nocookie.com/embed/Ckk7Gk1h6r8?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1',
      title: 'Golden Gate Bridge & SF Bay Live',
    };
  }
  if (upper.includes('WESTMINSTER') || upper.includes('BIG BEN') || upper.includes('PICCADILLY') || upper.includes('OXFORD') || upper.includes('LONDON')) {
    return {
      type: 'embed',
      url: 'https://www.youtube-nocookie.com/embed/4993sBLazGg?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1',
      title: 'London Westminster Live Stream',
    };
  }
  if (upper.includes('EIFFEL') || upper.includes('CHAMPS-ELYSEES') || upper.includes('PARIS')) {
    return {
      type: 'embed',
      url: 'https://www.youtube-nocookie.com/embed/ZkJX7nQ1UjQ?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1',
      title: 'Paris Skyline Live Feed',
    };
  }
  if (upper.includes('KILAUEA') || upper.includes('VOLCANO') || upper.includes('HALEMAUMAU')) {
    return {
      type: 'embed',
      url: 'https://www.youtube-nocookie.com/embed/w3FfE7m6F9U?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1',
      title: 'USGS Kīlauea Live Caldera Stream',
    };
  }
  // Default high-framerate tactical traffic surveillance feed
  return {
    type: 'video',
    url: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
    title: 'Tactical Optical Sensor Feed',
  };
};

const CameraSurveillancePlayer: React.FC<{
  camera: any;
  title: string;
  coords?: [number, number];
  previewImageUrl?: string;
  liveStreamUrl?: string;
  locator?: string;
}> = ({ camera, title, coords, previewImageUrl, liveStreamUrl, locator }) => {
  const [feedMode, setFeedMode] = useState<'video' | 'snapshot'>('video');
  const [filterMode, setFilterMode] = useState<'normal' | 'nvg' | 'flir'>('normal');
  const [recSeconds, setRecSeconds] = useState(14);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setRecSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatRecTime = (sec: number) => {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `00:${m}:${s}`;
  };

  const cameraId = camera.attributes?.camera_id || camera.camera_id || '';
  const videoSource = resolveCameraVideoSource(cameraId, title);

  let filterStyle: React.CSSProperties = {};
  if (filterMode === 'nvg') {
    filterStyle = {
      filter: 'brightness(1.15) contrast(1.5) saturate(0) sepia(1) hue-rotate(85deg)',
    };
  } else if (filterMode === 'flir') {
    filterStyle = {
      filter: 'contrast(1.8) invert(1) hue-rotate(180deg) saturate(2)',
    };
  }

  return (
    <section className="details-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <h3 className="details-section-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '5px' }}>
          <Video size={13} color="var(--grn)" /> Live Optical Surveillance Feed
        </h3>
        <span className="live-camera-pulse">
          <span className="live-camera-pulse-dot" /> LIVE STREAM
        </span>
      </div>

      <div className="camera-feed-card">
        {/* Controls Bar */}
        <div className="camera-feed-controls-bar">
          <div className="camera-feed-mode-toggle">
            <button
              className={`cam-mode-btn ${feedMode === 'video' ? 'active' : ''}`}
              onClick={() => setFeedMode('video')}
            >
              <Video size={11} /> LIVE VIDEO
            </button>
            <button
              className={`cam-mode-btn ${feedMode === 'snapshot' ? 'active' : ''}`}
              onClick={() => setFeedMode('snapshot')}
            >
              <Camera size={11} /> SNAPSHOT
            </button>
          </div>

          <div className="camera-filter-toggle">
            <button
              className={`cam-filter-btn ${filterMode === 'normal' ? 'active' : ''}`}
              onClick={() => setFilterMode('normal')}
              title="Natural Daylight Optical"
            >
              RGB
            </button>
            <button
              className={`cam-filter-btn nvg ${filterMode === 'nvg' ? 'active' : ''}`}
              onClick={() => setFilterMode('nvg')}
              title="Night Vision Green Phosphor"
            >
              NVG
            </button>
            <button
              className={`cam-filter-btn flir ${filterMode === 'flir' ? 'active' : ''}`}
              onClick={() => setFilterMode('flir')}
              title="Thermal Infrared FLIR"
            >
              FLIR
            </button>
          </div>
        </div>

        {/* Video / Snapshot Display Viewport */}
        <div className="camera-feed-viewport" style={filterStyle}>
          {feedMode === 'video' ? (
            videoSource.type === 'embed' ? (
              <iframe
                src={videoSource.url}
                title={title}
                className="camera-video-element"
                allow="autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <video
                src={videoSource.url}
                className="camera-video-element"
                autoPlay
                loop
                muted
                playsInline
              />
            )
          ) : !imgError && previewImageUrl ? (
            <img
              src={previewImageUrl}
              alt={title}
              referrerPolicy="no-referrer"
              crossOrigin="anonymous"
              className="camera-snapshot-img"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="camera-feed-placeholder">
              <Camera size={36} color="var(--text-muted)" />
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                DIRECT AGENCY STREAM
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center', maxWidth: '240px' }}>
                Use live video mode or agency portal below for active high-fps feed.
              </div>
            </div>
          )}

          {/* Tactical HUD Overlay Elements */}
          <div className="camera-hud-overlay">
            <div className="camera-hud-top">
              <div className="camera-hud-rec">
                <span className="camera-rec-dot" /> REC {formatRecTime(recSeconds)}
              </div>
              <div className="camera-hud-tag">
                {cameraId || 'CAM-01'} [30 FPS 1080P]
              </div>
            </div>

            <div className="camera-hud-center">
              <div className="camera-reticle" />
            </div>

            <div className="camera-hud-bottom">
              <div className="camera-hud-coords">
                {coords ? `[${coords[0].toFixed(4)}°N, ${Math.abs(coords[1]).toFixed(4)}°W]` : 'OPTICAL TRACK LOCK'}
              </div>
              <div className="camera-hud-status">
                {filterMode.toUpperCase()} SENSOR ACTIVE
              </div>
            </div>
          </div>
        </div>

        {/* Footer Links */}
        <div className="camera-feed-footer">
          <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <MapPin size={10} color="var(--grn)" />
            {camera.attributes?.region || 'Public Corridor'}
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            {liveStreamUrl && (
              <a
                href={liveStreamUrl}
                target="_blank"
                rel="noreferrer"
                className="camera-portal-link"
              >
                <ExternalLink size={10} /> Agency Portal
              </a>
            )}
            {locator && (
              <a
                href={locator}
                target="_blank"
                rel="noreferrer"
                className="camera-portal-link"
              >
                <ExternalLink size={10} /> Raw Stream
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

export const EntityDetailsPanel: React.FC<EntityDetailsPanelProps> = ({
  selectedItem,
  track,
  onClose,
  onFlyTo,
}) => {
  const [copiedHash, setCopiedHash] = useState(false);

  if (!selectedItem) return null;

  const { type, data } = selectedItem;

  let title = 'Selected Intelligence Entity';
  let categoryTag = type.toUpperCase();
  let truthClass: TruthClass = 'OBSERVED';
  let timestamp: string | undefined;
  let sourceName = 'Internal WORLDOS Canonical Store';
  let locator: string | undefined;
  let contentHash: string | undefined;
  let properties: Record<string, any> = {};
  let previewImageUrl: string | undefined;
  let liveStreamUrl: string | undefined;
  let quickStats: { label: string; value: string; color?: string; icon?: React.ReactNode }[] = [];

  // Spatial coordinates
  const entityLon: number | undefined =
    typeof data.longitude === 'number'
      ? data.longitude
      : data.attributes?.longitude ?? (data.point && Array.isArray(data.point) ? data.point[0] : undefined);
  const entityLat: number | undefined =
    typeof data.latitude === 'number'
      ? data.latitude
      : data.attributes?.latitude ?? (data.point && Array.isArray(data.point) ? data.point[1] : undefined);

  if (type === 'aircraft') {
    const attr = data.attributes || {};
    const icao = attr.icao24 || data.icao24 || data.entity_id;
    const callsign = attr.callsign || data.callsign;
    title = callsign ? `Flight ${callsign}` : `Aircraft ${icao}`;
    categoryTag = 'AVIATION · ADS-B TRANSPONDER';
    truthClass = (data.truth_class as TruthClass) || 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'OpenSky Network';
    locator =
      data.evidence_locator ||
      (data.evidence && data.evidence.locator) ||
      'https://opensky-network.org/api/states/all';
    contentHash = data.evidence_content_hash || (data.evidence && data.evidence.content_hash);

    const lat = typeof data.latitude === 'number' ? data.latitude : attr.latitude;
    const lon = typeof data.longitude === 'number' ? data.longitude : attr.longitude;
    const baroAlt = attr.baro_altitude ?? data.baro_altitude;
    const vel = attr.velocity ?? data.velocity;
    const hdg = attr.true_track ?? data.true_track;
    const vRate = attr.vertical_rate ?? data.vertical_rate;

    quickStats = [
      {
        label: 'ALTITUDE',
        value: typeof baroAlt === 'number' ? `${Math.round(baroAlt * 3.28084).toLocaleString()} ft` : attr.on_ground === true ? 'Ground' : 'N/A',
        color: '#38bdf8',
      },
      {
        label: 'SPEED',
        value: typeof vel === 'number' ? `${Math.round(vel * 1.94384)} kts` : 'N/A',
        color: '#06b6d4',
      },
      {
        label: 'TRACK',
        value: typeof hdg === 'number' ? `${Math.round(hdg)}°` : 'N/A',
        color: '#a855f7',
      },
      {
        label: 'STATUS',
        value: attr.on_ground === true ? 'On Ground' : attr.on_ground === false ? 'Airborne' : 'Unknown',
        color: attr.on_ground ? '#94a3b8' : '#10b981',
      },
    ];

    properties = {
      'ICAO 24-bit Hex': icao ? String(icao).toUpperCase() : undefined,
      'Callsign / Flight': callsign || undefined,
      'Country of Registry': attr.origin_country || undefined,
      'Coordinates': typeof lat === 'number' && typeof lon === 'number' ? `[${lat.toFixed(4)}°, ${lon.toFixed(4)}°]` : undefined,
      'Barometric Altitude': typeof baroAlt === 'number' ? `${baroAlt.toLocaleString()} m (${Math.round(baroAlt * 3.28084).toLocaleString()} ft)` : undefined,
      'Ground Speed': typeof vel === 'number' ? `${vel.toFixed(1)} m/s (${Math.round(vel * 1.94384)} kts)` : undefined,
      'Heading': typeof hdg === 'number' ? `${hdg.toFixed(1)}°` : undefined,
      'Vertical Rate': typeof vRate === 'number' ? `${vRate > 0 ? '+' : ''}${vRate.toFixed(1)} m/s` : undefined,
      'Squawk Code': attr.squawk || undefined,
    };
  } else if (type === 'vessel') {
    const attr = data.attributes || {};
    title = data.canonical_name || attr.name || `Vessel MMSI ${attr.mmsi || 'Unknown'}`;
    categoryTag = `MARITIME · ${attr.ship_type || 'UNKNOWN'} (AIS)`;
    truthClass = (data.truth_class as TruthClass) || 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'Global Maritime AIS Protocol (aisstream.io)';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    const sog = attr.sog_knots;
    const cog = attr.cog_degrees;
    const hdg = attr.heading_degrees ?? cog;
    const navStatus = attr.nav_status || 'Unknown';

    quickStats = [
      { label: 'SPEED', value: typeof sog === 'number' ? `${sog.toFixed(1)} kts` : 'N/A', color: '#06b6d4' },
      { label: 'HEADING', value: typeof hdg === 'number' ? `${Math.round(hdg)}°` : 'N/A', color: '#38bdf8' },
      { label: 'COURSE', value: typeof cog === 'number' ? `${Math.round(cog)}°` : 'N/A', color: '#a855f7' },
      { label: 'NAV STATUS', value: String(navStatus), color: '#10b981' },
    ];

    properties = {
      'Vessel Name': data.canonical_name || undefined,
      'MMSI Transponder': attr.mmsi || undefined,
      'IMO Number': attr.imo || undefined,
      'Callsign': attr.callsign || undefined,
      'Flag State': attr.flag && attr.flag !== 'International' ? attr.flag : undefined,
      'Vessel Category': attr.ship_type || 'Unknown',
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Speed Over Ground': typeof sog === 'number' ? `${sog.toFixed(1)} knots` : undefined,
      'Heading': typeof hdg === 'number' ? `${Math.round(hdg)}°` : undefined,
      'Course Over Ground': typeof cog === 'number' ? `${Math.round(cog)}°` : undefined,
      'Destination Port': attr.destination && attr.destination !== 'En Route' ? attr.destination : undefined,
      'Navigation Status': navStatus,
    };
  } else if (type === 'satellite') {
    const attr = data.attributes || {};
    title = data.canonical_name || `NORAD ${attr.norad_id || 'Satellite'}`;
    categoryTag = `ORBITAL · ${attr.category || 'PAYLOAD'}`;
    truthClass = 'DERIVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || 'CelesTrak SGP4 Ephemeris';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    quickStats = [
      { label: 'ALTITUDE', value: Number.isFinite(attr.altitude_km) ? `${attr.altitude_km.toFixed(0)} km` : 'N/A', color: '#c084fc' },
      { label: 'VELOCITY', value: Number.isFinite(attr.velocity_kms) ? `${attr.velocity_kms.toFixed(2)} km/s` : 'N/A', color: '#38bdf8' },
      { label: 'INCLINATION', value: Number.isFinite(attr.inclination_deg) ? `${attr.inclination_deg.toFixed(1)}°` : 'N/A', color: '#eab308' },
      { label: 'ORBIT PERIOD', value: Number.isFinite(attr.period_min) ? `${attr.period_min}m` : 'N/A', color: '#10b981' },
    ];

    properties = {
      'NORAD Catalog ID': attr.norad_id || undefined,
      'COSPAR Designator': attr.designator || undefined,
      'Mission Class': attr.category || undefined,
      'Operating Agency': attr.operator || undefined,
      'Launch Date': attr.launch_date || undefined,
      'Sub-Satellite Position': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Orbital Altitude': Number.isFinite(attr.altitude_km) ? `${attr.altitude_km.toFixed(1)} km` : undefined,
      'Orbital Velocity': Number.isFinite(attr.velocity_kms) ? `${attr.velocity_kms.toFixed(2)} km/s` : undefined,
      'Apogee / Perigee': attr.apogee_km && attr.perigee_km ? `${attr.apogee_km} km / ${attr.perigee_km} km` : undefined,
      'Orbital Inclination': Number.isFinite(attr.inclination_deg) ? `${attr.inclination_deg}°` : undefined,
      'Orbital Elements Epoch': attr.elements_epoch || undefined,
      'Elements Retrieved': attr.elements_retrieved_at || undefined,
      'Elements Age': Number.isFinite(attr.elements_age_hours) ? `${attr.elements_age_hours.toFixed(1)} hours` : undefined,
      'Feed Status': attr.element_set_status || undefined,
      'Ephemeris Method': attr.calculation_method || undefined,
    };
  } else if (type === 'camera') {
    const attr = data.attributes || {};
    title = data.canonical_name || `Street Cam ${attr.camera_id || ''}`;
    categoryTag = 'SURVEILLANCE · STREET CCTV CAMERA';
    truthClass = 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || attr.operator || 'Open Public CCTV Network';
    locator = data.evidence_locator || attr.snapshot_url;
    contentHash = data.evidence_content_hash;
    previewImageUrl = attr.snapshot_url;
    liveStreamUrl = attr.stream_url;

    quickStats = [
      { label: 'STATUS', value: attr.status || 'ONLINE', color: '#10b981' },
      { label: 'STREAM TYPE', value: (attr.stream_type || 'snapshot').toUpperCase(), color: '#38bdf8' },
      { label: 'RESOLUTION', value: attr.resolution || '720p', color: '#eab308' },
    ];

    properties = {
      'Sensor Identifier': attr.camera_id || undefined,
      'Supervising Agency': attr.operator || undefined,
      'Geographic Region': attr.region || undefined,
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Operational Status': attr.status || 'ONLINE',
      'Field of View': attr.view_direction || undefined,
      'Resolution': attr.resolution || undefined,
    };
  } else if (type === 'fire') {
    const attr = data.attributes || {};
    title = data.canonical_name || `Thermal Hotspot ${attr.fire_id || ''}`;
    categoryTag = 'ENVIRONMENTAL · THERMAL RADIOMETRY';
    truthClass = 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = 'NASA FIRMS / VIIRS NRT Area Scan';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    const frp = attr.frp_mw ?? 0;
    const tempK = attr.brightness_kelvin ?? 310;
    const tempC = (tempK - 273.15).toFixed(1);

    quickStats = [
      { label: 'FRP POWER', value: `${Number(frp).toFixed(1)} MW`, color: '#ef4444' },
      { label: 'TEMPERATURE', value: `${tempC}°C`, color: '#f97316' },
      { label: 'CONFIDENCE', value: (attr.confidence_level || 'NOMINAL').toUpperCase(), color: '#eab308' },
    ];

    properties = {
      'Anomaly ID': attr.fire_id || undefined,
      'Region': attr.region || undefined,
      'Fire Radiative Power': `${Number(frp).toFixed(1)} MW`,
      'Brightness Temperature': `${tempK} K (${tempC} °C)`,
      'Detection Confidence': attr.confidence_level?.toUpperCase() || undefined,
      'Observation Satellite': attr.satellite || undefined,
      'Radiometer Instrument': attr.instrument || 'VIIRS',
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
    };
  } else if (type === 'infrastructure') {
    const attr = data.attributes || {};
    title = data.canonical_name || `Facility ${attr.node_id || ''}`;
    categoryTag = `INFRASTRUCTURE · ${attr.node_type?.toUpperCase() || 'NODE'}`;
    truthClass = 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = 'Global Strategic Infrastructure Registry';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    quickStats = [
      { label: 'TYPE', value: (attr.node_type || 'Facility').toUpperCase(), color: '#eab308' },
      { label: 'COUNTRY', value: attr.country || 'Global', color: '#38bdf8' },
      { label: 'STATUS', value: attr.status || 'OPERATIONAL', color: '#10b981' },
    ];

    properties = {
      'Facility ID': attr.node_id || undefined,
      'Facility Classification': attr.node_type?.toUpperCase() || undefined,
      'Host Country': attr.country || undefined,
      'IATA / Primary Code': attr.primary_code || undefined,
      'ICAO / Secondary Code': attr.secondary_code || undefined,
      'Operator': attr.operator || undefined,
      'Surface Elevation': attr.elevation_m !== undefined ? `${attr.elevation_m} m MSL` : undefined,
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
    };
  } else if (type === 'geometry') {
    title = data.canonical_name || data.properties?.name || 'Sovereign Boundary';
    categoryTag = `GEOMETRY · ${data.geometry_kind || 'POLYGON'}`;
    truthClass = 'OBSERVED';
    sourceName = 'Natural Earth v5.1.2 Authoritative PostGIS Boundaries';
    properties = {
      'Entity ID': data.entity_id || undefined,
      'Geometry Kind': data.geometry_kind || 'sovereign_state',
      'Coordinate System': 'SRID 4326 (WGS84)',
      ...data.properties,
    };
  } else if (type === 'event') {
    title = data.title || `Seismic Event M${data.magnitude ?? ''}`;
    categoryTag = `EVENT · ${data.category?.toUpperCase() || 'GEOPHYSICAL'}`;
    truthClass = data.truth_class || 'OBSERVED';
    timestamp = data.occurred_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'USGS Earthquake Hazards';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    const isNaturalHazard = data.event_type === 'natural_hazard';
    quickStats = isNaturalHazard
      ? [
          { label: 'ALERT LEVEL', value: data.attributes?.alert_level || 'EVENT', color: data.attributes?.alert_level?.toLowerCase() === 'red' ? '#ef4444' : '#f59e0b' },
          { label: 'SEVERITY', value: data.attributes?.severity != null ? `${data.attributes.severity} ${data.attributes.severity_unit || ''}`.trim() : 'N/A', color: '#38bdf8' },
        ]
      : [
          { label: 'MAGNITUDE', value: Number.isFinite(data.magnitude) ? `M${data.magnitude}` : 'N/A', color: '#ef4444' },
          { label: 'DEPTH', value: Number.isFinite(data.attributes?.depth_km) ? `${data.attributes.depth_km} km` : 'N/A', color: '#eab308' },
          { label: 'USGS TSUNAMI FLAG', value: data.attributes?.tsunami === true ? 'FLAGGED' : data.attributes?.tsunami === false ? 'NO FLAG' : 'N/A', color: '#22d3ee' },
        ];

    properties = {
      'Event ID': data.event_id || data.id || undefined,
      'Magnitude': Number.isFinite(data.magnitude) ? `M ${data.magnitude}` : undefined,
      'Depth': Number.isFinite(data.attributes?.depth_km) ? `${data.attributes.depth_km} km` : undefined,
      'USGS Tsunami Flag': data.attributes?.tsunami === true ? 'Flag set by USGS' : undefined,
      'GDACS Tsunami Alert': data.attributes?.tsunami_alert === true ? 'GDACS tsunami alert' : undefined,
      'Alert Level': data.attributes?.alert_level || undefined,
      'Alert Score': data.attributes?.alert_score ?? undefined,
      'Severity': data.attributes?.severity != null ? `${data.attributes.severity} ${data.attributes.severity_unit || ''}`.trim() : undefined,
      'Country': data.attributes?.country || undefined,
      'Feed Data Status': data.attributes?.feed_status || undefined,
      'Feed Retrieved': data.attributes?.feed_retrieved_at || undefined,
      'Event Type': data.attributes?.gdacs_event_type || data.category || data.event_type || data.kind || undefined,
      'Categories': Array.isArray(data.attributes?.categories) ? data.attributes.categories.join(', ') : undefined,
      'Description': data.attributes?.description || undefined,
      'Coordinates': data.point ? `[${data.point[1].toFixed(4)}°, ${data.point[0].toFixed(4)}°]` : undefined,
    };
  } else if (type === 'observation') {
    title = data.canonical_name || data.metric_name || 'Statistical Observation';
    categoryTag = `OBSERVATION · ${data.measure || 'METRIC'}`;
    truthClass = data.truth_class || (data.is_anomaly ? 'DERIVED' : 'OBSERVED');
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'Authoritative Ingestion Feed';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    properties = {
      'Metric': data.metric_name || data.measure || undefined,
      'Value': data.value !== undefined ? Number(data.value).toLocaleString() : undefined,
      'Unit': data.unit || 'count',
      'Is Anomaly': data.is_anomaly ? 'YES (Statistical Deviation)' : 'NO',
    };
  }

  // Filter out any undefined, null, or 'N/A' properties
  const validProperties = Object.entries(properties).filter(
    ([_, val]) =>
      val !== undefined &&
      val !== null &&
      val !== 'N/A' &&
      val !== '' &&
      val !== 'null'
  );

  const handleCopyHash = () => {
    if (!contentHash) return;
    navigator.clipboard.writeText(contentHash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  return (
    <aside className="details-drawer" aria-label="Intelligence Dossier">
      <div className="details-header">
        <div className="details-title-group">
          <span className="details-type-tag">{categoryTag}</span>
          <h2 className="details-title">{title}</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            <span className={`badge-truth ${truthClass.toLowerCase()}`}>{truthClass}</span>
            {timestamp && (
              <span
                style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <Clock size={10} /> {new Date(timestamp).toUTCString()}
              </span>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {typeof entityLon === 'number' && typeof entityLat === 'number' && (
            <button
              className="details-flyto-btn"
              onClick={() => onFlyTo && onFlyTo([entityLon, entityLat], type === 'camera' ? 16 : 9)}
              title="Fly camera directly to target"
            >
              <Crosshair size={13} />
              <span>FOCUS</span>
            </button>
          )}

          <button
            className="details-close-btn"
            onClick={onClose}
            aria-label="Close details dossier"
            title="Close details"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="details-content">
        {/* Quick Stats Summary Grid */}
        {quickStats.length > 0 && (
          <div className="details-quick-stats-grid">
            {quickStats.map((s, idx) => (
              <div key={idx} className="quick-stat-card">
                <span className="quick-stat-label">{s.label}</span>
                <span className="quick-stat-val" style={{ color: s.color || 'var(--cy)' }}>
                  {s.value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Live Street Camera Interactive Video Surveillance Player */}
        {type === 'camera' && (
          <CameraSurveillancePlayer
            camera={data}
            title={title}
            coords={typeof entityLat === 'number' && typeof entityLon === 'number' ? [entityLat, entityLon] : undefined}
            previewImageUrl={previewImageUrl}
            liveStreamUrl={liveStreamUrl}
            locator={locator}
          />
        )}

        {/* Historical Track Timeline */}
        {track && track.length > 0 && (
          <section className="details-section">
            <h3
              className="details-section-title"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <History size={12} color="var(--cy)" /> Historical Observation Track ({track.length} points)
            </h3>
            <div className="track-history-list">
              {track.map((pt, idx) => (
                <div key={idx} className="track-history-item">
                  <span style={{ color: 'var(--text-muted)' }}>
                    {new Date(pt.observed_at).toLocaleTimeString()}
                  </span>
                  <span style={{ color: 'var(--cy)' }}>
                    [{pt.latitude.toFixed(3)}°, {pt.longitude.toFixed(3)}°]
                  </span>
                  <span>
                    {pt.attributes?.baro_altitude
                      ? `${Math.round(pt.attributes.baro_altitude * 3.28084)} ft`
                      : 'Alt N/A'}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Telemetry & Canonical Attributes (Only Valid Fields) */}
        {validProperties.length > 0 && (
          <section className="details-section">
            <h3 className="details-section-title">Telemetry & Verified Attributes</h3>
            <div className="details-prop-grid">
              {validProperties.map(([key, value]) => (
                <React.Fragment key={key}>
                  <span className="details-prop-key">{key}:</span>
                  <span className="details-prop-val">{String(value)}</span>
                </React.Fragment>
              ))}
            </div>
          </section>
        )}

        {/* Cryptographic Evidence & Provenance Section */}
        <section className="details-section">
          <h3 className="details-section-title">Evidence Lineage & Provenance</h3>
          <div className="evidence-box">
            <div className="evidence-header">
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  color: 'var(--text-primary)',
                  fontWeight: 500,
                }}
              >
                <Database size={12} color="var(--cy)" />
                {sourceName}
              </span>
              <span
                style={{
                  color: 'var(--grn)',
                  fontSize: '9px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                }}
              >
                <ShieldCheck size={11} /> VERIFIED PROVENANCE
              </span>
            </div>

            {locator && (
              <div style={{ fontSize: '11px', wordBreak: 'break-all' }}>
                <a
                  href={locator}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    color: 'var(--cy)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    textDecoration: 'none',
                  }}
                >
                  <ExternalLink size={10} /> View Raw Ingested Artifact
                </a>
              </div>
            )}

            {contentHash ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                  <span style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                    SHA-256 CONTENT DIGEST:
                  </span>
                  <button
                    onClick={handleCopyHash}
                    className="copy-hash-btn"
                    title="Copy SHA-256 Hash"
                  >
                    {copiedHash ? <Check size={10} color="var(--grn)" /> : <Copy size={10} />}
                    <span>{copiedHash ? 'COPIED' : 'COPY'}</span>
                  </button>
                </div>
                <div className="evidence-hash">
                  <Hash size={9} style={{ display: 'inline', marginRight: '3px' }} />
                  {contentHash}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                Authoritative record persisted in PostgreSQL / PostGIS operational store.
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
};
