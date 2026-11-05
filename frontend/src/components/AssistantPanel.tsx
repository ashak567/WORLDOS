import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { ConversationProvider, useConversation } from '@elevenlabs/react';
import {
  Mic,
  PhoneOff,
  Send,
  Trash2,
  Volume2,
  X,
  Globe,
  MapPin,
  Calendar,
  Utensils,
  Compass,
  Star,
  Sparkles,
} from 'lucide-react';
import {
  AssistantAction,
  AssistantContext,
  fetchAssistantMapContext,
  getAssistantSession,
  fetchTravelPlan,
  TravelPlanResponse,
} from '../api';

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
  'thermal-fires',
]);

const POPULAR_LOCATIONS: { keywords: string[]; center: [number, number]; zoom: number; label: string }[] = [
  { keywords: ['tokyo', 'japan', 'haneda', 'narita'], center: [139.6917, 35.6895], zoom: 12, label: 'Tokyo, Japan' },
  { keywords: ['shibuya'], center: [139.7016, 35.6580], zoom: 15, label: 'Shibuya Crossing, Tokyo' },
  { keywords: ['shinjuku'], center: [139.7006, 35.6897], zoom: 15, label: 'Shinjuku, Tokyo' },
  { keywords: ['kyoto'], center: [135.7681, 35.0116], zoom: 13, label: 'Kyoto, Japan' },
  { keywords: ['osaka'], center: [135.5023, 34.6937], zoom: 13, label: 'Osaka, Japan' },
  { keywords: ['new york', 'nyc', 'manhattan', 'jfk', 'newark'], center: [-74.0060, 40.7128], zoom: 12, label: 'New York City, USA' },
  { keywords: ['times square'], center: [-73.9855, 40.7580], zoom: 16, label: 'Times Square, New York' },
  { keywords: ['london', 'heathrow', 'gatwick'], center: [-0.1278, 51.5074], zoom: 12, label: 'London, United Kingdom' },
  { keywords: ['paris', 'france', 'eiffel', 'orly', 'cdg'], center: [2.3522, 48.8566], zoom: 12, label: 'Paris, France' },
  { keywords: ['san francisco', 'sfo', 'bay area', 'silicon valley'], center: [-122.4194, 37.7749], zoom: 12, label: 'San Francisco, USA' },
  { keywords: ['los angeles', 'la', 'lax', 'hollywood'], center: [-118.2437, 34.0522], zoom: 12, label: 'Los Angeles, USA' },
  { keywords: ['chicago', 'o\'hare', 'midway'], center: [-87.6298, 41.8781], zoom: 12, label: 'Chicago, USA' },
  { keywords: ['dubai', 'dxb', 'burj'], center: [55.2708, 25.2048], zoom: 12, label: 'Dubai, UAE' },
  { keywords: ['singapore', 'changi'], center: [103.8198, 1.3521], zoom: 12, label: 'Singapore' },
  { keywords: ['hong kong', 'hkg'], center: [114.1694, 22.3193], zoom: 12, label: 'Hong Kong' },
  { keywords: ['sydney', 'australia'], center: [151.2093, -33.8688], zoom: 12, label: 'Sydney, Australia' },
  { keywords: ['delhi', 'new delhi', 'indira gandhi'], center: [77.2090, 28.6139], zoom: 12, label: 'Delhi, India' },
  { keywords: ['mumbai', 'bombay'], center: [72.8777, 19.0760], zoom: 12, label: 'Mumbai, India' },
  { keywords: ['bengaluru', 'bangalore'], center: [77.5946, 12.9716], zoom: 12, label: 'Bengaluru, India' },
  { keywords: ['seoul', 'incheon', 'korea'], center: [126.9780, 37.5665], zoom: 12, label: 'Seoul, South Korea' },
  { keywords: ['rome', 'italy', 'fiumicino'], center: [12.4964, 41.9028], zoom: 12, label: 'Rome, Italy' },
  { keywords: ['berlin', 'germany'], center: [13.4050, 52.5200], zoom: 12, label: 'Berlin, Germany' },
  { keywords: ['amsterdam', 'schiphol', 'netherlands'], center: [4.9041, 52.3676], zoom: 12, label: 'Amsterdam, Netherlands' },
  { keywords: ['cairo', 'egypt'], center: [31.2357, 30.0444], zoom: 12, label: 'Cairo, Egypt' },
  { keywords: ['bangkok', 'thailand'], center: [100.5018, 13.7563], zoom: 12, label: 'Bangkok, Thailand' },
];

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

