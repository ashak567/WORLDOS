import React, { useState, useMemo } from 'react';
import { AircraftState } from '../api';
import { EyeOff, Gauge, ArrowUpRight, Plane, Radio, AlertTriangle, ShieldCheck, Cloud } from 'lucide-react';
import { CloudBrightnessEstimate } from './SatelliteClouds';

interface CockpitHUDProps {
  aircraft: AircraftState;
  allAircraft?: AircraftState[];
  cloudEstimate?: CloudBrightnessEstimate | null;
  onExitCockpit: () => void;
}

function getDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180.0;
  const dLon = ((lon2 - lon1) * Math.PI) / 180.0;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180.0) * Math.cos((lat2 * Math.PI) / 180.0) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function getRelativeBearing(lat1: number, lon1: number, lat2: number, lon2: number, currentHeading: number): number {
  const y = Math.sin(((lon2 - lon1) * Math.PI) / 180.0) * Math.cos((lat2 * Math.PI) / 180.0);
  const x =
    Math.cos((lat1 * Math.PI) / 180.0) * Math.sin((lat2 * Math.PI) / 180.0) -
    Math.sin((lat1 * Math.PI) / 180.0) * Math.cos((lat2 * Math.PI) / 180.0) * Math.cos(((lon2 - lon1) * Math.PI) / 180.0);
  const brng = ((Math.atan2(y, x) * 180.0) / Math.PI + 360.0) % 360.0;
  return (brng - currentHeading + 360.0) % 360.0;
}

