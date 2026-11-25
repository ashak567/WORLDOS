import React, { useEffect, useState } from 'react';
import { Cloud, Play, Pause, SkipBack, SkipForward, AlertTriangle, RefreshCw } from 'lucide-react';

export interface CloudFrameInfo {
  rawTime: string;
  utcIso: string;
  displayUtc: string;
  shortLabel: string;
  ageMinutes: number;
  ageLabel: string;
  isStale: boolean;
  tileUrlTemplate: string;
}

export interface CloudBrightnessEstimate {
  brightness: number; // 0..1
  hasClouds: boolean;
  estimatedBaseMeters: number;
  estimatedTopMeters: number;
}

const REALEARTH_TIMES_URL = 'https://realearth.ssec.wisc.edu/api/times?products=globalir';

export function parseRealEarthTimestamp(rawTime: string, nowMs: number = Date.now()): CloudFrameInfo {
  const match = rawTime.match(/^(\d{4})(\d{2})(\d{2})\.(\d{2})(\d{2})(\d{2})$/);
  let timestampMs = nowMs;
  let displayUtc = rawTime;
  let shortLabel = rawTime;
  let utcIso = new Date(nowMs).toISOString();

  if (match) {
    const [, y, m, d, hh, mm, ss] = match;
    utcIso = `${y}-${m}-${d}T${hh}:${mm}:${ss}Z`;
    timestampMs = Date.parse(utcIso);
    displayUtc = `${y}-${m}-${d} ${hh}:${mm} UTC`;
    shortLabel = `${hh}:${mm}Z`;
  }

  const ageMinutes = Math.max(0, Math.round((nowMs - timestampMs) / 60_000));
  const hrs = Math.floor(ageMinutes / 60);
  const mins = ageMinutes % 60;
  const ageLabel = hrs > 0 ? `${hrs}h ${mins}m old` : `${mins}m ago`;
  const isStale = ageMinutes >= 120; // > 2 hours old for hourly satellite composite

  return {
    rawTime,
    utcIso,
    displayUtc,
    shortLabel,
    ageMinutes,
    ageLabel,
    isStale,
    tileUrlTemplate: `https://realearth.ssec.wisc.edu/tiles/globalir/{z}/{x}/{y}.png?time=${encodeURIComponent(rawTime)}`,
  };
}

// Cache sampled zoom-3 tiles in memory so cockpit estimation avoids repeated network fetches
const sampledTileCache = new Map<string, ImageData | null>();

