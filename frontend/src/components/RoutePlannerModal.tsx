import React, { useState, useEffect } from 'react';
import {
  HubLocation,
  ConflictZone,
  RoutePlanRequest,
  RoutePlanResponse,
  fetchRoutingHubs,
  fetchConflictZones,
  planStrategicRoute,
} from '../api';
import {
  Navigation,
  X,
  Plane,
  Ship,
  Globe2,
  ShieldAlert,
  ShieldCheck,
  ArrowRight,
  ArrowLeftRight,
  Clock,
  Gauge,
  Fuel,
  TrendingUp,
  MapPin,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Zap,
} from 'lucide-react';

interface RoutePlannerModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeRoute: RoutePlanResponse | null;
  onSelectRoute: (route: RoutePlanResponse | null) => void;
  onFlyToRoute?: (coords: [number, number], zoom?: number) => void;
}

export const RoutePlannerModal: React.FC<RoutePlannerModalProps> = ({
  isOpen,
  onClose,
  activeRoute,
  onSelectRoute,
  onFlyToRoute,
}) => {
  const [hubs, setHubs] = useState<{ airports: HubLocation[]; seaports: HubLocation[] }>({
    airports: [],
    seaports: [],
  });
  const [conflictZones, setConflictZones] = useState<ConflictZone[]>([]);
  const [mode, setMode] = useState<'air' | 'sea' | 'multimodal'>('air');
  const [originId, setOriginId] = useState<string>('LHR');
  const [destinationId, setDestinationId] = useState<string>('HND');
  const [avoidConflicts, setAvoidConflicts] = useState<boolean>(true);
  const [speedKts, setSpeedKts] = useState<number>(480);
  const [isComputing, setIsComputing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load hubs and conflict zones on mount
  useEffect(() => {
    fetchRoutingHubs()
      .then((data) => {
        setHubs(data);
      })
      .catch((err) => console.error('Failed to load routing hubs:', err));

    fetchConflictZones()
      .then((data) => setConflictZones(data))
      .catch((err) => console.error('Failed to load conflict zones:', err));
  }, []);

  // Update default hubs when switching modes
  const handleModeChange = (newMode: 'air' | 'sea' | 'multimodal') => {
    setMode(newMode);
    if (newMode === 'sea') {
      setOriginId('ROTTERDAM');
      setDestinationId('SINGAPORE-PORT');
      setSpeedKts(18);
    } else {
      setOriginId('LHR');
      setDestinationId('HND');
      setSpeedKts(480);
    }
  };

  const handleSwap = () => {
    const temp = originId;
    setOriginId(destinationId);
    setDestinationId(temp);
  };

  const handleComputeRoute = async () => {
    setIsComputing(true);
    setErrorMsg(null);
    try {
      const plan = await planStrategicRoute({
        origin_id: originId,
        destination_id: destinationId,
        mode,
        avoid_conflict_zones: avoidConflicts,
        cruise_speed_kts: speedKts,
      });
      onSelectRoute(plan);
      if (onFlyToRoute && plan.origin) {
        onFlyToRoute([plan.origin.latitude, plan.origin.longitude], 4);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to compute route');
    } finally {
      setIsComputing(false);
    }
  };

  // Quick preset loader
  const applyPreset = (presetMode: 'air' | 'sea', orig: string, dest: string, avoid: boolean) => {
    setMode(presetMode);
    setOriginId(orig);
    setDestinationId(dest);
    setAvoidConflicts(avoid);
    setSpeedKts(presetMode === 'air' ? 480 : 18);
  };

  if (!isOpen) return null;

  const currentHubList = mode === 'sea' ? hubs.seaports : hubs.airports;

  return (
    <div className="route-planner-overlay">
      <div className="route-planner-modal">
        {/* Modal Header */}
        <div className="route-planner-header">
          <div className="route-planner-title">
            <Navigation size={16} color="var(--cy)" />
            <span>STRATEGIC MULTI-MODAL ROUTE PLANNER</span>
            <span className="route-planner-badge">PHASE 1</span>
          </div>
          <button
            className="route-planner-close"
            onClick={onClose}
            aria-label="Close route planner"
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="route-planner-body">
          {/* Mode Selector */}
          <div className="route-mode-selector">
            <button
              className={`route-mode-btn ${mode === 'air' ? 'active' : ''}`}
              onClick={() => handleModeChange('air')}
            >
              <Plane size={13} />
              <span>GREAT-CIRCLE AIR</span>
            </button>
            <button
              className={`route-mode-btn ${mode === 'sea' ? 'active' : ''}`}
              onClick={() => handleModeChange('sea')}
            >
              <Ship size={13} />
              <span>MARITIME SEA-LANES</span>
            </button>
            <button
              className={`route-mode-btn ${mode === 'multimodal' ? 'active' : ''}`}
              onClick={() => handleModeChange('multimodal')}
            >
              <Globe2 size={13} />
              <span>INTERMODAL TRANSIT</span>
            </button>
          </div>

          {/* Quick Presets Bar */}
          <div className="route-presets-row">
            <span className="route-presets-label">TACTICAL PRESETS:</span>
            <button
              className="route-preset-chip"
              onClick={() => applyPreset('air', 'LHR', 'HND', true)}
            >
              ✈ LHR ➔ HND (London-Tokyo Caucasus Detour)
            </button>
            <button
              className="route-preset-chip"
              onClick={() => applyPreset('sea', 'ROTTERDAM', 'SINGAPORE-PORT', true)}
            >
              ⚓ Rotterdam ➔ Singapore (Cape of Good Hope Bypass)
            </button>
            <button
              className="route-preset-chip"
              onClick={() => applyPreset('air', 'JFK', 'DXB', true)}
            >
              ✈ JFK ➔ DXB (New York to Dubai)
            </button>
            <button
              className="route-preset-chip"
              onClick={() => applyPreset('sea', 'SHANGHAI-PORT', 'LA-PORT', false)}
            >
              ⚓ Shanghai ➔ Los Angeles (Transpacific)
            </button>
          </div>

          {/* Hub Selector Inputs */}
          <div className="route-hub-selectors">
            <div className="route-hub-col">
              <label className="route-hub-label">
                <MapPin size={11} color="var(--cy)" /> ORIGIN ({mode.toUpperCase()})
              </label>
              <select
                className="route-hub-select"
                value={originId}
                onChange={(e) => setOriginId(e.target.value)}
              >
                {currentHubList.map((h) => (
                  <option key={h.id} value={h.id}>
                    [{h.code}] {h.city} — {h.name} ({h.country})
                  </option>
                ))}
              </select>
            </div>

            <div className="route-swap-wrapper">
              <button
                className="route-swap-btn"
                onClick={handleSwap}
                title="Swap Origin and Destination"
              >
                <ArrowLeftRight size={14} />
              </button>
            </div>

            <div className="route-hub-col">
              <label className="route-hub-label">
                <MapPin size={11} color="var(--grn)" /> DESTINATION ({mode.toUpperCase()})
              </label>
              <select
                className="route-hub-select"
                value={destinationId}
                onChange={(e) => setDestinationId(e.target.value)}
              >
                {currentHubList.map((h) => (
                  <option key={h.id} value={h.id}>
                    [{h.code}] {h.city} — {h.name} ({h.country})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Strategic Constraints & Options */}
          <div className="route-options-panel">
            <label className="route-checkbox-label">
              <input
                type="checkbox"
                checked={avoidConflicts}
                onChange={(e) => setAvoidConflicts(e.target.checked)}
              />
              <span className="route-checkbox-custom" />
              <div className="route-checkbox-text">
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  Avoid Geopolitical Conflict Zones & Closed Airspace
                </span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  Reroutes around Ukraine/Black Sea closure NOTAMs and Red Sea Houthi anti-ship missile threat corridor.
                </span>
              </div>
            </label>

            <div className="route-speed-slider">
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-secondary)' }}>
                <span><Gauge size={11} /> CRUISE SPEED</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--cy)' }}>
                  {speedKts} KNOTS ({Math.round(speedKts * 1.852)} KM/H)
                </span>
              </div>
              <input
                type="range"
                min={mode === 'sea' ? 10 : 250}
                max={mode === 'sea' ? 30 : 600}
                value={speedKts}
                onChange={(e) => setSpeedKts(Number(e.target.value))}
                className="route-slider-input"
              />
            </div>
          </div>

          {/* Compute Action Button */}
          <button
            className="route-compute-btn"
            onClick={handleComputeRoute}
            disabled={isComputing}
          >
            {isComputing ? (
              <span>SOLVING GEODESIC TRANSIT EQUATIONS...</span>
            ) : (
              <>
                <TrendingUp size={14} />
                <span>COMPUTE STRATEGIC ROUTE & EMISSIONS</span>
              </>
            )}
          </button>

          {errorMsg && (
            <div className="route-error-banner">
              <AlertTriangle size={14} />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Active Route Telemetry Dossier */}
          {activeRoute && (
            <div className="route-results-card">
              <div className="route-results-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={14} color="var(--grn)" />
                  <span style={{ fontWeight: 700, fontSize: '12px', letterSpacing: '0.06em' }}>
                    TACTICAL ROUTE: {activeRoute.origin.code} ➔ {activeRoute.destination.code}
                  </span>
                </div>
                <span
                  className={`route-threat-badge ${
                    activeRoute.threat_level === 'CRITICAL'
                      ? 'critical'
                      : activeRoute.threat_level === 'HIGH' || activeRoute.threat_level === 'ELEVATED'
                      ? 'warning'
                      : 'safe'
                  }`}
                >
                  {activeRoute.threat_level === 'LOW' ? (
                    <ShieldCheck size={11} />
                  ) : (
                    <ShieldAlert size={11} />
                  )}
                  {activeRoute.threat_level} THREAT
                </span>
              </div>

              {/* Metrics Grid */}
              <div className="route-metrics-grid">
                <div className="route-metric-box">
                  <span className="route-metric-label">TOTAL DISTANCE</span>
                  <span className="route-metric-val">
                    {Math.round(activeRoute.total_distance_nm).toLocaleString()} <small>NM</small>
                  </span>
                  <span className="route-metric-sub">
                    ({Math.round(activeRoute.total_distance_km).toLocaleString()} km)
                  </span>
                </div>

                <div className="route-metric-box">
                  <span className="route-metric-label">EST. DURATION</span>
                  <span className="route-metric-val" style={{ color: 'var(--grn)' }}>
                    {activeRoute.estimated_duration_formatted}
                  </span>
                  <span className="route-metric-sub">
                    at {speedKts} kts
                  </span>
                </div>

                <div className="route-metric-box">
                  <span className="route-metric-label">FUEL CONSUMPTION</span>
                  <span className="route-metric-val" style={{ color: 'var(--amber)' }}>
                    {activeRoute.fuel_estimate_tons} <small>TONS</small>
                  </span>
                  <span className="route-metric-sub">
                    {mode === 'air' ? 'Jet-A1' : 'HFO'}
                  </span>
                </div>

                <div className="route-metric-box">
                  <span className="route-metric-label">CO₂ EQUIVALENT</span>
                  <span className="route-metric-val" style={{ color: 'var(--text-secondary)' }}>
                    {activeRoute.co2_estimate_tons} <small>TONS</small>
                  </span>
                  <span className="route-metric-sub">
                    Scope 1 Emissions
                  </span>
                </div>
              </div>

              {/* Conflict Avoidance Notice */}
              {activeRoute.conflict_zones_avoided.length > 0 && (
                <div className="route-avoidance-notice">
                  <ShieldCheck size={13} color="var(--grn)" />
                  <span>
                    <strong>Tactical Reroute Verified:</strong> Dynamically routed around{' '}
                    {activeRoute.conflict_zones_avoided.join(', ')}.
                  </span>
                </div>
              )}

              {/* Narrative Summary */}
              <p className="route-summary-text">{activeRoute.summary}</p>

              {/* Altitude / Profile Mini-Preview */}
              {mode === 'air' && activeRoute.altitude_profile.length > 0 && (
                <div className="route-altitude-viz">
                  <div className="route-alt-header">
                    <span>CRUISE ALTITUDE PROFILE (FL360 / 11,000M)</span>
                  </div>
                  <div className="route-alt-bars">
                    {activeRoute.altitude_profile.map((p, idx) => {
                      const hPct = Math.round((p.alt_m / 11000) * 100);
                      return (
                        <div
                          key={idx}
                          className="route-alt-bar"
                          style={{ height: `${Math.max(4, hPct)}%` }}
                          title={`${Math.round(p.dist_km)} km: ${Math.round(p.alt_m)}m altitude`}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="route-actions-row">
                {onFlyToRoute && (
                  <button
                    className="route-action-btn primary"
                    onClick={() => {
                      onFlyToRoute([activeRoute.origin.latitude, activeRoute.origin.longitude], 4);
                      onClose();
                    }}
                  >
                    <Globe2 size={13} />
                    <span>VIEW ON GLOBE</span>
                  </button>
                )}
                <button
                  className="route-action-btn secondary"
                  onClick={() => onSelectRoute(null)}
                >
                  <X size={13} />
                  <span>CLEAR ROUTE</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