export const CockpitHUD: React.FC<CockpitHUDProps> = ({ aircraft, allAircraft = [], cloudEstimate = null, onExitCockpit }) => {
  const [radarRangeKm, setRadarRangeKm] = useState<number>(5); // default tactical proximity range: 5 km (or 1.5 km / 15 km)
  const attr = aircraft?.attributes || {};
  const callsign = String(attr.callsign || aircraft?.canonical_name || aircraft?.id || 'N/A').trim().toUpperCase();
  const origin = String(attr.origin_country || 'International Airspace');

  const formatAirport = (val: any, fallback: string): string => {
    if (!val) return fallback;
    if (typeof val === 'string') {
      const trimmed = val.trim();
      return trimmed === '[object Object]' || !trimmed ? fallback : trimmed.toUpperCase();
    }
    if (typeof val === 'object') {
      const code = val.iata || val.icao || val.code || val.name || val.city;
      if (code && typeof code === 'string') return code.trim().toUpperCase();
      return fallback;
    }
    return String(val).trim().toUpperCase() || fallback;
  };

  const dep = formatAirport(attr.departure_airport || (attr as any).origin, 'DEP');
  const dest = formatAirport(attr.destination_airport || (attr as any).destination, 'ARR');

  // Live flight telemetries
  const rawAlt = attr.geo_altitude || attr.baro_altitude || 10500;
  const altMeters = Number.isFinite(Number(rawAlt)) ? Number(rawAlt) : 10500;
  const altFeet = Math.round(altMeters * 3.28084);
  const flightLevel = Math.round(altFeet / 100);
  const rawVel = attr.velocity || 240;
  const velMps = Number.isFinite(Number(rawVel)) ? Number(rawVel) : 240;
  const airspeedKnots = Math.round(velMps * 1.94384);
  const mach = (velMps / 295.0).toFixed(2);
  const rawHeading = attr.true_track || 0;
  const heading = Math.round(Number.isFinite(Number(rawHeading)) ? Number(rawHeading) : 0);
  const rawVert = attr.vertical_rate || 0;
  const vertRateFpm = Math.round((Number.isFinite(Number(rawVert)) ? Number(rawVert) : 0) * 196.85);

  // Compass tape headings (render 5 marks centered around current heading)
  const headingMarks = [-40, -20, 0, 20, 40].map((offset) => {
    const deg = (heading + offset + 360) % 360;
    const label =
      deg === 0 || deg === 360
        ? 'N'
        : deg === 90
        ? 'E'
        : deg === 180
        ? 'S'
        : deg === 270
        ? 'W'
        : `${Math.round(deg / 10)}`;
    return { deg, offset, label };
  });

  // Calculate nearby air traffic for Cockpit TCAS Collision Avoidance Radar
  const myLon = aircraft?.longitude;
  const myLat = aircraft?.latitude;

  const nearbyTargets = useMemo(() => {
    if (typeof myLon !== 'number' || typeof myLat !== 'number' || !allAircraft.length) return [];
    const list: Array<{
      id: string;
      callsign: string;
      distKm: number;
      relBearing: number;
      altDiffFt: number;
      isDanger: boolean;
      isWarning: boolean;
      heading: number;
    }> = [];

    for (let i = 0; i < allAircraft.length; i++) {
      const other = allAircraft[i];
      if (other.id === aircraft.id || other.canonical_name === aircraft.canonical_name) continue;
      if (typeof other.longitude !== 'number' || typeof other.latitude !== 'number') continue;

      const dist = getDistanceKm(myLat, myLon, other.latitude, other.longitude);
      if (dist <= radarRangeKm) {
        const relBearing = getRelativeBearing(myLat, myLon, other.latitude, other.longitude, heading);
        const otherAlt = other.attributes?.geo_altitude || other.attributes?.baro_altitude || 10000;
        const altDiffFt = Math.round((otherAlt - altMeters) * 3.28084);
        const otherCallsign = (other.attributes?.callsign || other.canonical_name || other.id || 'AC').trim().toUpperCase();
        const otherHeading = other.attributes?.true_track || 0;
        const isDanger = dist <= 1.5 && Math.abs(altDiffFt) <= 1500;
        const isWarning = dist <= 3.5 && Math.abs(altDiffFt) <= 2500;

        list.push({
          id: other.id || `target-${i}`,
          callsign: otherCallsign,
          distKm: Math.round(dist * 10) / 10,
          relBearing,
          altDiffFt,
          isDanger,
          isWarning,
          heading: otherHeading,
        });
      }
    }
    return list.sort((a, b) => a.distKm - b.distKm);
  }, [allAircraft, aircraft, radarRangeKm, heading, altMeters, myLon, myLat]);

  const closestTarget = nearbyTargets[0];
  const hasDangerAlert = nearbyTargets.some((t) => t.isDanger);
  const hasWarningAlert = nearbyTargets.some((t) => t.isWarning);

  return (
    <div className="cockpit-hud-overlay" aria-label="First-Person Aircraft Cockpit Heads-Up Display">
      {/* Windshield Subtle Vignette Frame */}
      <div className="cockpit-canopy-vignette" />

      {/* Top Bar: Compass Heading Tape */}
      <div className="cockpit-heading-tape-container">
        <div className="cockpit-heading-box">
          <span className="cockpit-hud-heading-val">{heading.toString().padStart(3, '0')}°</span>
        </div>
        <div className="cockpit-tape-strip">
          {headingMarks.map((m, i) => (
            <div key={i} className="cockpit-tape-tick">
              <span className="tick-label">{m.label}</span>
              <div className={`tick-mark ${m.offset === 0 ? 'center' : ''}`} />
            </div>
          ))}
        </div>
        <div className="cockpit-tape-luber-line" />
      </div>

      {/* Center Flight Director / Artificial Horizon Pitch Ladder */}
      <div className="cockpit-artificial-horizon">
        <div className="pitch-ladder ladder-pos-10">
          <div className="ladder-line left" />
          <span className="ladder-deg">10</span>
          <div className="ladder-line right" />
        </div>
        <div className="pitch-ladder ladder-pos-05">
          <div className="ladder-line left short" />
          <span className="ladder-deg">5</span>
          <div className="ladder-line right short" />
        </div>

        {/* Center Aircraft Boresight / Waterline Symbol */}
        <div className="cockpit-boresight">
          <div className="boresight-wing left" />
          <div className="boresight-dot" />
          <div className="boresight-wing right" />
        </div>

        <div className="pitch-ladder ladder-neg-05">
          <div className="ladder-line dashed left short" />
          <span className="ladder-deg">-5</span>
          <div className="ladder-line dashed right short" />
        </div>
        <div className="pitch-ladder ladder-neg-10">
          <div className="ladder-line dashed left" />
          <span className="ladder-deg">-10</span>
          <div className="ladder-line dashed right" />
        </div>
      </div>

      {/* Left Airspeed Tape */}
      <div className="cockpit-tape airspeed-tape">
        <div className="tape-header">
          <Gauge size={12} />
          <span>IAS KTS</span>
        </div>
        <div className="tape-current-box">
          <span className="tape-current-val">{airspeedKnots}</span>
        </div>
        <div className="tape-ladder">
          <div className="ladder-val-tick">{airspeedKnots + 40}</div>
          <div className="ladder-val-tick">{airspeedKnots + 20}</div>
          <div className="ladder-val-tick center">{airspeedKnots}</div>
          <div className="ladder-val-tick">{Math.max(0, airspeedKnots - 20)}</div>
          <div className="ladder-val-tick">{Math.max(0, airspeedKnots - 40)}</div>
        </div>
        <div className="tape-footer">
          <span>MACH {mach}</span>
        </div>
      </div>

      {/* Right Altitude Tape */}
      <div className="cockpit-tape altitude-tape">
        <div className="tape-header">
          <ArrowUpRight size={12} />
          <span>ALT FT</span>
        </div>
        <div className="tape-current-box">
          <span className="tape-current-val">{altFeet.toLocaleString()}</span>
        </div>
        <div className="tape-ladder">
          <div className="ladder-val-tick">{altFeet + 1000}</div>
          <div className="ladder-val-tick">{altFeet + 500}</div>
          <div className="ladder-val-tick center">{altFeet}</div>
          <div className="ladder-val-tick">{Math.max(0, altFeet - 500)}</div>
          <div className="ladder-val-tick">{Math.max(0, altFeet - 1000)}</div>
        </div>
        <div className="tape-footer">
          <span>FL{flightLevel} · {vertRateFpm >= 0 ? `+${vertRateFpm}` : vertRateFpm} FPM</span>
        </div>
      </div>

      {/* Upper Tactical Cockpit Header Bar */}
      <div className="cockpit-tactical-header">
        <div className="cockpit-callsign-badge">
          <Plane size={15} color="#38bdf8" />
          <span className="callsign-text">{callsign}</span>
          <span className="origin-country-tag">{origin}</span>
        </div>

        <div className="cockpit-route-badge">
          <span className="route-leg">{dep}</span>
          <span className="route-arrow">⟶</span>
          <span className="route-leg">{dest}</span>
        </div>

        {cloudEstimate && (
          <div
            className="cockpit-cloud-estimate-badge"
            title="3D cloud layers rendered in cockpit view are visual height/density estimates derived from SSEC RealEarth satellite IR brightness."
          >
            <Cloud size={12} color="#e2e8f0" />
            <span>
              {cloudEstimate.hasClouds
                ? `3D clouds: visual estimate from satellite IR brightness (~${Math.round(cloudEstimate.estimatedBaseMeters)}–${Math.round(cloudEstimate.estimatedTopMeters)}m)`
                : '3D clouds: clear IR estimate from satellite brightness'}
            </span>
          </div>
        )}

        {/* TCAS Hazard Alert Banner */}
        {hasDangerAlert && (
          <div className="tcas-alert-pill danger pulse-danger">
            <AlertTriangle size={14} />
            <span>TRAFFIC ALERT: COLLISION HAZARD &lt; 1.5 KM!</span>
          </div>
        )}
        {!hasDangerAlert && hasWarningAlert && (
          <div className="tcas-alert-pill warning">
            <AlertTriangle size={14} />
            <span>TCAS ADVISORY: TRAFFIC NEARBY</span>
          </div>
        )}

        <button
          className="cockpit-exit-btn"
          onClick={onExitCockpit}
          title="Exit Cockpit View (Return to Orbital Overview)"
        >
          <EyeOff size={14} />
          <span>EXIT COCKPIT [ESC]</span>
        </button>
      </div>

      {/* Cockpit Tactical TCAS Air Traffic & Proximity Radar */}
      <div className={`cockpit-tcas-radar ${hasDangerAlert ? 'danger-border' : ''}`}>
        <div className="tcas-radar-header">
          <div className="tcas-title-group">
            <Radio size={13} className={hasDangerAlert ? 'pulse-icon red' : 'cyan'} />
            <span className="tcas-title">TCAS RADAR</span>
          </div>
          <div className="tcas-range-controls">
            <button
              className={`tcas-range-btn ${radarRangeKm === 1.5 ? 'active' : ''}`}
              onClick={() => setRadarRangeKm(1.5)}
              title="Close 1.5 KM Collision Proximity Radar"
            >
              1.5 KM
            </button>
            <button
              className={`tcas-range-btn ${radarRangeKm === 5 ? 'active' : ''}`}
              onClick={() => setRadarRangeKm(5)}
              title="Medium 5 KM Terminal Radar"
            >
              5 KM
            </button>
            <button
              className={`tcas-range-btn ${radarRangeKm === 15 ? 'active' : ''}`}
              onClick={() => setRadarRangeKm(15)}
              title="Wide 15 KM En-Route Radar"
            >
              15 KM
            </button>
          </div>
        </div>

        <div className="tcas-radar-scope">
          {/* Concentric Range Rings */}
          <div className="tcas-ring ring-outer">
            <span className="ring-label">{radarRangeKm}km</span>
          </div>
          <div className="tcas-ring ring-mid">
            <span className="ring-label">{(radarRangeKm * 0.66).toFixed(1)}km</span>
          </div>
          <div className="tcas-ring ring-inner">
            <span className="ring-label">{(radarRangeKm * 0.33).toFixed(1)}km</span>
          </div>

          {/* Crosshairs */}
          <div className="tcas-crosshair horiz" />
          <div className="tcas-crosshair vert" />

          {/* Rotating Phosphor Radar Sweep Line */}
          <div className="tcas-sweep-line" />

          {/* Own Aircraft Center Chevron Symbol */}
          <div className="tcas-own-aircraft">
            <div className="tcas-own-nose" />
          </div>

          {/* Plotted Nearby Aircraft Targets */}
          {nearbyTargets.map((target) => {
            const rad = ((target.relBearing - 90) * Math.PI) / 180.0;
            const rFraction = Math.min(0.96, target.distKm / radarRangeKm);
            const xPct = 50 + Math.cos(rad) * rFraction * 45;
            const yPct = 50 + Math.sin(rad) * rFraction * 45;
            const targetRelHeading = (target.heading - heading + 360) % 360;

            return (
              <div
                key={target.id}
                className={`tcas-target-blip ${target.isDanger ? 'danger' : target.isWarning ? 'warning' : 'normal'}`}
                style={{ left: `${xPct}%`, top: `${yPct}%` }}
                title={`${target.callsign}: ${target.distKm} km, ${target.altDiffFt >= 0 ? '+' : ''}${target.altDiffFt} ft`}
              >
                <div
                  className="tcas-blip-chevron"
                  style={{ transform: `rotate(${targetRelHeading}deg)` }}
                />
                <div className="tcas-blip-tag">
                  <span className="blip-callsign">{target.callsign}</span>
                  <span className="blip-dist">{target.distKm}km</span>
                  <span className="blip-alt">{target.altDiffFt >= 0 ? `+${Math.round(target.altDiffFt / 100)}` : Math.round(target.altDiffFt / 100)}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="tcas-radar-footer">
          {closestTarget ? (
            <span className={`tcas-status-text ${closestTarget.isDanger ? 'red' : closestTarget.isWarning ? 'amber' : 'green'}`}>
              {closestTarget.isDanger
                ? `COLLISION ALERT: ${closestTarget.callsign} AT ${closestTarget.distKm} KM`
                : `${nearbyTargets.length} TRAFFIC IN RANGE (CLOSEST: ${closestTarget.distKm} KM)`}
            </span>
          ) : (
            <span className="tcas-status-text green">
              <ShieldCheck size={11} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
              AIRSPACE CLEAR · NO TRAFFIC WITHIN {radarRangeKm} KM
            </span>
          )}
        </div>
      </div>

      {/* Bottom Avionics Status Bar */}
      <div className="cockpit-bottom-avionics-bar">
        <div className="avionics-item">
          <span className="lbl">NAV MODE</span>
          <span className="val cyan">LNAV / VNAV PTH</span>
        </div>
        <div className="avionics-item">
          <span className="lbl">GROUND SPEED</span>
          <span className="val">{airspeedKnots} KT</span>
        </div>
        <div className="avionics-item">
          <span className="lbl">GEO ALTITUDE</span>
          <span className="val">{altFeet.toLocaleString()} FT</span>
        </div>
        <div className="avionics-item">
          <span className="lbl">TRUE TRACK</span>
          <span className="val">{heading}° TRUE</span>
        </div>
        <div className="avionics-item live-indicator">
          <span className="pulse-dot" />
          <span className="val green">LIVE PILOT POV</span>
        </div>
      </div>
    </div>
  );
};
