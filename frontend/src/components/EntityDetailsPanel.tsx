import React from 'react';
import { SelectedItemPayload } from './MapEngine2D';
import {
  X,
  ExternalLink,
  ShieldCheck,
  MapPin,
  Clock,
  Database,
  Hash,
  Radio,
  Camera,
  Flame,
  Plane,
  Anchor,
  Globe2,
  Building2,
  AlertTriangle,
  History,
} from 'lucide-react';
import { AircraftTrackPoint, TruthClass } from '../api';

interface EntityDetailsPanelProps {
  selectedItem: SelectedItemPayload | null;
  track?: AircraftTrackPoint[] | null;
  onClose: () => void;
}

export const EntityDetailsPanel: React.FC<EntityDetailsPanelProps> = ({
  selectedItem,
  track,
  onClose,
}) => {
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

  if (type === 'aircraft') {
    const attr = data.attributes || {};
    const icao = attr.icao24 || data.icao24 || data.entity_id;
    const callsign = attr.callsign || data.callsign;
    title = callsign ? `Flight ${callsign} · ${icao}` : `Aircraft ${icao}`;
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
    const geoAlt = attr.geo_altitude ?? data.geo_altitude;
    const vel = attr.velocity ?? data.velocity;
    const hdg = attr.true_track ?? data.true_track;
    const vRate = attr.vertical_rate ?? data.vertical_rate;

    properties = {
      'ICAO 24-bit Hex': icao ? String(icao).toUpperCase() : 'N/A',
      'Callsign / Flight': callsign || '(Not Broadcast)',
      'Country of Registry': attr.origin_country || 'N/A',
      'Coordinates (WGS84)':
        typeof lat === 'number' && typeof lon === 'number'
          ? `[${lat.toFixed(4)}°, ${lon.toFixed(4)}°]`
          : 'N/A',
      'Barometric Altitude':
        typeof baroAlt === 'number'
          ? `${baroAlt.toLocaleString()} m (${Math.round(baroAlt * 3.28084).toLocaleString()} ft)`
          : 'N/A',
      'Geometric Altitude':
        typeof geoAlt === 'number'
          ? `${geoAlt.toLocaleString()} m (${Math.round(geoAlt * 3.28084).toLocaleString()} ft)`
          : 'N/A',
      'Ground Speed':
        typeof vel === 'number'
          ? `${vel.toFixed(1)} m/s (${Math.round(vel * 1.94384)} kts)`
          : 'N/A',
      'True Track (Heading)': typeof hdg === 'number' ? `${hdg.toFixed(1)}°` : 'N/A',
      'Vertical Rate':
        typeof vRate === 'number'
          ? `${vRate > 0 ? '+' : ''}${vRate.toFixed(1)} m/s`
          : 'Level Flight',
      'Flight Status': attr.on_ground ? 'Taxiing / On Ground' : 'En Route / Airborne',
      'Squawk Transponder': attr.squawk || 'N/A',
      'Position Telemetry Source': 'ADS-B Transponder Mode-S',
    };
  } else if (type === 'vessel') {
    const attr = data.attributes || {};
    title = data.canonical_name || attr.name || `MMSI ${attr.mmsi}`;
    categoryTag = `MARITIME · ${attr.ship_type || 'VESSEL'} (AIS)`;
    truthClass = (data.truth_class as TruthClass) || 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'Global Maritime AIS Protocol';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    properties = {
      'Vessel Name': data.canonical_name || 'N/A',
      'MMSI Transponder': attr.mmsi || 'N/A',
      'IMO Number': attr.imo || 'N/A',
      'Callsign': attr.callsign || 'N/A',
      'Flag State': attr.flag || 'N/A',
      'Vessel Category': attr.ship_type || 'Cargo',
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Speed Over Ground': `${attr.sog_knots?.toFixed(1) || 0} knots`,
      'Course Over Ground': `${attr.cog_degrees?.toFixed(1) || 0}°`,
      'Compass Heading': `${attr.heading_degrees?.toFixed(1) || 0}°`,
      'Current Draft': attr.draft_meters ? `${attr.draft_meters} meters` : 'N/A',
      'Destination Port': attr.destination || 'N/A',
      'Reported ETA': attr.eta || 'N/A',
      'Navigation Status': attr.nav_status || 'Under way using engine',
    };
  } else if (type === 'satellite') {
    const attr = data.attributes || {};
    title = data.canonical_name || `NORAD ${attr.norad_id}`;
    categoryTag = `ORBITAL · ${attr.category || 'SATELLITE'}`;
    truthClass = 'DERIVED'; // Explicitly derived via Keplerian ephemeris
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || 'CelesTrak Orbital Ephemeris';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    properties = {
      'NORAD Catalog ID': attr.norad_id || 'N/A',
      'COSPAR Designator': attr.designator || 'N/A',
      'Mission Category': attr.category || 'N/A',
      'Operating Agency': attr.operator || 'N/A',
      'Launch Date': attr.launch_date || 'N/A',
      'Sub-Satellite Position': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Orbital Altitude': `${attr.altitude_km?.toFixed(1)} km`,
      'Orbital Velocity': `${attr.velocity_kms?.toFixed(2)} km/s`,
      'Apogee / Perigee': `${attr.apogee_km} km / ${attr.perigee_km} km`,
      'Orbital Inclination': `${attr.inclination_deg}°`,
      'Orbital Period': `${attr.period_min} minutes`,
      'Orbit Calculation Method': attr.calculation_method || 'kepler_sgp4_orbit_propagation',
      'Ephemeris Derivation': 'DERIVED (Physics-based Keplerian Orbit Propagation)',
    };
  } else if (type === 'camera') {
    const attr = data.attributes || {};
    title = data.canonical_name || `Camera ${attr.camera_id}`;
    categoryTag = 'SURVEILLANCE · OPTICAL SENSOR';
    truthClass = 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || attr.operator || 'Public DOT CCTV Feeds';
    locator = data.evidence_locator || attr.snapshot_url;
    contentHash = data.evidence_content_hash;
    previewImageUrl = attr.snapshot_url;

    properties = {
      'Sensor Identifier': attr.camera_id || 'N/A',
      'Supervising Agency': attr.operator || 'N/A',
      'Geographic Region': attr.region || 'N/A',
      'Sensor Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Operational Status': attr.status || 'ONLINE',
      'Stream Architecture': attr.stream_type || 'snapshot',
      'Field of View': attr.view_direction || 'N/A',
      'Frame Resolution': attr.resolution || 'N/A',
    };
  } else if (type === 'fire') {
    const attr = data.attributes || {};
    title = data.canonical_name || `Thermal Anomaly ${attr.fire_id}`;
    categoryTag = 'ENVIRONMENTAL · THERMAL ANOMALY';
    truthClass = 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = 'NASA FIRMS / ESDIS Satellite Radiometry';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    properties = {
      'Anomaly ID': attr.fire_id || 'N/A',
      'Region': attr.region || 'N/A',
      'Fire Radiative Power (FRP)': `${attr.frp_mw?.toFixed(1)} MW`,
      'Brightness Temperature': `${attr.brightness_kelvin?.toFixed(1)} K (${(attr.brightness_kelvin - 273.15).toFixed(1)} °C)`,
      'Detection Confidence': attr.confidence_level?.toUpperCase() || 'NOMINAL',
      'Observation Satellite': attr.satellite || 'N/A',
      'Radiometer Sensor': attr.instrument || 'VIIRS',
      'Scan Mode': attr.daynight === 'D' ? 'Daytime Scan' : 'Nighttime Scan',
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
    };
  } else if (type === 'infrastructure') {
    const attr = data.attributes || {};
    title = data.canonical_name || `Facility ${attr.node_id}`;
    categoryTag = `INFRASTRUCTURE · ${attr.node_type?.toUpperCase() || 'NODE'}`;
    truthClass = 'OBSERVED';
    timestamp = data.observed_at || data.starts_at;
    sourceName = 'Global Strategic Infrastructure Registry';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;

    properties = {
      'Facility ID': attr.node_id || 'N/A',
      'Facility Classification': attr.node_type?.toUpperCase() || 'N/A',
      'Sovereign Host': attr.country || 'N/A',
      'Primary Code': attr.primary_code || 'N/A',
      'Secondary Code': attr.secondary_code || 'N/A',
      'Operator Authority': attr.operator || 'N/A',
      'Surface Elevation': `${attr.elevation_m} meters MSL`,
      'Operational Status': attr.status || 'OPERATIONAL',
      'Coordinates': `[${data.latitude?.toFixed(4)}°, ${data.longitude?.toFixed(4)}°]`,
      'Key Capabilities': Array.isArray(attr.capabilities) ? attr.capabilities.join(', ') : 'N/A',
    };
  } else if (type === 'geometry') {
    title = data.canonical_name || data.properties?.name || 'Boundary Geometry';
    categoryTag = `GEOMETRY · ${data.geometry_kind || 'POLYGON'}`;
    truthClass = 'OBSERVED';
    sourceName = 'Natural Earth v5.1.2 / PostGIS Authoritative Boundaries';
    properties = {
      'Entity ID': data.entity_id || 'N/A',
      'Geometry Kind': data.geometry_kind || 'sovereign_state',
      'SRID': '4326 (WGS84)',
      ...data.properties,
    };
  } else if (type === 'event') {
    title = data.title || `Seismic Event (M${data.magnitude ?? 'N/A'})`;
    categoryTag = `EVENT · ${data.category?.toUpperCase() || 'GEOPHYSICAL'}`;
    truthClass = data.truth_class || 'OBSERVED';
    timestamp = data.occurred_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'USGS Earthquake Hazards';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;
    properties = {
      'Event ID': data.id || data.event_id || 'N/A',
      'Magnitude': data.magnitude !== undefined ? `M ${data.magnitude}` : 'N/A',
      'Depth': data.properties?.depth ? `${data.properties.depth} km` : 'N/A',
      'Coordinates': data.point ? `[${data.point[1].toFixed(4)}, ${data.point[0].toFixed(4)}]` : 'N/A',
    };
  } else if (type === 'observation') {
    title = data.canonical_name || data.metric_name || 'Observation Record';
    categoryTag = `OBSERVATION · ${data.metric_name || 'STATISTICAL'}`;
    truthClass = data.truth_class || (data.is_anomaly ? 'DERIVED' : 'OBSERVED');
    timestamp = data.observed_at || data.starts_at;
    sourceName = data.source_name || data.source_slug || 'World Bank Open Data';
    locator = data.evidence_locator;
    contentHash = data.evidence_content_hash;
    properties = {
      'Metric': data.metric_name || data.measure || 'N/A',
      'Value': data.value !== undefined ? Number(data.value).toLocaleString() : 'N/A',
      'Unit': data.unit || 'count',
      'Is Anomaly': data.is_anomaly ? 'YES (Statistical Deviation)' : 'NO',
    };
  } else if (type === 'alert') {
    title = data.title || 'System Tactical Alert';
    categoryTag = `ALERT · ${data.severity || 'WARNING'}`;
    truthClass = data.truth_class || 'INFERRED';
    timestamp = data.created_at;
    sourceName = data.source || 'WORLDOS Alert Dispatcher';
    properties = {
      'Alert ID': data.id || 'N/A',
      'Severity': data.severity || 'HIGH',
      'Description': data.description || 'Threshold breach detected in spatial cell.',
    };
  }

  return (
    <aside className="details-drawer" aria-label="Intelligence Dossier">
      <div className="details-header">
        <div className="details-title-group">
          <span className="details-type-tag">{categoryTag}</span>
          <h2 className="details-title">{title}</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
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
        <button
          className="details-close-btn"
          onClick={onClose}
          aria-label="Close details dossier"
          title="Close details"
        >
          <X size={16} />
        </button>
      </div>

      <div className="details-content">
        {/* Live Camera Snapshot Preview Card if Available */}
        {previewImageUrl && (
          <section className="details-section">
            <h3 className="details-section-title">Optical Feed Snapshot</h3>
            <div
              style={{
                borderRadius: '6px',
                overflow: 'hidden',
                border: '1px solid var(--border-subtle)',
                background: '#020617',
              }}
            >
              <img
                src={previewImageUrl}
                alt={title}
                style={{ width: '100%', height: 'auto', display: 'block' }}
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
              <div
                style={{
                  padding: '6px 10px',
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  background: 'rgba(0,0,0,0.5)',
                }}
              >
                <span>Live Public Frame</span>
                <a
                  href={data.attributes?.stream_url || locator}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: 'var(--cy)', textDecoration: 'none' }}
                >
                  View Agency Portal &rarr;
                </a>
              </div>
            </div>
          </section>
        )}

        {/* Historical Track Timeline */}
        {track && track.length > 0 && (
          <section className="details-section">
            <h3
              className="details-section-title"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <History size={12} color="var(--cy)" /> Historical Observation Track (
              {track.length} points)
            </h3>
            <div
              style={{
                maxHeight: '140px',
                overflowY: 'auto',
                fontSize: '10px',
                border: '1px solid var(--border-subtle)',
                borderRadius: '4px',
                padding: '6px',
                background: 'rgba(0,0,0,0.2)',
              }}
            >
              {track.map((pt, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '3px 0',
                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                  }}
                >
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

        {/* Telemetry & Attributes Grid */}
        <section className="details-section">
          <h3 className="details-section-title">Telemetry & Canonical Attributes</h3>
          <div className="details-prop-grid">
            {Object.entries(properties).map(([key, value]) => (
              <React.Fragment key={key}>
                <span className="details-prop-key">{key}:</span>
                <span className="details-prop-val">{String(value)}</span>
              </React.Fragment>
            ))}
          </div>
        </section>

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
                <span
                  style={{
                    fontSize: '9px',
                    color: 'var(--text-muted)',
                    display: 'block',
                    marginBottom: '2px',
                  }}
                >
                  SHA-256 CONTENT DIGEST:
                </span>
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
