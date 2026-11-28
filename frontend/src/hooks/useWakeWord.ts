import { useCallback, useEffect, useRef, useState } from 'react';

function buildWakeRegex(name: string): RegExp {
  const normalized = name
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const candidates =
    normalized === 'rogers' || normalized === 'roger'
      ? ['rogers', 'roger']
      : normalized
        ? [normalized]
        : ['rogers', 'roger'];

  const pattern = candidates
    .map((phrase) => phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+'))
    .join('|');
  return new RegExp(`(?:^|\\s)(?:hey\\s+)?(?:${pattern})(?:$|\\s)`, 'i');
}

// Browser speech recognition requires explicit microphone consent and a visible page.
// It is an opt-in convenience, not an always-on OS/background assistant.
export function useWakeWord(name: string, busy: boolean, onWake: () => void) {
  const [enabled, setEnabled] = useState(false);
  const [status, setStatus] = useState('Wake word off');
  const wakeRef = useRef(onWake);
  wakeRef.current = onWake;
  const recognitionRef = useRef<any>(null);
  const activeRef = useRef(false);
  const releaseWaitersRef = useRef<Array<() => void>>([]);

  const supported =
    typeof window !== 'undefined' &&
    Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const flushReleaseWaiters = useCallback(() => {
    const waiters = releaseWaitersRef.current.splice(0);
    for (const resolve of waiters) resolve();
  }, []);

  // Explicitly wait until SpeechRecognition releases the browser microphone before starting WebRTC voice.
  const releaseMicrophone = useCallback(async () => {
    const rec = recognitionRef.current;
    if (!rec || !activeRef.current) return;
    await new Promise<void>((resolve) => {
      const fallbackTimer = window.setTimeout(() => {
        activeRef.current = false;
        resolve();
      }, 350);
      releaseWaitersRef.current.push(() => {
        window.clearTimeout(fallbackTimer);
        resolve();
      });
      try {
        rec.abort();
      } catch {
        window.clearTimeout(fallbackTimer);
        activeRef.current = false;
        flushReleaseWaiters();
      }
    });
  }, [flushReleaseWaiters]);

  useEffect(() => {
    if (!enabled || !supported) {
      activeRef.current = false;
      recognitionRef.current = null;
      flushReleaseWaiters();
      setStatus(supported ? 'Wake word off' : 'Wake words unavailable in this browser');
      return;
    }

    if (busy) {
      setStatus('Wake listener paused during active voice session');
      return;
    }

    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const wakeRegex = buildWakeRegex(name);
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const recognition = new Recognition();
    recognitionRef.current = recognition;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    const scheduleRestart = (delayMs: number) => {
      if (timer) clearTimeout(timer);
      if (disposed || document.hidden) return;
      timer = setTimeout(start, delayMs);
    };

    const start = () => {
      if (disposed || document.hidden || activeRef.current) return;
      if (timer) {
        clearTimeout(timer);
        timer = undefined;
      }
      try {
        activeRef.current = true;
        recognition.start();
      } catch (err: any) {
        activeRef.current = false;
        const msg = String(err?.name || err?.message || '');
        if (/InvalidStateError/i.test(msg)) {
          scheduleRestart(600);
          return;
        }
        failures += 1;
        setStatus('Wake listener unavailable; use Start voice.');
        setEnabled(false);
      }
    };

    recognition.onstart = () => {
      if (disposed) return;
      activeRef.current = true;
      failures = 0;
      setStatus(`Listening for “Hey ${name}”`);
    };

    recognition.onresult = (event: any) => {
      if (disposed) return;
      const transcript = Array.from(event.results)
        .slice(event.resultIndex)
        .map((r: any) => r[0]?.transcript || '')
        .join(' ')
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

      if (wakeRegex.test(transcript)) {
        disposed = true;
        if (timer) clearTimeout(timer);
        try {
          recognition.abort();
        } catch {}
        activeRef.current = false;
        setStatus('Waking up…');
        wakeRef.current();
      }
    };

    recognition.onerror = (event: any) => {
      activeRef.current = false;
      if (event.error === 'aborted' || event.error === 'no-speech') return;
      failures += 1;
      const fatal =
        event.error === 'not-allowed' ||
        event.error === 'audio-capture' ||
        event.error === 'service-not-allowed' ||
        failures >= 3;
      setStatus(
        event.error === 'not-allowed'
          ? 'Microphone permission denied. Use Start voice after allowing it.'
          : fatal
            ? `Wake listener stopped (${event.error}); use Start voice.`
            : `Wake listener: ${event.error}`
      );
      if (fatal) {
        disposed = true;
        if (timer) clearTimeout(timer);
        setEnabled(false);
      }
    };

    recognition.onend = () => {
      activeRef.current = false;
      flushReleaseWaiters();
      if (!disposed && !document.hidden) {
        scheduleRestart(1200);
      }
    };

    const visibility = () => {
      if (timer) {
        clearTimeout(timer);
        timer = undefined;
      }
      if (document.hidden) {
        try {
          recognition.abort();
        } catch {}
        setStatus('Wake listener paused while page is hidden');
      } else if (!disposed) {
        scheduleRestart(250);
      }
    };

    document.addEventListener('visibilitychange', visibility);
    if (document.hidden) {
      setStatus('Wake listener paused while page is hidden');
    } else {
      start();
    }

    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', visibility);
      try {
        recognition.abort();
      } catch {}
      activeRef.current = false;
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      flushReleaseWaiters();
    };
  }, [enabled, busy, supported, name, flushReleaseWaiters]);

  return {
    enabled,
    supported,
    status,
    setEnabled,
    releaseMicrophone,
    stopListening: () => {
      try {
        recognitionRef.current?.abort();
      } catch {}
    },
  };
}
