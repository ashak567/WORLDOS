import React from 'react';
import { CloudRain, AlertTriangle, Droplets, Eye, Activity } from 'lucide-react';
import { LiveRainfallData } from '../api';

interface RainfallHUDProps {
  rainfallData: LiveRainfallData | null;
  isZoomedIn: boolean;
  rainFxEnabled: boolean;
  onToggleRainFx: () => void;
  onDismiss?: () => void;
}

export const RainfallHUD: React.FC<RainfallHUDProps> = ({
  rainfallData,
  isZoomedIn,
  rainFxEnabled,
  onToggleRainFx,
}) => {
  if (!rainfallData) return null;

  const isRaining = rainfallData.precipitation_mm_h > 0;
  const isDanger = rainfallData.danger_level === 'DANGER';
  const isModerate = rainfallData.danger_level === 'MODERATE';

  return (
    <div className={`rainfall-tactical-hud ${isDanger ? 'danger' : isModerate ? 'warning' : ''}`}>
      <div className="rainfall-hud-header">
        <div className="rainfall-hud-title-group">
          <CloudRain size={14} color={rainfallData.danger_color} className={isRaining ? 'pulse-icon' : ''} />
          <span className="rainfall-hud-label">LIVE ATMOSPHERIC PRECIPITATION</span>
        </div>
        <span
          className="rainfall-danger-badge"
          style={{
            backgroundColor: `${rainfallData.danger_color}22`,
            color: rainfallData.danger_color,
            borderColor: `${rainfallData.danger_color}66`,
          }}
        >
          {isDanger && <AlertTriangle size={10} className="mr-1" />}
          {rainfallData.danger_label}
        </span>
      </div>

      <div className="rainfall-hud-body">
        <div className="rainfall-stat-box">
          <span className="stat-label">RAIN RATE</span>
          <div className="stat-value-row">
            <span className="stat-num" style={{ color: rainfallData.danger_color }}>
              {rainfallData.precipitation_mm_h.toFixed(1)}
            </span>
            <span className="stat-unit">mm/h</span>
          </div>
        </div>

        <div className="rainfall-stat-box">
          <span className="stat-label">RAIN PROBABILITY</span>
          <div className="stat-value-row">
            <Droplets size={12} color="var(--cy)" />
            <span className="stat-num text-cyan-400">
              {rainfallData.precipitation_probability}%
            </span>
          </div>
        </div>

        <div className="rainfall-stat-box">
          <span className="stat-label">ATMOSPHERIC CONDITION</span>
          <span className="stat-condition">{rainfallData.condition}</span>
        </div>
      </div>

      <div className="rainfall-hud-footer">
        <div className="rainfall-fx-status">
          <Activity size={11} color={isZoomedIn && isRaining ? '#10b981' : '#64748b'} />
          <span className="fx-text">
            {isZoomedIn ? (isRaining ? 'Zoom FX: Active Falling Rain' : 'Zoom FX: Dry (Zoomed In)') : 'Zoom in closer for 3D rain simulation'}
          </span>
        </div>
        <button
          className={`rainfall-toggle-btn ${rainFxEnabled ? 'active' : ''}`}
          onClick={onToggleRainFx}
          title="Toggle 3D Falling Rain Particles"
        >
          <Eye size={11} />
          <span>{rainFxEnabled ? 'RAIN PARTICLES: ON' : 'RAIN PARTICLES: OFF'}</span>
        </button>
      </div>
    </div>
  );
};