export async function sampleSatelliteCloudBrightness(
  lon: number,
  lat: number,
  rawTime?: string | null
): Promise<CloudBrightnessEstimate | null> {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (typeof document === 'undefined') return null;

  const clampedLat = Math.max(-85, Math.min(85, lat));
  const z = 3;
  const n = 1 << z;
  const xFloat = ((lon + 180) / 360) * n;
  const latRad = (clampedLat * Math.PI) / 180;
  const yFloat = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;

  const x = Math.max(0, Math.min(n - 1, Math.floor(xFloat)));
  const y = Math.max(0, Math.min(n - 1, Math.floor(yFloat)));
  const px = Math.max(0, Math.min(255, Math.floor((xFloat - x) * 256)));
  const py = Math.max(0, Math.min(255, Math.floor((yFloat - y) * 256)));

  const timeParam = rawTime ? `?time=${encodeURIComponent(rawTime)}` : '';
  const url = `https://realearth.ssec.wisc.edu/tiles/globalir/${z}/${x}/${y}.png${timeParam}`;
  const cacheKey = `${rawTime || 'latest'}:${z}:${x}:${y}`;

  let imageData = sampledTileCache.get(cacheKey);
  if (imageData === undefined) {
    try {
      const img = await new Promise<HTMLImageElement>((resolve, reject) => {
        const el = new Image();
        el.crossOrigin = 'anonymous';
        const timer = window.setTimeout(() => reject(new Error('Tile sample timeout')), 4500);
        el.onload = () => {
          window.clearTimeout(timer);
          resolve(el);
        };
        el.onerror = () => {
          window.clearTimeout(timer);
          reject(new Error('Tile load failed'));
        };
        el.src = url;
      });
      const canvas = document.createElement('canvas');
      canvas.width = 256;
      canvas.height = 256;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(img, 0, 0, 256, 256);
      imageData = ctx.getImageData(0, 0, 256, 256);
      sampledTileCache.set(cacheKey, imageData);
    } catch {
      sampledTileCache.set(cacheKey, null);
      return null;
    }
  }

  if (!imageData) return null;

  // Sample 5x5 patch around pixel
  let sum = 0;
  let samples = 0;
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      const sx = Math.max(0, Math.min(255, px + dx));
      const sy = Math.max(0, Math.min(255, py + dy));
      const idx = (sy * 256 + sx) * 4;
      const r = imageData.data[idx];
      const g = imageData.data[idx + 1];
      const b = imageData.data[idx + 2];
      const a = imageData.data[idx + 3] / 255;
      const lum = ((0.299 * r + 0.587 * g + 0.114 * b) / 255) * a;
      sum += lum;
      samples += 1;
    }
  }

  const brightness = samples > 0 ? sum / samples : 0;
  // Bright IR cloud tops correspond to cold high clouds; dark regions indicate low/no cloud deck
  const hasClouds = brightness >= 0.22;
  const estimatedBaseMeters = Math.round(2200 + brightness * 4200);
  const estimatedTopMeters = Math.round(estimatedBaseMeters + 1800 + brightness * 3800);

  return {
    brightness,
    hasClouds,
    estimatedBaseMeters,
    estimatedTopMeters,
  };
}

interface SatelliteCloudsProps {
  enabled: boolean;
  inCockpit?: boolean;
  tileErrorCount?: number;
  activeFrame: CloudFrameInfo | null;
  onActiveFrameChange: (frame: CloudFrameInfo | null) => void;
}

