import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Cloud, Play, Pause, SkipBack, SkipForward, AlertTriangle, RefreshCw } from 'lucide-react';

import { CloudFrameInfo, cloudFrame, fetchCloudFrames, loadCloudImage } from '../utils/cloudFrames';
export { sampleSatelliteCloudBrightness } from '../utils/cloudFrames';
export type { CloudFrameInfo, CloudBrightnessEstimate } from '../utils/cloudFrames';

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

  const mountedRef = useRef<boolean>(true);
  const enabledRef = useRef<boolean>(enabled);
  enabledRef.current = enabled;
  const loadGenRef = useRef<number>(0);
  const activeControllerRef = useRef<AbortController | null>(null);
  const framesRef = useRef<CloudFrameInfo[]>(frames);
  framesRef.current = frames;
  const onActiveFrameChangeRef = useRef(onActiveFrameChange);
  onActiveFrameChangeRef.current = onActiveFrameChange;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      loadGenRef.current += 1;
      activeControllerRef.current?.abort();
      activeControllerRef.current = null;
    };
  }, []);

  const loadRecentFrames = useCallback(async () => {
    if (!enabledRef.current) return;
    const gen = ++loadGenRef.current;
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;

    setLoading(true);
    setFetchError(null);
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const parsed = await fetchCloudFrames(controller.signal);
      if (!mountedRef.current || !enabledRef.current || gen !== loadGenRef.current) return;

      // Preload frames; a failed older frame must not prevent displaying a working latest frame.
      const settled = await Promise.allSettled(parsed.map((f) => loadCloudImage(f)));
      if (!mountedRef.current || !enabledRef.current || gen !== loadGenRef.current) return;

      const workingFrames = parsed.filter((_, i) => settled[i].status === 'fulfilled');
      if (workingFrames.length === 0) {
        const firstErr = settled.find((s): s is PromiseRejectedResult => s.status === 'rejected');
        throw firstErr?.reason instanceof Error
          ? firstErr.reason
          : new Error('Cloud imagery unavailable');
      }

      const now = Date.now();
      const refreshed = workingFrames.map((f) => cloudFrame(f.rawTime, now));
      const partialFailure = workingFrames.length < parsed.length;
      if (partialFailure) {
        setFetchError('Some older cloud frames were unavailable; showing loaded imagery');
      }

      setFrames(refreshed);
      const latestIdx = refreshed.length - 1;
      setActiveIndex(latestIdx);
      onActiveFrameChangeRef.current(refreshed[latestIdx]);
    } catch (err) {
      if (controller.signal.aborted && (!enabledRef.current || gen !== loadGenRef.current)) return;
      if (!mountedRef.current || !enabledRef.current || gen !== loadGenRef.current) return;
      setFetchError(err instanceof Error ? err.message : 'Satellite cloud index unavailable');
      // Retain any already loaded frame on refresh error; only clear if none exist yet.
      if (framesRef.current.length === 0) {
        onActiveFrameChangeRef.current(null);
      }
    } finally {
      window.clearTimeout(timeout);
      if (mountedRef.current && gen === loadGenRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      loadGenRef.current += 1;
      activeControllerRef.current?.abort();
      activeControllerRef.current = null;
      setIsPlaying(false);
      setLoading(false);
      setFetchError(null);
      onActiveFrameChangeRef.current(null);
      return;
    }
    void loadRecentFrames();
    const refreshTimer = window.setInterval(() => {
      void loadRecentFrames();
    }, 15 * 60_000);
    return () => {
      window.clearInterval(refreshTimer);
      loadGenRef.current += 1;
      activeControllerRef.current?.abort();
    };
  }, [enabled, loadRecentFrames]);

  // Keep observation age and stale indicator accurate over time without redundant fetches
  useEffect(() => {
    if (!enabled || frames.length === 0) return;
    const ageTimer = window.setInterval(() => {
      const now = Date.now();
      setFrames((prev) => prev.map((f) => cloudFrame(f.rawTime, now)));
    }, 60_000);
    return () => window.clearInterval(ageTimer);
  }, [enabled, frames.length]);

  useEffect(() => {
    if (!enabled || !isPlaying || frames.length <= 1) return;
    const timer = window.setInterval(() => {
      setActiveIndex((prev) => {
        const next = (prev + 1) % frames.length;
        onActiveFrameChangeRef.current(frames[next]);
        return next;
      });
    }, 1400);
    return () => window.clearInterval(timer);
  }, [enabled, isPlaying, frames]);

  if (!enabled || inCockpit) return null;

  const rawCurrent = frames[activeIndex] || activeFrame;
  const current = rawCurrent ? cloudFrame(rawCurrent.rawTime, Date.now()) : null;

  const selectIndex = (idx: number) => {
    if (!frames[idx]) return;
    setActiveIndex(idx);
    onActiveFrameChangeRef.current(frames[idx]);
  };

  return (
    <div className="satellite-clouds-hud" aria-label="Satellite Cloud Observation Controls">
      <div className="sat-clouds-header">
        <div className="sat-clouds-title-row">
          <Cloud size={13} color="#e2e8f0" />
          <span className="sat-clouds-title">EUMETSAT IR CLOUDS</span>
          {current?.isStale && (
            <span className="sat-clouds-stale-badge" title="Latest available satellite mosaic is over 6 hours old">
              <AlertTriangle size={10} /> OLD ({current.ageLabel})
            </span>
          )}
        </div>
        <button
          type="button"
          className="sat-clouds-refresh-btn"
          onClick={() => void loadRecentFrames()}
          disabled={loading}
          title="Refresh 3-hourly satellite observations"
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
            {loading ? 'Loading 3-hourly IR metadata…' : fetchError || 'Waiting for EUMETSAT IR frame…'}
          </span>
        </div>
      )}

      {tileErrorCount > 0 && (
        <div className="sat-clouds-warning" role="status">
          <AlertTriangle size={11} />
          <span>Cloud image unavailable — underlying globe remains active.</span>
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
            title="Previous 3-hourly observation"
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
            <span>{isPlaying ? 'PAUSE' : 'PLAY LOOP'}</span>
          </button>

          <button
            type="button"
            className="sat-clouds-btn"
            onClick={() => selectIndex((activeIndex + 1) % frames.length)}
            disabled={frames.length <= 1}
            title="Next 3-hourly observation"
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
