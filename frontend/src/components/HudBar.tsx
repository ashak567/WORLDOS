import React, { useEffect, useState, useRef } from 'react';
import { BoundingBox, CameraEntity } from '../api';
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
  Camera,
  ChevronDown,
  Plane,
  Ship,
  Flame,
  Building2,
  Video,
  MapPin,
  Navigation,
  Mic,
} from 'lucide-react';

interface HudBarProps {
  viewMode?: '2d' | '3d';
  onToggleViewMode?: (mode: '2d' | '3d') => void;
  basemapMode: BasemapMode;
  onSetBasemapMode: (mode: BasemapMode) => void;
  viewportBbox: BoundingBox | null;
  isLoading: boolean;
  onOpenCommandPalette: () => void;
  onOpenSourceHealth: () => void;
  onOpenRoutePlanner?: () => void;
  onOpenAssistant: () => void;
  isAssistantOpen: boolean;
  onTogglePlacesDeck?: () => void;
  isPlacesDeckOpen?: boolean;
  isRouteActive?: boolean;
  isDockCollapsed: boolean;
  onToggleDock: () => void;
  aircraftCount: number;
  vesselCount: number;
  satelliteCount: number;
  cameraCount: number;
  fireCount: number;
  infraCount: number;
  cameras?: CameraEntity[];
  onJumpToCamera?: (camera: CameraEntity) => void;
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
  onOpenRoutePlanner,
  onOpenAssistant,
  isAssistantOpen,
  onTogglePlacesDeck,
  isPlacesDeckOpen,
  isRouteActive = false,
  isDockCollapsed,
  onToggleDock,
  aircraftCount,
  vesselCount,
  satelliteCount,
  cameraCount,
  fireCount,
  infraCount,
  cameras = [],
  onJumpToCamera,
}) => {
  const [utcTime, setUtcTime] = useState<string>('');
  const [isCameraMenuOpen, setIsCameraMenuOpen] = useState(false);
  const cameraMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setUtcTime(now.toISOString().slice(11, 19) + ' UTC');
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (cameraMenuRef.current && !cameraMenuRef.current.contains(e.target as Node)) {
        setIsCameraMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Curated iconic street cameras for instant jump
  const featuredCameras = cameras.filter((c) => {
    const cid = c.attributes?.camera_id || '';
    const name = (c.canonical_name || '').toLowerCase();
    return (
      cid.includes('TIMES-SQUARE') ||
      cid.includes('SHIBUYA') ||
      cid.includes('5TH-AVE') ||
      cid.includes('PICCADILLY') ||
      cid.includes('GOLDEN-GATE') ||
      cid.includes('CHAMPS-ELYSEES') ||
      cid.includes('HOLLYWOOD') ||
      cid.includes('WESTMINSTER') ||
      cid.includes('OXFORD') ||
      cid.includes('KILAUEA') ||
      name.includes('times square') ||
      name.includes('shibuya')
    );
  });

  const displayCameras = featuredCameras.length > 0 ? featuredCameras : cameras.slice(0, 8);

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
        {/* 3D Geospatial Globe Badge */}
        <div className="mode-switcher" role="group" aria-label="Geospatial Projection Mode">
          <div className="mode-btn active" style={{ cursor: 'default', pointerEvents: 'none' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Globe size={12} /> 3D GLOBE
            </span>
          </div>
        </div>

        {/* Basemap Selection Group */}
        <div
          className="mode-switcher"
          role="group"
          aria-label="Cartographic Basemap"
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

        {/* Street Cameras Quick-Jump Selector Dropdown */}
        <div className="street-cam-selector-wrapper" ref={cameraMenuRef}>
          <button
            className={`street-cam-trigger-btn ${isCameraMenuOpen ? 'active' : ''}`}
            onClick={() => setIsCameraMenuOpen((prev) => !prev)}
            title="Browse & Jump to Global Street Cameras"
          >
            <Video size={13} color="var(--grn)" />
            <span>STREET CAMS</span>
            <span className="street-cam-badge">{cameraCount}</span>
            <ChevronDown size={11} />
          </button>

          {isCameraMenuOpen && (
            <div className="street-cam-dropdown-menu">
              <div className="street-cam-dropdown-header">
                <Video size={12} color="var(--grn)" />
                <span>LIVE STREET & TRAFFIC CAMERAS</span>
              </div>
              <div className="street-cam-dropdown-list">
                {displayCameras.length === 0 ? (
                  <div className="street-cam-empty">No cameras loaded in database yet</div>
                ) : (
                  displayCameras.map((cam) => {
                    const name = cam.canonical_name || cam.attributes?.camera_id || 'Street Camera';
                    const region = cam.attributes?.region || 'Global';
                    return (
                      <button
                        key={cam.entity_id}
                        className="street-cam-item"
                        onClick={() => {
                          if (onJumpToCamera) onJumpToCamera(cam);
                          setIsCameraMenuOpen(false);
                        }}
                      >
                        <div className="street-cam-item-info">
                          <span className="street-cam-item-name">{name}</span>
                          <span className="street-cam-item-region">
                            <MapPin size={9} /> {region}
                          </span>
                        </div>
                        <span className="street-cam-item-pill">LIVE</span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Live Multi-Domain Telemetry Tactical Badges */}
        <div className="hud-telemetry">
          <div className="telemetry-badge sky" title="Active ADS-B Aircraft Transponders">
            <Plane size={11} />
            <span className="telemetry-val">{aircraftCount.toLocaleString()}</span>
          </div>
          <div className="telemetry-badge cyan" title="AIS Maritime Cargo & Tankers">
            <Ship size={11} />
            <span className="telemetry-val">{vesselCount}</span>
          </div>
          <div className="telemetry-badge neon-red" title="Active Orbital Assets (SGP4 Ephemeris)">
            <Satellite size={11} />
            <span className="telemetry-val">{satelliteCount}</span>
          </div>
          <div className="telemetry-badge red" title="NASA FIRMS Thermal Fire Hotspots">
            <Flame size={11} />
            <span className="telemetry-val">{fireCount}</span>
          </div>
          <div className="telemetry-badge gold" title="Strategic Ports & Spaceports">
            <Building2 size={11} />
            <span className="telemetry-val">{infraCount}</span>
          </div>
          <div className="telemetry-badge time" title="Universal Coordinated Time">
            <span>{utcTime}</span>
          </div>
        </div>
      </div>

      <div className="hud-actions">
        <button
          className={`hud-btn ${isPlacesDeckOpen ? 'active' : ''}`}
          onClick={onTogglePlacesDeck}
          title="Discover stays, fine dining, scenery, and nightlife via Google Places"
          aria-expanded={isPlacesDeckOpen}
        >
          <Building2 size={13} color="#eab308" />
          <span>STAYS & PLACES</span>
        </button>

        <button
          className="hud-btn"
          onClick={onOpenAssistant}
          title="Talk to the local WORLDOS assistant"
          aria-expanded={isAssistantOpen}
        >
          <Mic size={13} color="var(--cy)" />
          <span>ASSISTANT</span>
        </button>

        <button
          className="hud-btn"
          onClick={onOpenRoutePlanner}
          title="Open Strategic Multi-Modal Route Planner"
          style={isRouteActive ? { borderColor: 'var(--cy)', background: 'rgba(6, 182, 212, 0.2)' } : {}}
        >
          <Navigation size={13} color="var(--cy)" />
          <span>ROUTES</span>
        </button>

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
