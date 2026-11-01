import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { ConversationProvider, useConversation } from '@elevenlabs/react';
import { Mic, PhoneOff, Send, Volume2, X } from 'lucide-react';
import { AssistantAction, AssistantContext, fetchAssistantMapContext, getAssistantSessionToken } from '../api';

interface AssistantPanelProps {
  isOpen: boolean;
  context: AssistantContext;
  onClose: () => void;
  onAction: (action: AssistantAction) => void;
}

type TravelPreferences = NonNullable<AssistantContext['travel_preferences']>;
type AssistantMessage = { role: 'user' | 'ai'; message: string };
const PREFERENCES_KEY = 'worldos-assistant-preferences-v1';
const SAFE_LAYER_IDS = new Set([
  'country-boundaries', 'population-observations', 'aircraft-states', 'maritime-vessels',
  'space-satellites', 'surveillance-cameras', 'earthquake-events', 'natural-hazards',
  'thermal-fires', 'critical-infrastructure', 'anomalies', 'system-alerts',
]);

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

export const AssistantPanel: React.FC<AssistantPanelProps> = (props) => (
  <ConversationProvider>
    <AssistantPanelSession {...props} />
  </ConversationProvider>
);

const AssistantPanelSession: React.FC<AssistantPanelProps> = ({ isOpen, context, onClose, onAction }) => {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [evidence, setEvidence] = useState<NonNullable<Awaited<ReturnType<typeof fetchAssistantMapContext>>['evidence']>>([]);
  const [isStarting, setIsStarting] = useState(false);
  const [message, setMessage] = useState('');
  const [preferences, setPreferences] = useState<TravelPreferences>(readPreferences);
  const [paceDraft, setPaceDraft] = useState<TravelPreferences['pace']>('balanced');
  const [photoDraft, setPhotoDraft] = useState('');
  const contextRef = useRef(context);
  const preferencesRef = useRef(preferences);
  const onActionRef = useRef(onAction);
  contextRef.current = context;
  preferencesRef.current = preferences;
  onActionRef.current = onAction;

  const handleMessage = useCallback((item: AssistantMessage) => {
    if (item.message.trim()) setMessages((current) => [...current.slice(-19), item]);
  }, []);
  const conversation = useConversation({
    onMessage: ({ message: text, role, source }) => handleMessage({ role: role === 'user' || source === 'user' ? 'user' : 'ai', message: text }),
    onError: (error) => setMessage(error || 'The ElevenLabs conversation hit a snag.'),
    clientTools: {
      get_worldos_map_context: async () => {
        setEvidence([]);
        try {
          const data = await fetchAssistantMapContext({
            ...contextRef.current,
            ...(Object.keys(preferencesRef.current).length ? { travel_preferences: preferencesRef.current } : {}),
          });
          setEvidence(data.evidence || []);
          return JSON.stringify(data);
        } catch (error) {
          return JSON.stringify({ error: error instanceof Error ? error.message : 'Map context unavailable' });
        }
      },
      set_map_layer_visibility: async (args: { layer_id: string; visible: boolean }) => {
        if (!SAFE_LAYER_IDS.has(args.layer_id) || typeof args.visible !== 'boolean') return JSON.stringify({ success: false, message: 'That map layer action is not allowed.' });
        onActionRef.current({ type: 'set_layer_visibility', layer_id: args.layer_id, visible: args.visible });
        return JSON.stringify({ success: true, message: `${args.layer_id} is now ${args.visible ? 'visible' : 'hidden'}.` });
      },
    },
  });

  useEffect(() => {
    if (!isOpen && conversation.status !== 'disconnected') void conversation.endSession();
    if (!isOpen) {
      setQuestion('');
      setMessage('');
      setEvidence([]);
      setMessages([]);
    }
  }, [isOpen]);

  const startConversation = async () => {
    setIsStarting(true);
    setMessage('Connecting to your WORLDOS assistant…');
    try {
      const conversationToken = await getAssistantSessionToken();
      await conversation.startSession({ conversationToken });
      setMessage('Connected. Ask about the map or tell me what to show.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not connect to ElevenLabs.');
    } finally {
      setIsStarting(false);
    }
  };

  const sendQuestion = (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || conversation.status !== 'connected') return;
    conversation.sendUserMessage(text);
    setQuestion('');
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
    } catch { setMessage('This browser could not update preferences.'); }
  };

  if (!isOpen) return null;

  return (
    <section className="assistant-panel" aria-label="WORLDOS assistant" aria-modal="false">
      <header className="assistant-panel-header">
        <div>
          <strong>WORLDOS ASSISTANT</strong>
          <span>{conversation.status === 'connected' ? (conversation.isSpeaking ? 'Speaking' : 'Listening') : 'ElevenLabs intelligence · voice'}</span>
        </div>
        <button className="assistant-icon-button" type="button" onClick={onClose} aria-label="Close assistant"><X size={16} /></button>
      </header>

      <div className="assistant-panel-body">
        <p className="assistant-privacy-note">ElevenLabs processes your voice and chat. WORLDOS shares a small, sourced slice of the current map and any saved travel preferences only when the assistant asks for it.</p>
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

        <div className="assistant-transcript" aria-live="polite">
          {messages.map((item, index) => <p className={`assistant-message ${item.role}`} key={`${index}-${item.message.slice(0, 20)}`}><strong>{item.role === 'ai' ? 'WORLDOS' : 'You'}</strong>{item.message}</p>)}
        </div>
        {evidence.length > 0 && <div className="assistant-evidence"><strong>Map sources shared with the assistant</strong>{evidence.map((item) => <div className="assistant-evidence-item" key={item.evidence_id}><span>{item.source_name}</span><time dateTime={item.retrieved_at}>{new Date(item.retrieved_at).toLocaleString()}</time></div>)}</div>}

        <form onSubmit={sendQuestion}>
          <label htmlFor="assistant-question">Ask by text</label>
          <textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} maxLength={1200} placeholder="What stands out in this view?" disabled={conversation.status !== 'connected'} />
          <div className="assistant-controls">
            {conversation.status === 'connected' ? (
              <>
                <button className="assistant-control-button" type="button" onClick={() => conversation.setMuted(!conversation.isMuted)}><Mic size={14} /> {conversation.isMuted ? 'Unmute' : 'Mute'}</button>
                <button className="assistant-control-button" type="button" onClick={() => void conversation.endSession()}><PhoneOff size={14} /> End voice</button>
                <button className="assistant-control-button primary" type="submit" disabled={!question.trim()}><Send size={14} /> Send</button>
              </>
            ) : (
              <button className="assistant-control-button primary" type="button" onClick={() => void startConversation()} disabled={isStarting}><Mic size={14} /> {isStarting ? 'Connecting…' : 'Start voice assistant'}</button>
            )}
            <span><Volume2 size={14} /> {conversation.status}</span>
          </div>
        </form>
        <div className="assistant-status" aria-live="polite">{message}</div>
      </div>
    </section>
  );
};
