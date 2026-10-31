import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Send, Square, Volume2, X } from 'lucide-react';
import {
  answerAssistant,
  AssistantAnswer,
  AssistantAction,
  AssistantContext,
  transcribeAssistantAudio,
} from '../api';

interface AssistantPanelProps {
  isOpen: boolean;
  context: AssistantContext;
  onClose: () => void;
  onAction: (action: AssistantAction) => void;
}

type TravelPreferences = NonNullable<AssistantContext['travel_preferences']>;
const PREFERENCES_KEY = 'worldos-assistant-preferences-v1';

function readPreferences(): TravelPreferences {
  try {
    const saved = JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) || '{}');
    return {
      ...( ['relaxed', 'balanced', 'packed'].includes(saved.pace) ? { pace: saved.pace } : {}),
      ...(typeof saved.photo_interest === 'string' && saved.photo_interest.trim().length <= 120 && saved.photo_interest.trim()
        ? { photo_interest: saved.photo_interest.trim() } : {}),
    };
  } catch { return {}; }
}

export const AssistantPanel: React.FC<AssistantPanelProps> = ({ isOpen, context, onClose, onAction }) => {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [preferences, setPreferences] = useState<TravelPreferences>(readPreferences);
  const [paceDraft, setPaceDraft] = useState<TravelPreferences['pace']>('balanced');
  const [photoDraft, setPhotoDraft] = useState('');
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const cancelRecordingRef = useRef(false);
  const questionRef = useRef<HTMLTextAreaElement>(null);

  const stopSpeaking = useCallback(() => {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  }, []);

  const releaseMicrophone = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    setIsRecording(false);
  }, []);

  useEffect(() => {
    if (isOpen) questionRef.current?.focus();
    else {
      cancelRecordingRef.current = true;
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
      releaseMicrophone();
      stopSpeaking();
      setQuestion('');
      setAnswer(null);
      setMessage('');
    }
  }, [isOpen, releaseMicrophone, stopSpeaking]);

  useEffect(() => () => {
    cancelRecordingRef.current = true;
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    releaseMicrophone();
    stopSpeaking();
  }, [releaseMicrophone, stopSpeaking]);

  const startRecording = async () => {
    setMessage('');
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setMessage('Microphone recording is not supported here. You can still type your question.');
      return;
    }
    try {
      cancelRecordingRef.current = false;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        releaseMicrophone();
        if (cancelRecordingRef.current || !blob.size) return;
        setIsBusy(true);
        try {
          const transcript = await transcribeAssistantAudio(blob);
          if (transcript.service_status === 'unavailable') {
            setMessage(transcript.detail || 'Local speech recognition is unavailable. Type your question instead.');
          } else {
            setQuestion(transcript.text);
            questionRef.current?.focus();
          }
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'The recording could not be transcribed.');
        } finally {
          setIsBusy(false);
        }
      };
      recorder.start();
      setIsRecording(true);
      setMessage('Listening. Stop when you’re done; the recording is limited to 30 seconds.');
      timerRef.current = window.setTimeout(() => {
        if (recorder.state === 'recording') recorder.stop();
      }, 30_000);
    } catch {
      releaseMicrophone();
      setMessage('Microphone access was denied or unavailable. You can still type your question.');
    }
  };

  const speakAnswer = (text: string) => {
    if (!('speechSynthesis' in window)) {
      setMessage('This browser has no speech output; the answer is still available as text.');
      return;
    }
    const localVoice = window.speechSynthesis.getVoices().find((voice) => voice.localService);
    if (!localVoice) {
      setMessage('No local speech voice is installed, so I left the answer in text.');
      return;
    }
    stopSpeaking();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = localVoice;
    window.speechSynthesis.speak(utterance);
  };

  const sendQuestion = async (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || isBusy) return;
    stopSpeaking();
    setIsBusy(true);
    setMessage('');
    setAnswer(null);
    try {
      const result = await answerAssistant(text, { ...context, ...(Object.keys(preferences).length ? { travel_preferences: preferences } : {}) });
      setAnswer(result);
      result.actions.forEach(onAction);
      if (result.service_status === 'unavailable') setMessage('WORLDOS kept this request local, but a required local service is unavailable.');
      else speakAnswer(result.answer);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'WORLDOS could not answer right now.');
    } finally {
      setIsBusy(false);
    }
  };

  const savePreferences = (event: FormEvent) => {
    event.preventDefault();
    const next = { ...(paceDraft ? { pace: paceDraft } : {}), ...(photoDraft.trim() ? { photo_interest: photoDraft.trim().slice(0, 120) } : {}) };
    if (!Object.keys(next).length) return;
    const summary = [next.pace && `Pace: ${next.pace}`, next.photo_interest && `Photo interests: ${next.photo_interest}`].filter(Boolean).join('\n');
    if (!window.confirm(`Save these preferences on this device?\n\n${summary}`)) return;
    try {
      window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
      setPreferences(next);
      setMessage('Preferences saved on this device.');
    } catch { setMessage('This browser could not save preferences.'); }
  };

  const removePreference = (key: keyof TravelPreferences) => {
    const next = { ...preferences };
    delete next[key];
    try {
      if (Object.keys(next).length) window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
      else window.localStorage.removeItem(PREFERENCES_KEY);
      setPreferences(next);
    } catch { setMessage('This browser could not update saved preferences.'); }
  };

  if (!isOpen) return null;

  return (
    <section className="assistant-panel" aria-label="WORLDOS assistant" aria-modal="false">
      <header className="assistant-panel-header">
        <div>
          <strong>WORLDOS ASSISTANT</strong>
          <span>Local voice · map-aware answers</span>
        </div>
        <button className="assistant-icon-button" type="button" onClick={onClose} aria-label="Close assistant">
          <X size={16} />
        </button>
      </header>

      <div className="assistant-panel-body">
        <p className="assistant-privacy-note">Your recording and question stay on this PC. Answers show the WORLDOS sources they use.</p>
        <details className="assistant-preferences">
          <summary>Optional travel preferences</summary>
          {Object.entries(preferences).map(([key, value]) => (
            <div className="assistant-preference-item" key={key}>
              <span>{key === 'pace' ? `Pace: ${value}` : `Photo interests: ${value}`}</span>
              <button type="button" onClick={() => removePreference(key as keyof TravelPreferences)}>Remove</button>
            </div>
          ))}
          <form onSubmit={savePreferences}>
            <label htmlFor="assistant-pace">Travel pace</label>
            <select id="assistant-pace" value={paceDraft || ''} onChange={(event) => setPaceDraft((event.target.value || undefined) as TravelPreferences['pace'])}>
              <option value="">Not set</option><option value="relaxed">Relaxed</option><option value="balanced">Balanced</option><option value="packed">Packed</option>
            </select>
            <label htmlFor="assistant-photo-interest">Photo interests (up to 120 characters)</label>
            <input id="assistant-photo-interest" maxLength={120} value={photoDraft} onChange={(event) => setPhotoDraft(event.target.value)} placeholder="e.g. architecture, coastlines" />
            <button className="assistant-control-button" type="submit" disabled={!paceDraft && !photoDraft.trim()}>Review and save</button>
          </form>
        </details>
        <form onSubmit={sendQuestion}>
          <label htmlFor="assistant-question">Ask about this map</label>
          <textarea
            id="assistant-question"
            ref={questionRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            maxLength={1200}
            placeholder="What stands out in this view?"
          />
          <div className="assistant-controls">
            <button className="assistant-control-button" type="button" onClick={isRecording ? () => recorderRef.current?.stop() : startRecording} disabled={isBusy}>
              {isRecording ? <Square size={14} /> : <Mic size={14} />}
              {isRecording ? 'Stop' : 'Talk'}
            </button>
            <button className="assistant-control-button primary" type="submit" disabled={!question.trim() || isBusy || isRecording}>
              <Send size={14} /> {isBusy ? 'Working…' : 'Ask'}
            </button>
            <button className="assistant-control-button" type="button" onClick={stopSpeaking} aria-label="Stop speaking">
              <Volume2 size={14} /> Stop voice
            </button>
          </div>
        </form>

        <div className="assistant-status" aria-live="polite">{message}</div>
        {answer && (
          <article className="assistant-answer">
            <p>{answer.answer}</p>
            {answer.evidence.length > 0 && (
              <div className="assistant-evidence">
                <strong>Sources</strong>
                {answer.evidence.map((item) => (
                  <div className="assistant-evidence-item" key={item.evidence_id}>
                    <span>{item.source_name}</span>
                    <time dateTime={item.retrieved_at}>{new Date(item.retrieved_at).toLocaleString()}</time>
                    <small>{item.freshness}</small>
                  </div>
                ))}
              </div>
            )}
          </article>
        )}
      </div>
    </section>
  );
};
