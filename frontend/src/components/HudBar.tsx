import React, { useEffect, useState, useRef } from 'react';
import { BoundingBox, CameraEntity } from '../api';
import { BasemapMode } from '../types/layers';
import {
  Search,
  Activity,
  Layers,
  Globe,
  Compass,
  Satellite,
  Waves,
  ChevronDown,
  Plane,
  Ship,
  Flame,
  Building2,
  Video,
  MapPin,
  Navigation,
  Mic,
  Map,
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
  const [isBasemapMenuOpen, setIsBasemapMenuOpen] = useState(false);
  const [isToolsMenuOpen, setIsToolsMenuOpen] = useState(false);

  const cameraMenuRef = useRef<HTMLDivElement>(null);
  const basemapMenuRef = useRef<HTMLDivElement>(null);
  const toolsMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setUtcTime(now.toISOString().slice(11, 19) + ' UTC');
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (cameraMenuRef.current && !cameraMenuRef.current.contains(target)) {
        setIsCameraMenuOpen(false);
      }
      if (basemapMenuRef.current && !basemapMenuRef.current.contains(target)) {
        setIsBasemapMenuOpen(false);
      }
      if (toolsMenuRef.current && !toolsMenuRef.current.contains(target)) {
        setIsToolsMenuOpen(false);
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

  const getBasemapLabel = () => {
    switch (basemapMode) {
      case 'streets':
        return 'STREETS';
      case 'google-3d':
        return 'GOOGLE 3D';
      case 'dark-tactical':
        return 'TACTICAL';
      case 'oceanic':
        return 'OCEANIC';
      case 'satellite-hybrid':
      default:
        return 'SATELLITE';
    }
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
        {/* 3D Geospatial Globe Badge */}
        <div className="mode-switcher" role="group" aria-label="Geospatial Projection Mode">
          <div className="mode-btn active" style={{ cursor: 'default', pointerEvents: 'none' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <Globe size={12} /> 3D GLOBE
            </span>
          </div>
        </div>

        {/* Basemap Selection Dropdown */}
        <div className="hud-dropdown-wrapper" ref={basemapMenuRef}>
          <button
            className={`hud-dropdown-trigger-btn ${isBasemapMenuOpen ? 'active' : ''}`}
            onClick={() => setIsBasemapMenuOpen((prev) => !prev)}
            title="Switch Cartographic Basemap & 3D Tiles"
            aria-expanded={isBasemapMenuOpen}
          >
            {basemapMode === 'satellite-hybrid' && <Satellite size={12} color="var(--cy)" />}
            {basemapMode === 'streets' && <Map size={12} color="#10b981" />}
            {basemapMode === 'google-3d' && <Building2 size={12} color="#eab308" />}
            {basemapMode === 'dark-tactical' && <Compass size={12} color="var(--cy)" />}
            {basemapMode === 'oceanic' && <Waves size={12} color="#38bdf8" />}
            <span>{getBasemapLabel()}</span>
            <ChevronDown size={11} />
          </button>

          {isBasemapMenuOpen && (
            <div className="hud-custom-dropdown-menu">
              <div className="hud-dropdown-menu-header">CARTOGRAPHIC BASEMAP</div>
              <button
                className={`hud-dropdown-menu-item ${basemapMode === 'satellite-hybrid' ? 'active' : ''}`}
                onClick={() => {
                  onSetBasemapMode('satellite-hybrid');
                  setIsBasemapMenuOpen(false);
                }}
              >
                <Satellite size={13} color="var(--cy)" />
                <div className="hud-dropdown-item-desc">
                  <strong>Satellite Hybrid (Esri 4K)</strong>
                  <span>Photorealistic orbital imagery with street network overlay</span>
                </div>
              </button>

              <button
                className={`hud-dropdown-menu-item ${basemapMode === 'streets' ? 'active' : ''}`}
                onClick={() => {
                  onSetBasemapMode('streets');
                  setIsBasemapMenuOpen(false);
                }}
              >
                <Map size={13} color="#10b981" />
                <div className="hud-dropdown-item-desc">
                  <strong>Streets &amp; Places Navigation</strong>
                  <span>Detailed road network, street names, POIs, motels &amp; dining</span>
                </div>
              </button>

              <button
                className={`hud-dropdown-menu-item ${basemapMode === 'google-3d' ? 'active' : ''}`}
                onClick={() => {
                  onSetBasemapMode('google-3d');
                  setIsBasemapMenuOpen(false);
                }}
              >
                <Building2 size={13} color="#eab308" />
                <div className="hud-dropdown-item-desc">
                  <strong>Google Photorealistic 3D</strong>
                  <span>3D buildings, urban meshes, and textured terrain</span>
                </div>
              </button>

              <button
                className={`hud-dropdown-menu-item ${basemapMode === 'dark-tactical' ? 'active' : ''}`}
                onClick={() => {
                  onSetBasemapMode('dark-tactical');
                  setIsBasemapMenuOpen(false);
                }}
              >
                <Compass size={13} color="var(--cy)" />
                <div className="hud-dropdown-item-desc">
                  <strong>Dark Tactical Vector</strong>
                  <span>Operational high-contrast dark vector basemap</span>
                </div>
              </button>

              <button
                className={`hud-dropdown-menu-item ${basemapMode === 'oceanic' ? 'active' : ''}`}
                onClick={() => {
                  onSetBasemapMode('oceanic');
                  setIsBasemapMenuOpen(false);
                }}
              >
                <Waves size={13} color="#38bdf8" />
                <div className="hud-dropdown-item-desc">
                  <strong>Oceanic Bathymetry</strong>
                  <span>Marine seabed topography, trenches, and seafloor contours</span>
                </div>
              </button>
            </div>
          )}
        </div>

        {/* Street Cameras Quick-Jump Selector Dropdown */}
        <div className="street-cam-selector-wrapper" ref={cameraMenuRef}>
          <button
            className={`street-cam-trigger-btn ${isCameraMenuOpen ? 'active' : ''}`}
            onClick={() => setIsCameraMenuOpen((prev) => !prev)}
            title="Browse & Jump to Global Street Cameras"
            aria-expanded={isCameraMenuOpen}
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
        {/* Stays & Places Discovery Deck Button */}
        <button
          className={`hud-btn ${isPlacesDeckOpen ? 'active' : ''}`}
          onClick={onTogglePlacesDeck}
          title="Discover stays, fine dining, scenery, and nightlife via Google Places"
          aria-expanded={isPlacesDeckOpen}
        >
          <Building2 size={13} color="#eab308" />
          <span>STAYS & PLACES</span>
        </button>

        {/* AI Mission Assistant Roger Button */}
        <button
          className={`hud-btn ${isAssistantOpen ? 'active' : ''}`}
          onClick={onOpenAssistant}
          title="Talk to Roger, your WORLDOS mission control copilot"
          aria-expanded={isAssistantOpen}
        >
          <Mic size={13} color="var(--cy)" />
          <span>ASSISTANT</span>
        </button>

        {/* Operations & Tactical Tools Dropdown */}
        <div className="hud-dropdown-wrapper" ref={toolsMenuRef}>
          <button
            className={`hud-btn ${isToolsMenuOpen || isRouteActive ? 'active' : ''}`}
            onClick={() => setIsToolsMenuOpen((prev) => !prev)}
            title="Operations & Tactical Tools Menu"
            style={isRouteActive ? { borderColor: 'var(--cy)', background: 'rgba(6, 182, 212, 0.2)' } : {}}
            aria-expanded={isToolsMenuOpen}
          >
            <Navigation size={13} color="var(--cy)" />
            <span>OPS TOOLS</span>
            <ChevronDown size={11} />
          </button>

          {isToolsMenuOpen && (
            <div className="hud-custom-dropdown-menu align-right">
              <div className="hud-dropdown-menu-header">MISSION OPERATIONS &amp; TOOLS</div>
              <button
                className="hud-dropdown-menu-item"
                onClick={() => {
                  if (onOpenRoutePlanner) onOpenRoutePlanner();
                  setIsToolsMenuOpen(false);
                }}
              >
                <Navigation size={13} color="var(--cy)" />
                <div className="hud-dropdown-item-desc">
                  <strong>Strategic Route Planner</strong>
                  <span>Multi-modal geodesic routing &amp; conflict zone avoidance</span>
                </div>
              </button>

              <button
                className="hud-dropdown-menu-item"
                onClick={() => {
                  onOpenCommandPalette();
                  setIsToolsMenuOpen(false);
                }}
              >
                <Search size={13} />
                <div className="hud-dropdown-item-desc">
                  <strong>Tactical Command Palette</strong>
                  <span>Search entities, airports, and hotkeys (Ctrl+K)</span>
                </div>
              </button>

              <button
                className="hud-dropdown-menu-item"
                onClick={() => {
                  onOpenSourceHealth();
                  setIsToolsMenuOpen(false);
                }}
              >
                <Activity size={13} color="var(--grn)" />
                <div className="hud-dropdown-item-desc">
                  <strong>Live Ingestion Telemetry</strong>
                  <span>Inspect ADS-B, AIS, Celestrak, and FIRMS adapter health</span>
                </div>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
