import React, { useEffect, useState } from 'react';
import { BoundingBox } from '../api';
import { BasemapMode } from '../types/layers';
import {
  Search,
  Activity,
  Layers,
  Globe,
  Map,
  Compass,
  Satellite,
  Waves,
  Eye,
} from 'lucide-react';

interface HudBarProps {
  viewMode: '2d' | '3d';
  onToggleViewMode: (mode: '2d' | '3d') => void;
  basemapMode: BasemapMode;
  onSetBasemapMode: (mode: BasemapMode) => void;
  viewportBbox: BoundingBox | null;
  isLoading: boolean;
  onOpenCommandPalette: () => void;
  onOpenSourceHealth: () => void;
  isDockCollapsed: boolean;
  onToggleDock: () => void;
  aircraftCount: number;
  vesselCount: number;
  satelliteCount: number;
  cameraCount: number;
  fireCount: number;
  infraCount: number;
}

export const HudBar: React.FC<HudBarProps> = ({
  viewMode,
  onToggleViewMode,
  basemapMode,
  onSetBasemapMode,
  viewportBbox,
  isLoading,
  onOpenCommandPalette,
  onOpenSourceHealth,
  isDockCollapsed,
  onToggleDock,
  aircraftCount,
  vesselCount,
  satelliteCount,
  cameraCount,
  fireCount,
  infraCount,
}) => {
  const [utcTime, setUtcTime] = useState<string>('');

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setUtcTime(now.toISOString().slice(11, 19) + ' UTC');
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatCoord = (val: number | undefined) => {
    if (val === undefined || isNaN(val)) return '0.00';
    return val >= 0 ? `+${val.toFixed(2)}` : val.toFixed(2);
  };

  return (
    <header className="hud-topbar">
      <div className="hud-brand">
        <button
          className="hud-btn"
          style={{ padding: '6px 8px' }}
          onClick={onToggleDock}
          title={isDockCollapsed ? 'Expand Layer Dock' : 'Collapse Layer Dock'}
          aria-label="Toggle Layer Dock"
        >
          <Layers size={14} color="var(--cy)" />
        </button>
        <div className="hud-brand-title">
          <span>WORLDOS</span>
          <span className="hud-brand-tag">GLOBAL INTEL</span>
        </div>
      </div>

      <div className="hud-center-group">
        {/* 2D / 3D Projection Switcher */}
        <div className="mode-switcher" role="group" aria-label="Geospatial Projection Mode">
          <button
            className={`mode-btn ${viewMode === '2d' ? 'active' : ''}`}
            onClick={() => onToggleViewMode('2d')}
            aria-pressed={viewMode === '2d'}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Map size={12} /> 2D FLAT
            </span>
          </button>
          <button
            className={`mode-btn ${viewMode === '3d' ? 'active' : ''}`}
            onClick={() => onToggleViewMode('3d')}
            aria-pressed={viewMode === '3d'}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Globe size={12} /> 3D GLOBE
            </span>
          </button>
        </div>

        {/* Basemap Selection Group */}
        <div
          className="mode-switcher"
          role="group"
          aria-label="Cartographic Basemap"
          style={{ marginLeft: '6px' }}
        >
          <button
            className={`mode-btn ${basemapMode === 'dark-tactical' ? 'active' : ''}`}
            onClick={() => onSetBasemapMode('dark-tactical')}
            title="Dark Tactical Vector Canvas"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Compass size={11} /> TACTICAL
            </span>
          </button>
          <button
            className={`mode-btn ${basemapMode === 'satellite-hybrid' ? 'active' : ''}`}
            onClick={() => onSetBasemapMode('satellite-hybrid')}
            title="Satellite Imagery with Sovereign Boundaries"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Satellite size={11} /> SATELLITE
            </span>
          </button>
          <button
            className={`mode-btn ${basemapMode === 'oceanic' ? 'active' : ''}`}
            onClick={() => onSetBasemapMode('oceanic')}
            title="Oceanic Bathymetry and Marine Topography"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Waves size={11} /> OCEANIC
            </span>
          </button>
        </div>

        {/* Live Multi-Domain Telemetry Summary Pills */}
        <div className="hud-telemetry" style={{ display: 'flex', gap: '8px' }}>
          <div className="telemetry-item" title="Active ADS-B Aircraft Transponders">
            <span className="telemetry-label" style={{ color: '#38bdf8' }}>
              ADS-B:
            </span>
            <span className="telemetry-val">{aircraftCount.toLocaleString()}</span>
          </div>
          <div className="telemetry-item" title="AIS Maritime Vessels in Global Sea Corridors">
            <span className="telemetry-label" style={{ color: '#06b6d4' }}>
              AIS:
            </span>
            <span className="telemetry-val">{vesselCount}</span>
          </div>
          <div className="telemetry-item" title="Active Orbital Assets & Ground Tracks">
            <span className="telemetry-label" style={{ color: '#a855f7' }}>
              ORBIT:
            </span>
            <span className="telemetry-val">{satelliteCount}</span>
          </div>
          <div className="telemetry-item" title="Live Optical CCTV & Sensor Feeds">
            <span className="telemetry-label" style={{ color: '#10b981' }}>
              CCTV:
            </span>
            <span className="telemetry-val">{cameraCount}</span>
          </div>
          <div className="telemetry-item" title="NASA FIRMS Thermal Fire Anomalies">
            <span className="telemetry-label" style={{ color: '#ef4444' }}>
              FIRMS:
            </span>
            <span className="telemetry-val">{fireCount}</span>
          </div>
          <div className="telemetry-item" title="Airports, Deep-Water Ports & Spaceports">
            <span className="telemetry-label" style={{ color: '#eab308' }}>
              INFRA:
            </span>
            <span className="telemetry-val">{infraCount}</span>
          </div>

          <div className="telemetry-item">
            <span className="telemetry-label">TIME:</span>
            <span className="telemetry-val">{utcTime}</span>
          </div>
        </div>
      </div>

      <div className="hud-actions">
        <button
          className="hud-btn"
          onClick={onOpenCommandPalette}
          title="Open Tactical Command Palette (Ctrl+K)"
        >
          <Search size={13} />
          <span>COMMANDS</span>
          <kbd>Ctrl+K</kbd>
        </button>

        <button
          className="hud-btn"
          onClick={onOpenSourceHealth}
          title="Inspect Registered Source Adapters & Telemetry"
        >
          <Activity size={13} />
          <span>FEEDS</span>
        </button>
      </div>
    </header>
  );
};