export const SatelliteClouds: React.FC<SatelliteCloudsProps> = ({
  enabled,
  inCockpit = false,
  tileErrorCount = 0,
  activeFrame,
  onActiveFrameChange,
}) => {
  const [frames, setFrames] = useState<CloudFrameInfo[]>([]);
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const loadRecentFrames = async () => {
    setLoading(true);
    setFetchError(null);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(REALEARTH_TIMES_URL, { signal: controller.signal });
      if (!response.ok) throw new Error(`RealEarth HTTP ${response.status}`);
      const payload = await response.json();
      const rawTimes: string[] = Array.isArray(payload?.globalir) ? payload.globalir : [];
      const recent = rawTimes.slice(-3);
      if (recent.length === 0) {
        throw new Error('No hourly satellite cloud frames available');
      }
      const now = Date.now();
      const parsed = recent.map((t) => parseRealEarthTimestamp(t, now));
      setFrames(parsed);
      const latestIdx = parsed.length - 1;
      setActiveIndex(latestIdx);
      onActiveFrameChange(parsed[latestIdx]);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : 'Satellite cloud index unavailable');
      // Keep underlying globe usable; emit null frame so no stale overlay blocks view
      if (frames.length === 0) {
        onActiveFrameChange(null);
      }
    } finally {
      window.clearTimeout(timeout);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!enabled) {
      setIsPlaying(false);
      onActiveFrameChange(null);
      return;
    }
    void loadRecentFrames();
    const refreshTimer = window.setInterval(() => {
      void loadRecentFrames();
    }, 15 * 60_000);
    return () => window.clearInterval(refreshTimer);
  }, [enabled]);

  useEffect(() => {
    if (!enabled || !isPlaying || frames.length <= 1) return;
    const timer = window.setInterval(() => {
      setActiveIndex((prev) => {
        const next = (prev + 1) % frames.length;
        onActiveFrameChange(frames[next]);
        return next;
      });
    }, 1400);
    return () => window.clearInterval(timer);
  }, [enabled, isPlaying, frames]);

  if (!enabled || inCockpit) return null;

  const current = frames[activeIndex] || activeFrame;

  const selectIndex = (idx: number) => {
    if (!frames[idx]) return;
    setActiveIndex(idx);
    onActiveFrameChange(frames[idx]);
  };

  return (
    <div className="satellite-clouds-hud" aria-label="Satellite Cloud Observation Controls">
      <div className="sat-clouds-header">
        <div className="sat-clouds-title-row">
          <Cloud size={13} color="#e2e8f0" />
          <span className="sat-clouds-title">SSEC REALEARTH IR CLOUDS</span>
          {current?.isStale && (
            <span className="sat-clouds-stale-badge" title="Latest available satellite mosaic is over 2 hours old">
              <AlertTriangle size={10} /> OLD ({current.ageLabel})
            </span>
          )}
        </div>
        <button
          type="button"
          className="sat-clouds-refresh-btn"
          onClick={() => void loadRecentFrames()}
          disabled={loading}
          title="Refresh hourly satellite observations"
          aria-label="Refresh satellite cloud observations"
        >
          <RefreshCw size={11} className={loading ? 'spin-icon' : ''} />
        </button>
      </div>

      {current ? (
        <div className="sat-clouds-meta">
          <span className="sat-clouds-time" data-testid="cloud-observation-time">
            {current.displayUtc}
          </span>
          <span className="sat-clouds-age">
            Frame {activeIndex + 1}/{frames.length || 1} · {current.ageLabel}
          </span>
        </div>
      ) : (
        <div className="sat-clouds-meta">
          <span className="sat-clouds-age">
            {loading ? 'Loading hourly IR metadata…' : fetchError || 'Waiting for SSEC IR frame…'}
          </span>
        </div>
      )}

      {tileErrorCount > 0 && (
        <div className="sat-clouds-warning" role="status">
          <AlertTriangle size={11} />
          <span>Missing cloud tiles on this frame — underlying globe remains active.</span>
        </div>
      )}

      {fetchError && (
        <div className="sat-clouds-warning" role="status">
          <AlertTriangle size={11} />
          <span>{fetchError} — globe unaffected.</span>
        </div>
      )}

      {frames.length > 0 && (
        <div className="sat-clouds-controls">
          <button
            type="button"
            className="sat-clouds-btn"
            onClick={() => selectIndex((activeIndex - 1 + frames.length) % frames.length)}
            disabled={frames.length <= 1}
            title="Previous hourly observation"
            aria-label="Previous cloud frame"
          >
            <SkipBack size={12} />
          </button>

          <button
            type="button"
            className={`sat-clouds-play-btn ${isPlaying ? 'playing' : ''}`}
            onClick={() => setIsPlaying((p) => !p)}
            disabled={frames.length <= 1}
            aria-label={isPlaying ? 'Pause cloud playback' : 'Play cloud loop'}
          >
            {isPlaying ? <Pause size={12} /> : <Play size={12} />}
            <span>{isPlaying ? 'PAUSE' : 'PLAY 3H'}</span>
          </button>

          <button
            type="button"
            className="sat-clouds-btn"
            onClick={() => selectIndex((activeIndex + 1) % frames.length)}
            disabled={frames.length <= 1}
            title="Next hourly observation"
            aria-label="Next cloud frame"
          >
            <SkipForward size={12} />
          </button>

          <div className="sat-clouds-frame-dots">
            {frames.map((f, idx) => (
              <button
                key={f.rawTime}
                type="button"
                className={`sat-clouds-dot-btn ${idx === activeIndex ? 'active' : ''}`}
                onClick={() => selectIndex(idx)}
                title={f.displayUtc}
              >
                {f.shortLabel}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