function sanitizeAiMessageAndExecute(
  rawText: string,
  onAction: (action: AssistantAction) => void
): string {
  const isCode =
    rawText.includes('tool_code') ||
    rawText.includes('default_api.') ||
    rawText.includes('print(') ||
    rawText.includes('discover_places') ||
    rawText.includes('fly_to_location');

  if (!isCode) return rawText;

  // 1. Try parsing discover_places
  const discoverMatch = rawText.match(/discover_places\s*\(([\s\S]*?)\)/);
  if (discoverMatch) {
    const inner = discoverMatch[1];
    const catMatch = inner.match(/category\s*=\s*["']([^"']+)["']/);
    const latMatch = inner.match(/latitude\s*=\s*([-0-9.]+)/);
    const lonMatch = inner.match(/longitude\s*=\s*([-0-9.]+)/);
    const queryMatch = inner.match(/query\s*=\s*["']([\s\S]*?)["']/);

    const category = (catMatch?.[1] as any) || 'stays';
    const lat = latMatch ? parseFloat(latMatch[1]) : undefined;
    const lon = lonMatch ? parseFloat(lonMatch[1]) : undefined;
    const query = queryMatch ? queryMatch[1].replace(/[\r\n]+/g, ' ').trim() : undefined;

    if (typeof lon === 'number' && typeof lat === 'number') {
      onAction({ type: 'fly_to', center: [lon, lat], zoom: 14 });
      onAction({ type: 'discover_places', category, query, center: [lon, lat] });
    } else {
      onAction({ type: 'discover_places', category, query });
    }

    return `Roger: Locating top-rated ${query || category} in this sector...`;
  }

  // 2. Try parsing fly_to_location
  const flyMatch = rawText.match(/fly_to_location\s*\(([\s\S]*?)\)/);
  if (flyMatch) {
    const inner = flyMatch[1];
    const latMatch = inner.match(/latitude\s*=\s*([-0-9.]+)/);
    const lonMatch = inner.match(/longitude\s*=\s*([-0-9.]+)/);
    const zoomMatch = inner.match(/zoom\s*=\s*([0-9.]+)/);

    const lat = latMatch ? parseFloat(latMatch[1]) : undefined;
    const lon = lonMatch ? parseFloat(lonMatch[1]) : undefined;
    const zoom = zoomMatch ? parseFloat(zoomMatch[1]) : 13;

    if (typeof lon === 'number' && typeof lat === 'number') {
      onAction({ type: 'fly_to', center: [lon, lat], zoom });
    }
    return 'Roger: Navigating 3D camera to requested coordinates.';
  }

  // 3. Try parsing set_map_layer_visibility
  const layerMatch = rawText.match(/set_map_layer_visibility\s*\(([\s\S]*?)\)/);
  if (layerMatch) {
    const inner = layerMatch[1];
    const idMatch = inner.match(/layer_id\s*=\s*["']([^"']+)["']/);
    const visMatch = inner.match(/visible\s*=\s*(True|False|true|false)/i);
    if (idMatch) {
      const visible = visMatch ? visMatch[1].toLowerCase() === 'true' : true;
      onAction({ type: 'set_layer_visibility', layer_id: idMatch[1], visible });
      return `Roger: Updated ${idMatch[1]} layer visibility.`;
    }
  }

  return 'Roger: Mission command processed.';
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
  const [activeTravelPlan, setActiveTravelPlan] = useState<TravelPlanResponse | null>(null);
  const [activeDayIndex, setActiveDayIndex] = useState<number>(0);
  const [loadingPlan, setLoadingPlan] = useState<boolean>(false);

  const transcriptRef = useRef<HTMLDivElement>(null);
  const contextRef = useRef(context);
  const preferencesRef = useRef(preferences);
  const onActionRef = useRef(onAction);
  const conversationRef = useRef<any>(null);
  contextRef.current = context;
  preferencesRef.current = preferences;
  onActionRef.current = onAction;

  const fetchPlanForDestination = useCallback(async (destName: string) => {
    setLoadingPlan(true);
    setMessage(`Retrieving live internet travel intelligence for ${destName}...`);
    try {
      const plan = await fetchTravelPlan(
        destName,
        3,
        preferencesRef.current.pace || 'balanced',
        preferencesRef.current.photo_interest || ''
      );
      setActiveTravelPlan(plan);
      setActiveDayIndex(0);
      if (plan.center && plan.center.length === 2) {
        onActionRef.current({ type: 'fly_to', center: plan.center, zoom: plan.zoom || 13 });
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'ai',
          message: plan.spoken_summary,
        },
      ]);
      setMessage(`Generated live internet travel plan for ${plan.destination}!`);
    } catch (err) {
      console.warn('Could not generate travel plan:', err);
      setMessage(`Travel search: ${err instanceof Error ? err.message : 'Could not fetch travel plan'}`);
    } finally {
      setLoadingPlan(false);
    }
  }, []);

  const handleMessage = useCallback((item: AssistantMessage) => {
    if (!item.message.trim()) return;

    let displayMessage = item.message;
    if (item.role === 'ai') {
      displayMessage = sanitizeAiMessageAndExecute(item.message, onActionRef.current);
    }

    setMessages((current) => [...current.slice(-29), { role: item.role, message: displayMessage }]);

    // Intelligent client-side intent interpreter for voice and text commands
    if (item.role === 'user') {
      const lower = item.message.toLowerCase();

      // Check if user is asking for a travel plan or recommendations
      const isAskingTravel =
        lower.includes('plan') ||
        lower.includes('travel') ||
        lower.includes('itinerary') ||
        lower.includes('trip') ||
        lower.includes('visit') ||
        lower.includes('famous') ||
        lower.includes('local') ||
        lower.includes('things to do') ||
        lower.includes('suggest') ||
        lower.includes('recommend');

      if (isAskingTravel) {
        let matchedCity: string | null = null;
        for (const loc of POPULAR_LOCATIONS) {
          if (loc.keywords.some((k) => lower.includes(k))) {
            matchedCity = loc.label.split(',')[0].trim();
            break;
          }
        }
        if (matchedCity) {
          fetchPlanForDestination(matchedCity);
          return;
        }
      }

      // Check for world location navigation commands
      for (const loc of POPULAR_LOCATIONS) {
        if (loc.keywords.some((k) => lower.includes(k))) {
          onActionRef.current({
            type: 'fly_to',
            center: loc.center,
            zoom: loc.zoom,
          });
          setMessage(`Roger: Flying 3D camera to ${loc.label} now.`);

          if (lower.includes('flight') || lower.includes('plane') || lower.includes('aircraft')) {
            onActionRef.current({ type: 'set_layer_visibility', layer_id: 'aircraft-states', visible: true });
          }
          if (lower.includes('stay') || lower.includes('place') || lower.includes('hotel') || lower.includes('motel')) {
            onActionRef.current({ type: 'discover_places', category: 'stays', center: loc.center });
          }
          break;
        }
      }

      // Check for standalone layer toggle keywords
      if (lower.includes('satellite') || lower.includes('orbit')) {
        onActionRef.current({ type: 'set_layer_visibility', layer_id: 'space-satellites', visible: true });
      }
      if (lower.includes('vessel') || lower.includes('ship') || lower.includes('boat') || lower.includes('maritime')) {
        onActionRef.current({ type: 'set_layer_visibility', layer_id: 'maritime-vessels', visible: true });
      }
    }
  }, [fetchPlanForDestination]);

  const conversation = useConversation({
    onMessage: ({ message: text, role, source }) => {
      const isUser = role === 'user' || source === 'user';
      if (!isUser) {
        const isCode = text.includes('tool_code') || text.includes('default_api.') || text.includes('print(');
        if (isCode) {
          try {
            conversationRef.current?.setVolume?.({ volume: 0 });
            setTimeout(() => {
              try {
                conversationRef.current?.setVolume?.({ volume: 1 });
              } catch {}
            }, 3500);
          } catch {}
        }
      }
      handleMessage({ role: isUser ? 'user' : 'ai', message: text });
    },
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
        if (!SAFE_LAYER_IDS.has(args.layer_id) || typeof args.visible !== 'boolean') {
          return JSON.stringify({ success: false, message: 'That map layer action is not allowed.' });
        }
        onActionRef.current({ type: 'set_layer_visibility', layer_id: args.layer_id, visible: args.visible });
        return JSON.stringify({ success: true, message: `${args.layer_id} is now ${args.visible ? 'visible' : 'hidden'}.` });
      },
      fly_to_location: async (args: { longitude: number; latitude: number; zoom?: number }) => {
        if (typeof args.longitude !== 'number' || typeof args.latitude !== 'number') {
          return JSON.stringify({ success: false, message: 'Invalid coordinates' });
        }
        if (args.longitude < -180 || args.longitude > 180 || args.latitude < -90 || args.latitude > 90) {
          return JSON.stringify({ success: false, message: 'Coordinates out of bounds [-180, 180], [-90, 90]' });
        }
        const zoom = typeof args.zoom === 'number' && args.zoom >= 1 && args.zoom <= 20 ? args.zoom : 12;
        onActionRef.current({
          type: 'fly_to',
          center: [args.longitude, args.latitude],
          zoom,
        });
        return JSON.stringify({
          success: true,
          message: `Navigated map to [${args.longitude.toFixed(4)}, ${args.latitude.toFixed(4)}] at zoom ${zoom}.`,
        });
      },
      select_entity: async (args: {
        entity_type: 'aircraft' | 'satellite' | 'vessel' | 'event' | 'hazard' | 'camera';
        id: string;
        name?: string;
        longitude?: number;
        latitude?: number;
      }) => {
        if (!args.id || !args.entity_type) {
          return JSON.stringify({ success: false, message: 'Missing entity_type or id' });
        }
        const coords: [number, number] | undefined =
          typeof args.longitude === 'number' && typeof args.latitude === 'number'
            ? [args.longitude, args.latitude]
            : undefined;

        onActionRef.current({
          type: 'select_entity',
          entity_type: args.entity_type,
          id: String(args.id),
          name: args.name,
          coordinates: coords,
        });
        return JSON.stringify({
          success: true,
          message: `Selected ${args.entity_type} '${args.name || args.id}' and opened detailed dossier drawer.`,
        });
      },
      discover_places: async (args: {
        category?: 'stays' | 'food' | 'scenery' | 'nightlife';
        query?: string;
        longitude?: number;
        latitude?: number;
      }) => {
        const coords: [number, number] | undefined =
          typeof args.longitude === 'number' && typeof args.latitude === 'number'
            ? [args.longitude, args.latitude]
            : undefined;

        onActionRef.current({
          type: 'discover_places',
          category: args.category,
          query: args.query,
          center: coords,
        });
        return JSON.stringify({
          success: true,
          message: `Opened places & stays discovery deck for ${args.category || 'stays'} recommendations.`,
        });
      },
      search_internet_travel_intelligence: async (args: { location: string; query?: string }) => {
        try {
          const plan = await fetchTravelPlan(
            args.location,
            3,
            preferencesRef.current.pace || 'balanced',
            preferencesRef.current.photo_interest || ''
          );
          setActiveTravelPlan(plan);
          setActiveDayIndex(0);
          if (plan.center && plan.center.length === 2) {
            onActionRef.current({ type: 'fly_to', center: plan.center, zoom: plan.zoom || 13 });
          }
          return JSON.stringify({
            status: 'success',
            destination: plan.destination,
            summary: plan.summary,
            spoken_summary: plan.spoken_summary,
            days: plan.days,
            famous_attractions: plan.famous_attractions,
            local_food_recommendations: plan.local_food_recommendations,
            pro_tips: plan.pro_tips,
            instruction: 'Present this concrete travel plan directly to the user. Do NOT ask more questions.',
          });
        } catch (err) {
          return JSON.stringify({ error: err instanceof Error ? err.message : 'Travel search failed' });
        }
      },
      create_travel_itinerary: async (args: { destination: string; days?: number; pace?: string }) => {
        try {
          const plan = await fetchTravelPlan(
            args.destination,
            args.days || 3,
            args.pace || preferencesRef.current.pace || 'balanced',
            preferencesRef.current.photo_interest || ''
          );
          setActiveTravelPlan(plan);
          setActiveDayIndex(0);
          if (plan.center && plan.center.length === 2) {
            onActionRef.current({ type: 'fly_to', center: plan.center, zoom: plan.zoom || 13 });
          }
          return JSON.stringify({
            success: true,
            spoken_summary: plan.spoken_summary,
            plan,
          });
        } catch (err) {
          return JSON.stringify({ error: err instanceof Error ? err.message : 'Itinerary creation failed' });
        }
      },
    },
  });
  conversationRef.current = conversation;

  // Preserve messages and evidence across panel open/close so the user doesn't lose context
  useEffect(() => {
    if (!isOpen && conversation.status !== 'disconnected') {
      void conversation.endSession();
    }
    if (!isOpen) {
      setQuestion('');
    }
  }, [isOpen]);

  // Auto-scroll transcript on new messages
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [messages]);

  const startConversation = async () => {
    setIsStarting(true);
    setMessage('Connecting to your WORLDOS assistant…');
    try {
      const session = await getAssistantSession();
      if (session.signedUrl) {
        await conversation.startSession({ signedUrl: session.signedUrl });
      } else if (session.conversationToken) {
        await conversation.startSession({ conversationToken: session.conversationToken });
      } else {
        throw new Error('No valid session credentials received from server');
      }
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
    if (!text) return;
    handleMessage({ role: 'user', message: text });
    if (conversation.status === 'connected') {
      conversation.sendUserMessage(text);
    }
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

        {/* Quick Travel Destination Pills */}
        <div className="assistant-quick-travel-bar">
          <div className="assistant-quick-travel-header">
            <Globe size={11} color="var(--cy)" />
            <span>INTERNET TRAVEL INTELLIGENCE</span>
          </div>
          <div className="assistant-quick-travel-pills">
            {['Tokyo', 'Paris', 'Kyoto', 'New York', 'Rome', 'London', 'Dubai'].map((city) => (
              <button
                key={city}
                type="button"
                className="assistant-quick-travel-pill"
                onClick={() => fetchPlanForDestination(city)}
                disabled={loadingPlan}
              >
                {city}
              </button>
            ))}
          </div>
        </div>

        {/* Live Internet Travel Plan Deck */}
        {activeTravelPlan && (
          <div className="assistant-travel-plan-deck">
            <div className="assistant-plan-header">
              <div className="assistant-plan-title-block">
                <span className="assistant-plan-badge">LIVE INTERNET PLAN</span>
                <h4>{activeTravelPlan.destination}</h4>
                <span className="assistant-plan-source">Google Places & Wikipedia Live</span>
              </div>
              <button
                type="button"
                className="assistant-plan-close-btn"
                onClick={() => setActiveTravelPlan(null)}
                title="Hide Travel Plan"
              >
                <X size={12} />
              </button>
            </div>

            <p className="assistant-plan-summary">{activeTravelPlan.summary}</p>

            {/* Day Selector Tabs */}
            <div className="assistant-plan-tabs">
              {activeTravelPlan.days.map((day, idx) => (
                <button
                  key={day.day_number}
                  type="button"
                  className={`assistant-plan-tab ${activeDayIndex === idx ? 'active' : ''}`}
                  onClick={() => setActiveDayIndex(idx)}
                >
                  Day {day.day_number}
                </button>
              ))}
            </div>

            {/* Day Activities */}
            {activeTravelPlan.days[activeDayIndex] && (
              <div className="assistant-plan-day-content">
                <div className="assistant-plan-day-theme">
                  <Calendar size={11} color="var(--cy)" />
                  <span>{activeTravelPlan.days[activeDayIndex].theme}</span>
                </div>

                <div className="assistant-plan-activities">
                  {activeTravelPlan.days[activeDayIndex].activities.map((act, i) => (
                    <div className="assistant-plan-activity-item" key={i}>
                      <div className="assistant-act-header">
                        <span className="assistant-act-time">{act.time_of_day}</span>
                        <span className="assistant-act-rating">★ {act.rating?.toFixed(1) || '4.6'}</span>
                      </div>
                      <strong className="assistant-act-title">{act.title}</strong>
                      <p className="assistant-act-desc">{act.description}</p>
                      {typeof act.lat === 'number' && typeof act.lon === 'number' && (
                        <button
                          type="button"
                          className="assistant-act-fly-btn"
                          onClick={() => onActionRef.current({ type: 'fly_to', center: [act.lon, act.lat], zoom: 15 })}
                        >
                          <MapPin size={10} /> Fly to Location
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Authentic Local Food Highlights */}
            {activeTravelPlan.local_food_recommendations && activeTravelPlan.local_food_recommendations.length > 0 && (
              <div className="assistant-plan-food-section">
                <div className="assistant-plan-section-title">
                  <Utensils size={11} color="var(--gold)" />
                  <span>AUTHENTIC LOCAL SPECIALTIES</span>
                </div>
                <div className="assistant-plan-food-list">
                  {activeTravelPlan.local_food_recommendations.slice(0, 3).map((food, idx) => (
                    <div className="assistant-plan-food-item" key={idx}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong style={{ fontSize: '11px', color: 'var(--text-primary)' }}>{food.name}</strong>
                        {food.rating && <span style={{ color: 'var(--gold)', fontSize: '10px' }}>★ {food.rating.toFixed(1)}</span>}
                      </div>
                      <p style={{ margin: '2px 0 0 0', fontSize: '10px', color: 'var(--text-secondary)' }}>{food.summary}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Explore Stays & Places Button */}
            <button
              type="button"
              className="assistant-plan-explore-btn"
              onClick={() => onActionRef.current({ type: 'discover_places', category: 'stays', center: activeTravelPlan.center })}
            >
              <Compass size={12} /> Explore Stays & Sights in 3D
            </button>
          </div>
        )}

        <div className="assistant-transcript-section">
          <div className="assistant-transcript-bar">
            <span className="assistant-transcript-title">TRANSCRIPT</span>
            {messages.length > 0 && (
              <button
                className="assistant-clear-button"
                type="button"
                onClick={() => setMessages([])}
                title="Clear transcript history"
              >
                <Trash2 size={12} /> Clear
              </button>
            )}
          </div>
          <div className="assistant-transcript" aria-live="polite" ref={transcriptRef}>
            {messages.length === 0 ? (
              <p className="assistant-transcript-empty">
                No conversation yet. Connect below or ask a question to start.
              </p>
            ) : (
              messages.map((item, index) => (
                <div className={`assistant-message ${item.role}`} key={`${index}-${item.message.slice(0, 20)}`}>
                  <span className="assistant-sender">{item.role === 'ai' ? 'WORLDOS' : 'You'}</span>
                  <p className="assistant-text">{item.message}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {evidence.length > 0 && (
          <div className="assistant-evidence">
            <strong>Map sources shared with the assistant</strong>
            {evidence.map((item) => (
              <div className="assistant-evidence-item" key={item.evidence_id}>
                <span>{item.source_name}</span>
                <time dateTime={item.retrieved_at}>{new Date(item.retrieved_at).toLocaleString()}</time>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={sendQuestion}>
          <label htmlFor="assistant-question">Ask by text</label>
          <textarea
            id="assistant-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={2}
            maxLength={1200}
            placeholder="Ask for a travel plan (e.g. Plan a 3-day trip to Tokyo), or speak aloud..."
          />
          <div className="assistant-controls">
            {conversation.status === 'connected' ? (
              <>
                <button className="assistant-control-button" type="button" onClick={() => conversation.setMuted(!conversation.isMuted)}><Mic size={14} /> {conversation.isMuted ? 'Unmute' : 'Mute'}</button>
                <button className="assistant-control-button" type="button" onClick={() => void conversation.endSession()}><PhoneOff size={14} /> End voice</button>
                <button className="assistant-control-button primary" type="submit" disabled={!question.trim()}><Send size={14} /> Send</button>
              </>
            ) : (
              <>
                <button className="assistant-control-button primary" type="button" onClick={() => void startConversation()} disabled={isStarting}><Mic size={14} /> {isStarting ? 'Connecting…' : 'Start voice'}</button>
                <button className="assistant-control-button" type="submit" disabled={!question.trim()}><Send size={14} /> Send Text</button>
              </>
            )}
            <span><Volume2 size={14} /> {conversation.status}</span>
          </div>
        </form>
        <div className="assistant-status" aria-live="polite">{message}</div>
      </div>
    </section>
  );
};
