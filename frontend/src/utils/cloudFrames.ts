export interface CloudBrightnessEstimate {
  brightness: number;
  hasClouds: boolean;
  estimatedBaseMeters: number;
  estimatedTopMeters: number;
}

// A single geographic image avoids tile request quotas and visible tile boundaries.
export const CLOUD_WMS = 'https://view.eumetsat.int/geoserver/wms';
export const CLOUD_LAYER = 'mumi:worldcloudmap_ir108';

export interface CloudFrameInfo {
  rawTime: string;
  utcIso: string;
  displayUtc: string;
  shortLabel: string;
  ageMinutes: number;
  ageLabel: string;
  isStale: boolean;
  imageUrl: string;
}

export function formatCloudAge(ageMinutes: number): string {
  const safeMins = Math.max(0, Math.round(ageMinutes));
  const hrs = Math.floor(safeMins / 60);
  const mins = safeMins % 60;
  return hrs > 0 ? `${hrs}h ${mins}m old` : `${mins}m ago`;
}

export function cloudFrame(rawTime: string, now = Date.now()): CloudFrameInfo {
  const ms = Date.parse(rawTime);
  if (!Number.isFinite(ms)) throw new Error('Invalid satellite observation time');
  const utcIso = new Date(ms).toISOString();
  const ageMinutes = Math.max(0, Math.round((now - ms) / 60000));
  const params = new URLSearchParams({
    service: 'WMS',
    version: '1.1.1',
    request: 'GetMap',
    layers: CLOUD_LAYER,
    styles: '',
    srs: 'EPSG:4326',
    bbox: '-180,-90,180,90',
    width: '1024',
    height: '512',
    format: 'image/png',
    transparent: 'true',
    time: utcIso,
  });
  return {
    rawTime: utcIso,
    utcIso,
    displayUtc: utcIso.slice(0, 16).replace('T', ' ') + ' UTC',
    shortLabel: utcIso.slice(11, 16) + 'Z',
    ageMinutes,
    ageLabel: formatCloudAge(ageMinutes),
    isStale: ageMinutes >= 360,
    imageUrl: `${CLOUD_WMS}?${params}`,
  };
}

function parseIsoStepMs(rawInterval: string | undefined): number {
  if (!rawInterval) return 0;
  const match = rawInterval.trim().match(/^PT(\d+)(H|M)$/i);
  if (!match) return 0;
  const val = Number(match[1]);
  if (!Number.isFinite(val) || val <= 0) return 0;
  return match[2].toUpperCase() === 'H' ? val * 3_600_000 : val * 60_000;
}

export async function fetchCloudFrames(signal: AbortSignal): Promise<CloudFrameInfo[]> {
  const r = await fetch(`${CLOUD_WMS}?service=WMS&request=GetCapabilities`, { signal });
  if (!r.ok) throw new Error(`Satellite metadata HTTP ${r.status}`);
  const xml = new DOMParser().parseFromString(await r.text(), 'application/xml');
  const layer = Array.from(xml.getElementsByTagName('Layer')).find((l) =>
    Array.from(l.children).some((c) => c.localName === 'Name' && c.textContent === CLOUD_LAYER)
  );
  const dimension =
    layer &&
    Array.from(layer.children).find(
      (c) => c.localName === 'Dimension' && c.getAttribute('name') === 'time'
    );
  const latest = dimension?.getAttribute('default')?.trim();
  if (!latest || !Number.isFinite(Date.parse(latest))) {
    throw new Error('Satellite observation times unavailable');
  }

  const rawText = dimension?.textContent?.trim() || '';
  const parts = rawText.split('/');
  const stepMs = parseIsoStepMs(parts[2]);
  const startMs = parts[0] ? Date.parse(parts[0]) : NaN;
  const latestMs = Date.parse(latest);
  const now = Date.now();

  if (stepMs > 0) {
    const candidateOffsets = [2, 1, 0]
      .map((i) => latestMs - i * stepMs)
      .filter((ts) => !Number.isFinite(startMs) || ts >= startMs);
    if (candidateOffsets.length > 0) {
      return candidateOffsets.map((ts) => cloudFrame(new Date(ts).toISOString(), now));
    }
  }
  return [cloudFrame(new Date(latestMs).toISOString(), now)];
}

type CloudImage = { url: string; pixels: ImageData };
const cache = new Map<string, Promise<CloudImage>>();

export function loadCloudImage(frame: CloudFrameInfo): Promise<CloudImage> {
  const found = cache.get(frame.rawTime);
  if (found) return found;
  const pending = new Promise<CloudImage>((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    const timer = window.setTimeout(() => {
      img.src = '';
      reject(new Error('Cloud image timed out'));
    }, 20000);
    img.onerror = () => {
      clearTimeout(timer);
      reject(new Error('Cloud image unavailable'));
    };
    img.onload = () => {
      clearTimeout(timer);
      try {
        if (img.width !== 1024 || img.height !== 512) {
          throw new Error('Unexpected cloud image dimensions');
        }
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('Canvas unavailable');
        ctx.drawImage(img, 0, 0);
        const pixels = ctx.getImageData(0, 0, img.width, img.height);
        const overlay = ctx.createImageData(img.width, img.height);
        for (let i = 0; i < pixels.data.length; i += 4) {
          const brightness = pixels.data[i] / 255;
          overlay.data[i] = overlay.data[i + 1] = overlay.data[i + 2] = 255;
          // IR brightness is a visual approximation, not a measured cloud mask/altitude.
          overlay.data[i + 3] = Math.round(
            Math.pow(Math.max(0, (brightness - 0.30) / 0.70), 1.5) * pixels.data[i + 3]
          );
        }
        ctx.putImageData(overlay, 0, 0);
        resolve({ url: canvas.toDataURL('image/png'), pixels });
      } catch (e) {
        reject(e);
      }
    };
    img.src = frame.imageUrl;
  });
  cache.set(frame.rawTime, pending);
  while (cache.size > 3) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey !== undefined) cache.delete(oldestKey);
    else break;
  }
  pending.catch(() => {
    if (cache.get(frame.rawTime) === pending) cache.delete(frame.rawTime);
  });
  return pending;
}

export async function sampleSatelliteCloudBrightness(
  lon: number,
  lat: number,
  rawTime?: string | null
): Promise<CloudBrightnessEstimate | null> {
  if (!rawTime || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  try {
    const { pixels } = await loadCloudImage(cloudFrame(rawTime));
    const x = Math.min(1023, Math.max(0, Math.floor(((lon + 180) / 360) * 1024)));
    const y = Math.min(511, Math.max(0, Math.floor(((90 - lat) / 180) * 512)));
    const idx = (y * 1024 + x) * 4;
    const brightness = (pixels.data[idx] / 255) * (pixels.data[idx + 3] / 255);
    const estimatedBaseMeters = Math.round(2200 + brightness * 4200);
    return {
      brightness,
      hasClouds: brightness >= 0.45,
      estimatedBaseMeters,
      estimatedTopMeters: Math.round(estimatedBaseMeters + 1800 + brightness * 3800),
    };
  } catch {
    return null;
  }
}
