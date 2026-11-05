import React from 'react';
import {
  CornerUpRight,
  CornerUpLeft,
  ArrowUp,
  GitMerge,
  RotateCw,
  CheckCircle2,
  Compass,
  Radio,
  Play,
  Pause,
  FastForward,
  Clock,
  MapPin,
  Eye,
  Crosshair,
  X,
  Navigation as NavIcon,
} from 'lucide-react';
import { RoadRouteResponse, UserNavigationState } from '../api';

interface LiveNavigationHUDProps {
  userNavState: UserNavigationState;
  activeRoadRoute: RoadRouteResponse;
  onExitNavigation: () => void;
  onToggleCameraFollow: () => void;
  onToggleSimulate: (simulate: boolean) => void;
  onChangeSimSpeed: (speed: number) => void;
  onRecenter: () => void;
}

export const LiveNavigationHUD: React.FC<LiveNavigationHUDProps> = ({
  userNavState,
  activeRoadRoute,
  onExitNavigation,
  onToggleCameraFollow,
  onToggleSimulate,
  onChangeSimSpeed,
  onRecenter,
}) => {
  const steps = activeRoadRoute.steps || [];
  const currentStep = steps[userNavState.currentStepIndex] || steps[0];
  const nextStep = steps[userNavState.currentStepIndex + 1];

  const formatDistance = (distM: number) => {
    if (distM >= 1000) {
      return `${(distM / 1000).toFixed(1)} km`;
    }
    return `${Math.round(distM)} m`;
  };

  const formatDuration = (sec: number) => {
    const mins = Math.round(sec / 60);
    if (mins >= 60) {
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      return `${h} hr ${m} min`;
    }
    return `${Math.max(1, mins)} min`;
  };

  // Calculate clock arrival time (e.g. 5:45 PM)
  const arrivalDate = new Date(Date.now() + userNavState.remainingDuration_s * 1000);
  const arrivalTimeFormatted = arrivalDate.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });

  const getManeuverIcon = (type: string, size = 32) => {
    switch (type) {
      case 'turn_right':
      case 'sharp_right':
        return <CornerUpRight size={size} className="text-amber-400" />;
      case 'turn_left':
      case 'sharp_left':
        return <CornerUpLeft size={size} className="text-amber-400" />;
      case 'continue':
        return <ArrowUp size={size} className="text-emerald-400" />;
      case 'merge':
      case 'ramp':
        return <GitMerge size={size} className="text-sky-400" />;
      case 'roundabout':
        return <RotateCw size={size} className="text-purple-400" />;
      case 'arrive':
        return <CheckCircle2 size={size} className="text-emerald-400" />;
      case 'depart':
      default:
        return <Compass size={size} className="text-cyan-400" />;
    }
  };

  return (
    <div className="live-nav-hud-root">
      {/* 1. TOP MANEUVER BANNER (Google Maps Style) */}
      <div className="nav-hud-top-card">
        {userNavState.hasArrived ? (
          <div className="nav-hud-arrived-banner">
            <div className="arrived-icon-circle">
              <CheckCircle2 size={36} className="text-emerald-400" />
            </div>
            <div className="arrived-text-group">
              <h3 className="arrived-title">YOU HAVE ARRIVED!</h3>
              <p className="arrived-dest-name">{activeRoadRoute.destination_name}</p>
              <span className="arrived-summary">
                Completed {activeRoadRoute.total_distance_formatted} route safely.
              </span>
            </div>
          </div>
        ) : (
          <div className="nav-hud-maneuver-content">
            {/* Big Turn Icon */}
            <div className="nav-hud-icon-box">
              {getManeuverIcon(currentStep?.maneuver_type || 'continue', 34)}
            </div>

            {/* Instruction and Distance Countdown */}
            <div className="nav-hud-text-block">
              <div className="nav-hud-countdown-row">
                <span className="countdown-prefix">In</span>
                <span className="countdown-distance">
                  {formatDistance(userNavState.distanceToNextStep_m)}
                </span>
              </div>
              <div className="nav-hud-street-name" title={currentStep?.instruction}>
                {currentStep?.instruction || 'Continue straight along the road'}
              </div>
            </div>

            {/* Subsequent Maneuver Preview */}
            {nextStep && (
              <div className="nav-hud-next-step-preview">
                <span className="next-label">THEN</span>
                <div className="next-icon-badge">
                  {getManeuverIcon(nextStep.maneuver_type, 18)}
                </div>
                <span className="next-dist">{formatDistance(nextStep.distance_m)}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. RECENTER PROMPT (If User Panned Camera Away) */}
      {!userNavState.isCameraFollowing && !userNavState.hasArrived && (
        <button
          className="nav-hud-recenter-btn"
          onClick={onRecenter}
          title="Recenter 3D camera to user vehicle"
        >
          <Crosshair size={18} className="animate-spin text-cyan-400" />
          <span>RECENTER 3D CAMERA</span>
        </button>
      )}

      {/* 3. BOTTOM TELEMETRY & CONTROLS BAR (Google Maps Style) */}
      <div className="nav-hud-bottom-bar">
        {/* Left: ETA, Remaining Distance & Clock */}
        <div className="nav-hud-eta-group">
          <div className="eta-main-time text-emerald-400">
            {formatDuration(userNavState.remainingDuration_s)}
          </div>
          <div className="eta-sub-row">
            <span className="eta-sub-distance">
              {formatDistance(userNavState.remainingDistance_m)}
            </span>
            <span className="eta-dot">•</span>
            <span className="eta-sub-clock">ETA {arrivalTimeFormatted}</span>
          </div>
        </div>

        {/* Center: Live Speedometer */}
        <div className="nav-hud-speedometer-box">
          <span className="speed-val">{userNavState.speed_kmh}</span>
          <span className="speed-unit">KM/H</span>
        </div>

        {/* Right: Mode & Camera Controls */}
        <div className="nav-hud-controls-group">
          {/* Tracking Mode Toggle (Simulate vs GPS) */}
          <div className="nav-mode-pill-group">
            <button
              className={`nav-mode-btn ${userNavState.isSimulating ? 'active' : ''}`}
              onClick={() => onToggleSimulate(true)}
              title="Simulate driving along polyline"
            >
              <Play size={13} />
              <span>Simulate</span>
            </button>
            <button
              className={`nav-mode-btn ${!userNavState.isSimulating ? 'active' : ''}`}
              onClick={() => onToggleSimulate(false)}
              title="Track real-time device GPS"
            >
              <Radio size={13} className={!userNavState.isSimulating ? 'animate-pulse' : ''} />
              <span>Live GPS</span>
            </button>
          </div>

          {/* Simulation Speed Selector (if simulating) */}
          {userNavState.isSimulating && !userNavState.hasArrived && (
            <div className="nav-speed-pills">
              {[1, 2, 4, 8].map((s) => (
                <button
                  key={s}
                  className={`speed-pill ${userNavState.simulationSpeed === s ? 'active' : ''}`}
                  onClick={() => onChangeSimSpeed(s)}
                  title={`${s}x Simulation Speed`}
                >
                  {s}x
                </button>
              ))}
            </div>
          )}

          {/* 3D Driver Follow Camera Toggle */}
          <button
            className={`nav-cam-toggle-btn ${userNavState.isCameraFollowing ? 'active' : ''}`}
            onClick={onToggleCameraFollow}
            title={
              userNavState.isCameraFollowing
                ? 'Camera is following driver 3D view (Click to unlock)'
                : 'Camera is unlocked (Click to lock 3D follow)'
            }
          >
            <Eye size={15} />
            <span>{userNavState.isCameraFollowing ? '3D Driver' : 'Free Cam'}</span>
          </button>

          {/* Exit Navigation */}
          <button
            className="nav-exit-btn"
            onClick={onExitNavigation}
            title="Exit Live Navigation Mode"
          >
            <X size={16} />
            <span>Exit</span>
          </button>
        </div>
      </div>
    </div>
  );
};
