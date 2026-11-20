import React, { useEffect, useState } from 'react';
import { AircraftState } from '../api';
import { EyeOff, Compass, Gauge, ArrowUpRight, Plane } from 'lucide-react';

interface CockpitHUDProps {
  aircraft: AircraftState;
  onExitCockpit: () => void;
}

export const CockpitHUD: React.FC<CockpitHUDProps> = ({ aircraft, onExitCockpit }) => {
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
        {/* Pitch Ladders */}
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

        <button
          className="cockpit-exit-btn"
          onClick={onExitCockpit}
          title="Exit Cockpit View (Return to Orbital Overview)"
        >
          <EyeOff size={14} />
          <span>EXIT COCKPIT [ESC]</span>
        </button>
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
