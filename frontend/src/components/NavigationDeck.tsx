import React, { useState, useEffect } from 'react';
import {
  Navigation,
  Plane,
  Car,
  MapPin,
  Clock,
  Compass,
  ArrowRight,
  ArrowLeftRight,
  CornerUpRight,
  CornerUpLeft,
  ArrowUp,
  GitMerge,
  RotateCw,
  CheckCircle2,
  X,
  Search,
  Loader2,
  Globe2,
  Eye,
  Trash2,
  Building,
  Sparkles,
  LocateFixed,
  Play,
  Radio,
} from 'lucide-react';
import {
  FlightPlansResponse,
  InboundFlightPlan,
  RoadRouteResponse,
  RoadRouteStep,
  fetchInboundFlightPlans,
  fetchRoadRoute,
  geocodeLocation,
} from '../api';

interface NavigationDeckProps {
  isOpen: boolean;
  onClose: () => void;
  activeRoadRoute: RoadRouteResponse | null;
  onSelectRoadRoute: (route: RoadRouteResponse | null) => void;
  activeFlightPlan: InboundFlightPlan | null;
  onSelectFlightPlan: (flight: InboundFlightPlan | null) => void;
  onFlyToCoordinates: (coords: [number, number], zoom?: number) => void;
  initialDestination?: string;
  currentCenter?: [number, number]; // [lon, lat]
  onStartNavigation?: (mode: 'simulate' | 'gps') => void;
  userNavActive?: boolean;
}

const DESTINATION_PRESETS = [
  { name: 'Tokyo', lat: 35.6762, lon: 139.6503, airport: 'Haneda Airport (HND)', aptCoords: [139.7798, 35.5494] as [number, number], sight: 'Sensō-ji Temple', sightCoords: [139.7967, 35.7148] as [number, number] },
  { name: 'Paris', lat: 48.8566, lon: 2.3522, airport: 'Charles de Gaulle (CDG)', aptCoords: [2.5479, 49.0097] as [number, number], sight: 'Eiffel Tower', sightCoords: [2.2945, 48.8584] as [number, number] },
  { name: 'Rome', lat: 41.9028, lon: 12.4964, airport: 'Fiumicino Airport (FCO)', aptCoords: [12.2462, 41.7999] as [number, number], sight: 'Colosseum', sightCoords: [12.4922, 41.8902] as [number, number] },
  { name: 'New York', lat: 40.7128, lon: -74.0060, airport: 'JFK International (JFK)', aptCoords: [-73.7781, 40.6413] as [number, number], sight: 'Times Square', sightCoords: [-73.9851, 40.7580] as [number, number] },
  { name: 'London', lat: 51.5074, lon: -0.1278, airport: 'Heathrow Airport (LHR)', aptCoords: [-0.4543, 51.4700] as [number, number], sight: 'Tower Bridge', sightCoords: [-0.0754, 51.5055] as [number, number] },
  { name: 'Dubai', lat: 25.2048, lon: 55.2708, airport: 'Dubai International (DXB)', aptCoords: [55.3644, 25.2532] as [number, number], sight: 'Burj Khalifa', sightCoords: [55.2744, 25.1972] as [number, number] },
  { name: 'Sydney', lat: -33.8688, lon: 151.2093, airport: 'Kingsford Smith (SYD)', aptCoords: [151.1772, -33.9399] as [number, number], sight: 'Sydney Opera House', sightCoords: [151.2153, -33.8568] as [number, number] },
  { name: 'Kyoto', lat: 35.0116, lon: 135.7681, airport: 'Kansai Airport (KIX)', aptCoords: [135.2442, 34.4347] as [number, number], sight: 'Fushimi Inari Taisha', sightCoords: [135.7727, 34.9671] as [number, number] },
];

const ORIGIN_PRESETS = [
  { code: 'ALL', label: 'Any Origin' },
  { code: 'DEL', label: 'DEL (Delhi)' },
  { code: 'JFK', label: 'JFK (New York)' },
  { code: 'LHR', label: 'LHR (London)' },
  { code: 'DXB', label: 'DXB (Dubai)' },
  { code: 'SIN', label: 'SIN (Singapore)' },
  { code: 'SYD', label: 'SYD (Sydney)' },
  { code: 'BOM', label: 'BOM (Mumbai)' },
  { code: 'SFO', label: 'SFO (San Francisco)' },
];

const DESTINATION_AIRPORT_PRESETS = [
  { code: 'HND', label: 'HND (Tokyo)' },
  { code: 'CDG', label: 'CDG (Paris)' },
  { code: 'FCO', label: 'FCO (Rome)' },
  { code: 'JFK', label: 'JFK (New York)' },
  { code: 'LHR', label: 'LHR (London)' },
  { code: 'DXB', label: 'DXB (Dubai)' },
  { code: 'SYD', label: 'SYD (Sydney)' },
];

export const ROAD_CORRIDOR_PRESETS = [
  {
    city: 'Tokyo',
    country: 'Japan',
    originLabel: 'Haneda Airport (HND)',
    originCoords: [139.7798, 35.5494] as [number, number],
    destLabel: 'Sensō-ji Temple',
    destCoords: [139.7967, 35.7148] as [number, number],
  },
  {
    city: 'Paris',
    country: 'France',
    originLabel: 'Charles de Gaulle (CDG)',
    originCoords: [2.5479, 49.0097] as [number, number],
    destLabel: 'Eiffel Tower',
    destCoords: [2.2945, 48.8584] as [number, number],
  },
  {
    city: 'Rome',
    country: 'Italy',
    originLabel: 'Fiumicino Airport (FCO)',
    originCoords: [12.2462, 41.7999] as [number, number],
    destLabel: 'Colosseum',
    destCoords: [12.4922, 41.8902] as [number, number],
  },
  {
    city: 'New York',
    country: 'USA',
    originLabel: 'JFK International (JFK)',
    originCoords: [-73.7781, 40.6413] as [number, number],
    destLabel: 'Times Square',
    destCoords: [-73.9851, 40.7580] as [number, number],
  },
  {
    city: 'London',
    country: 'UK',
    originLabel: 'Heathrow Airport (LHR)',
    originCoords: [-0.4543, 51.4700] as [number, number],
    destLabel: 'Tower Bridge',
    destCoords: [-0.0754, 51.5055] as [number, number],
  },
  {
    city: 'Dubai',
    country: 'UAE',
    originLabel: 'Dubai International (DXB)',
    originCoords: [55.3644, 25.2532] as [number, number],
    destLabel: 'Burj Khalifa',
    destCoords: [55.2744, 25.1972] as [number, number],
  },
  {
    city: 'Sydney',
    country: 'Australia',
    originLabel: 'Kingsford Smith (SYD)',
    originCoords: [151.1772, -33.9399] as [number, number],
    destLabel: 'Sydney Opera House',
    destCoords: [151.2153, -33.8568] as [number, number],
  },
  {
    city: 'Delhi',
    country: 'India',
    originLabel: 'Indira Gandhi Intl (DEL)',
    originCoords: [77.1000, 28.5562] as [number, number],
    destLabel: 'India Gate',
    destCoords: [77.2295, 28.6129] as [number, number],
  },
  {
    city: 'Kyoto',
    country: 'Japan',
    originLabel: 'Kansai Airport (KIX)',
    originCoords: [135.2442, 34.4347] as [number, number],
    destLabel: 'Fushimi Inari Taisha',
    destCoords: [135.7727, 34.9671] as [number, number],
  },
  {
    city: 'Cross-Europe',
    country: 'Europe',
    originLabel: 'Paris Center',
    originCoords: [2.3522, 48.8566] as [number, number],
    destLabel: 'Berlin Center',
    destCoords: [13.4050, 52.5200] as [number, number],
  },
];

export const NavigationDeck: React.FC<NavigationDeckProps> = ({
  isOpen,
  onClose,
  activeRoadRoute,
  onSelectRoadRoute,
  activeFlightPlan,
  onSelectFlightPlan,
  onFlyToCoordinates,
  initialDestination = 'Tokyo',
  currentCenter,
  onStartNavigation,
  userNavActive = false,
}) => {
  const [activeTab, setActiveTab] = useState<'flights' | 'road'>('flights');

  // Flight Plan state
  const [flightOrigin, setFlightOrigin] = useState<string>('ALL');
  const [flightDestination, setFlightDestination] = useState<string>(initialDestination);
  const [flightPlansResponse, setFlightPlansResponse] = useState<FlightPlansResponse | null>(null);
  const [selectedCountryFilter, setSelectedCountryFilter] = useState<string>('ALL');
  const [isFlightLoading, setIsFlightLoading] = useState<boolean>(false);
  const [flightError, setFlightError] = useState<string | null>(null);

  // Road Navigation state
  const defaultCity = DESTINATION_PRESETS[0];
  const [originName, setOriginName] = useState<string>(defaultCity.airport);
  const [originCoords, setOriginCoords] = useState<[number, number]>(defaultCity.aptCoords);
  const [destName, setDestName] = useState<string>(defaultCity.sight);
  const [destCoords, setDestCoords] = useState<[number, number]>(defaultCity.sightCoords);
  const [isRoadLoading, setIsRoadLoading] = useState<boolean>(false);
  const [roadError, setRoadError] = useState<string | null>(null);
  const [activeStepIndex, setActiveStepIndex] = useState<number | null>(null);
  const [isLocatingUser, setIsLocatingUser] = useState<boolean>(false);

  // Request browser GPS position and set as departure point
  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser.');
      return;
    }
    setIsLocatingUser(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        setOriginCoords([lon, lat]);
        setOriginName('My Current Location');
        try {
          const geo = await geocodeLocation(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
          if (geo && (geo.name || geo.formatted_address)) {
            setOriginName(`My Location (${geo.name || geo.formatted_address.split(',')[0]})`);
          }
        } catch (_) {}
        setIsLocatingUser(false);
      },
      (err) => {
        setIsLocatingUser(false);
        alert(`Could not acquire GPS position: ${err.message}`);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  // Sync initial destination when it changes
  useEffect(() => {
    if (initialDestination) {
      setFlightDestination(initialDestination);
      const matched = DESTINATION_PRESETS.find(
        (p) => p.name.toLowerCase() === initialDestination.toLowerCase()
      );
      if (matched) {
        setOriginName(matched.airport);
        setOriginCoords(matched.aptCoords);
        setDestName(matched.sight);
        setDestCoords(matched.sightCoords);
      }
    }
  }, [initialDestination]);

  // Load flight plans on mount or when destination changes
  useEffect(() => {
    if (isOpen && flightDestination) {
      handleLoadFlightPlans(flightDestination, flightOrigin);
    }
  }, [isOpen, flightDestination]);

  const handleLoadFlightPlans = async (targetDest: string, targetOrig?: string) => {
    setIsFlightLoading(true);
    setFlightError(null);
    const origVal = targetOrig !== undefined ? targetOrig : flightOrigin;
    try {
      const resp = await fetchInboundFlightPlans(targetDest, origVal);
      setFlightPlansResponse(resp);
      setSelectedCountryFilter('ALL');
    } catch (err: any) {
      setFlightError(err.message || 'Failed to fetch flight plans');
    } finally {
      setIsFlightLoading(false);
    }
  };

  const handleSwapAirports = () => {
    const curOrigin = flightOrigin && flightOrigin !== 'ALL' ? flightOrigin : 'DEL';
    const curDest = flightDestination;
    setFlightOrigin(curDest);
    setFlightDestination(curOrigin);
    handleLoadFlightPlans(curOrigin, curDest);
  };

  const handleSelectOriginPreset = (code: string) => {
    setFlightOrigin(code);
    handleLoadFlightPlans(flightDestination, code);
  };

  const handleSelectDestPreset = (code: string) => {
    setFlightDestination(code);
    handleLoadFlightPlans(code, flightOrigin);
  };

  const handleCalculateRoadRoute = async (
    customOrigCoords?: [number, number],
    customDestCoords?: [number, number],
    customOrigName?: string,
    customDestName?: string
  ) => {
    setIsRoadLoading(true);
    setRoadError(null);

    let useOrigName = customOrigName !== undefined ? customOrigName : originName;
    let useDestName = customDestName !== undefined ? customDestName : destName;
    let useOrigCoords: [number, number] = customOrigCoords
      ? [customOrigCoords[0], customOrigCoords[1]]
      : [originCoords[0], originCoords[1]];
    let useDestCoords: [number, number] = customDestCoords
      ? [customDestCoords[0], customDestCoords[1]]
      : [destCoords[0], destCoords[1]];

    // 1. Check if name matches any of our known road corridor presets
    const matchedOrig = ROAD_CORRIDOR_PRESETS.find(
      (p) =>
        p.city.toLowerCase() === useOrigName.toLowerCase() ||
        p.originLabel.toLowerCase().includes(useOrigName.toLowerCase())
    );
    if (matchedOrig && !customOrigCoords) {
      useOrigCoords = matchedOrig.originCoords;
      setOriginCoords(useOrigCoords);
    }

    const matchedDest = ROAD_CORRIDOR_PRESETS.find(
      (p) =>
        p.city.toLowerCase() === useDestName.toLowerCase() ||
        p.destLabel.toLowerCase().includes(useDestName.toLowerCase())
    );
    if (matchedDest && !customDestCoords) {
      useDestCoords = matchedDest.destCoords;
      setDestCoords(useDestCoords);
    }

    // 2. Geocode custom names if not matching preset
    if (!matchedOrig && useOrigName.trim().length >= 2) {
      try {
        const geoOrig = await geocodeLocation(useOrigName);
        if (geoOrig) {
          useOrigCoords = [geoOrig.longitude, geoOrig.latitude];
          setOriginCoords(useOrigCoords);
        }
      } catch (_) {}
    }

    if (!matchedDest && useDestName.trim().length >= 2) {
      try {
        const geoDest = await geocodeLocation(useDestName);
        if (geoDest) {
          useDestCoords = [geoDest.longitude, geoDest.latitude];
          setDestCoords(useDestCoords);
        }
      } catch (_) {}
    }

    try {
      const resp = await fetchRoadRoute(
        useOrigCoords[1], // originLat
        useOrigCoords[0], // originLon
        useDestCoords[1],   // destLat
        useDestCoords[0],   // destLon
        useOrigName,
        useDestName
      );

      // Sync state with resolved coordinates
      if (resp.origin_coords && resp.origin_coords.length === 2) {
        setOriginCoords([resp.origin_coords[0], resp.origin_coords[1]]);
      }
      if (resp.destination_coords && resp.destination_coords.length === 2) {
        setDestCoords([resp.destination_coords[0], resp.destination_coords[1]]);
      }

      onSelectRoadRoute(resp);
      // Fly camera to midpoint of road route
      const midLon = (resp.origin_coords[0] + resp.destination_coords[0]) / 2.0;
      const midLat = (resp.origin_coords[1] + resp.destination_coords[1]) / 2.0;
      const zoomLevel = resp.total_distance_km > 300 ? 7 : resp.total_distance_km > 50 ? 10 : 13;
      onFlyToCoordinates([midLon, midLat], zoomLevel);
    } catch (err: any) {
      setRoadError(err.message || 'Failed to calculate road route');
    } finally {
      setIsRoadLoading(false);
    }
  };

  const handleSelectCityPreset = (city: typeof DESTINATION_PRESETS[0]) => {
    setFlightDestination(city.name);
    setOriginName(city.airport);
    setOriginCoords(city.aptCoords);
    setDestName(city.sight);
    setDestCoords(city.sightCoords);
    handleLoadFlightPlans(city.name, flightOrigin);
    if (activeTab === 'road') {
      handleCalculateRoadRoute(city.aptCoords, city.sightCoords, city.airport, city.sight);
    }
  };

  const handleSelectRoadPreset = (preset: typeof ROAD_CORRIDOR_PRESETS[0]) => {
    setOriginName(preset.originLabel);
    setOriginCoords(preset.originCoords);
    setDestName(preset.destLabel);
    setDestCoords(preset.destCoords);
    handleCalculateRoadRoute(preset.originCoords, preset.destCoords, preset.originLabel, preset.destLabel);
  };

  const handleSwapRoadEndpoints = () => {
    const tempName = originName;
    const tempCoords = originCoords;
    setOriginName(destName);
    setOriginCoords(destCoords);
    setDestName(tempName);
    setDestCoords(tempCoords);
  };

  const handleFlyToFlightArc = (flight: InboundFlightPlan) => {
    onSelectFlightPlan(flight);
    // Midpoint between origin and destination
    const midLon = (flight.origin_airport.longitude + flight.destination_airport.longitude) / 2.0;
    const midLat = (flight.origin_airport.latitude + flight.destination_airport.latitude) / 2.0;
    onFlyToCoordinates([midLon, midLat], 4);
  };

  const handleFlyToStep = (step: RoadRouteStep, index: number) => {
    setActiveStepIndex(index);
    onFlyToCoordinates(step.coordinates, 16);
  };

  if (!isOpen) return null;

  // Filter flights by country if selected
  const visibleFlights = (flightPlansResponse?.flights || []).filter((f) => {
    if (selectedCountryFilter === 'ALL') return true;
    return f.origin_country.toLowerCase() === selectedCountryFilter.toLowerCase();
  });

  const getManeuverIcon = (type: string) => {
    switch (type) {
      case 'depart':
        return <Compass size={14} className="text-cyan-400" />;
      case 'turn_right':
      case 'sharp_right':
        return <CornerUpRight size={14} className="text-amber-400" />;
      case 'turn_left':
      case 'sharp_left':
        return <CornerUpLeft size={14} className="text-amber-400" />;
      case 'continue':
        return <ArrowUp size={14} className="text-emerald-400" />;
      case 'merge':
      case 'ramp':
        return <GitMerge size={14} className="text-sky-400" />;
      case 'roundabout':
        return <RotateCw size={14} className="text-purple-400" />;
      case 'arrive':
        return <CheckCircle2 size={14} className="text-emerald-400" />;
      default:
        return <ArrowRight size={14} className="text-gray-400" />;
    }
  };

  return (
    <div className="navigation-deck">
      {/* Header */}
      <div className="navigation-deck-header">
        <div className="navigation-deck-title-group">
          <div className="navigation-deck-icon-badge">
            <Navigation size={18} />
          </div>
          <div>
            <h2 className="navigation-deck-title">WORLD NAVIGATION &amp; TRANSIT</h2>
            <p className="navigation-deck-subtitle">
              Inbound International Flight Plans • Short Road Route Navigation
            </p>
          </div>
        </div>
        <button
          className="navigation-deck-close-btn"
          onClick={onClose}
          title="Close Navigation Deck"
        >
          <X size={18} />
        </button>
      </div>

      {/* Mode Tabs */}
      <div className="navigation-deck-tabs">
        <button
          className={`nav-tab-btn ${activeTab === 'flights' ? 'active' : ''}`}
          onClick={() => setActiveTab('flights')}
        >
          <Plane size={15} />
          <span>Inbound Flights ({flightPlansResponse?.total_inbound_flights || 0})</span>
        </button>
        <button
          className={`nav-tab-btn ${activeTab === 'road' ? 'active' : ''}`}
          onClick={() => setActiveTab('road')}
        >
          <Car size={15} />
          <span>Road Navigation {activeRoadRoute ? `(${activeRoadRoute.total_distance_formatted})` : ''}</span>
        </button>
      </div>

      {/* Preset Destinations Bar */}
      <div className="navigation-presets-bar">
        <span className="presets-label">DESTINATIONS:</span>
        <div className="presets-scroll">
          {DESTINATION_PRESETS.map((city) => (
            <button
              key={city.name}
              className={`preset-pill ${
                flightDestination.toLowerCase() === city.name.toLowerCase() ? 'active' : ''
              }`}
              onClick={() => handleSelectCityPreset(city)}
            >
              {city.name}
            </button>
          ))}
        </div>
      </div>

      {/* TAB 1: INBOUND FLIGHT PLANS */}
      {activeTab === 'flights' && (
        <div className="navigation-tab-content">
          {/* Dual Origin & Destiny Selector */}
          <div className="nav-filter-section">
            <div className="nav-dual-inputs-wrap">
              {/* Departure (Origin) Input */}
              <div className="nav-endpoint-block">
                <div className="nav-endpoint-header">
                  <span className="nav-field-label">1. DEPARTURE AIRPORT (ORIGIN)</span>
                  <span className="text-[10px] text-gray-400">Select Hub or "Any Origin"</span>
                </div>
                <div className="nav-input-row">
                  <div className="nav-input-wrap flex-1">
                    <Search size={14} className="nav-input-icon" />
                    <input
                      type="text"
                      placeholder="Origin code or city (e.g. DEL, JFK, LHR, or ALL)..."
                      value={flightOrigin === 'ALL' ? '' : flightOrigin}
                      onChange={(e) => setFlightOrigin(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleLoadFlightPlans(flightDestination, flightOrigin)}
                      className="nav-input"
                    />
                  </div>
                </div>
                <div className="nav-quick-pills-row">
                  {ORIGIN_PRESETS.map((p) => (
                    <button
                      key={p.code}
                      className={`nav-quick-pill ${
                        flightOrigin === p.code || (p.code === 'ALL' && (!flightOrigin || flightOrigin === 'ALL'))
                          ? 'active'
                          : ''
                      }`}
                      onClick={() => handleSelectOriginPreset(p.code)}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Swap Origin & Destiny Button */}
              <div className="nav-swap-divider">
                <button
                  className="nav-swap-btn"
                  onClick={handleSwapAirports}
                  title="Swap Origin and Destiny Airports"
                >
                  <ArrowLeftRight size={12} />
                  <span>⇄ Swap Origin &amp; Destiny</span>
                </button>
              </div>

              {/* Arrival (Destiny) Input */}
              <div className="nav-endpoint-block">
                <div className="nav-endpoint-header">
                  <span className="nav-field-label">2. DESTINY AIRPORT (DESTINATION)</span>
                  <span className="text-[10px] text-emerald-400">Target Hub</span>
                </div>
                <div className="nav-input-row">
                  <div className="nav-input-wrap flex-1">
                    <Search size={14} className="nav-input-icon" />
                    <input
                      type="text"
                      placeholder="Destiny city or hub (e.g. Tokyo, HND, Paris, CDG)..."
                      value={flightDestination}
                      onChange={(e) => setFlightDestination(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleLoadFlightPlans(flightDestination, flightOrigin)}
                      className="nav-input"
                    />
                  </div>
                  <button
                    className="nav-action-btn primary"
                    onClick={() => handleLoadFlightPlans(flightDestination, flightOrigin)}
                    disabled={isFlightLoading}
                  >
                    {isFlightLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                    <span>Find Flights</span>
                  </button>
                </div>
                <div className="nav-quick-pills-row">
                  {DESTINATION_AIRPORT_PRESETS.map((p) => (
                    <button
                      key={p.code}
                      className={`nav-quick-pill ${
                        flightDestination.toLowerCase() === p.code.toLowerCase() ? 'active' : ''
                      }`}
                      onClick={() => handleSelectDestPreset(p.code)}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Corridor or Inbound Summary */}
            {flightPlansResponse && (
              <div className="corridor-summary-banner">
                <span className="corridor-summary-title">
                  {flightOrigin && flightOrigin !== 'ALL'
                    ? `FLIGHT CORRIDOR: ${flightPlansResponse.destination}`
                    : `INBOUND TO ${flightPlansResponse.destination_airport.iata} (${flightPlansResponse.destination_airport.city})`}
                </span>
                <span className="text-cyan-400 font-semibold">
                  {flightPlansResponse.total_inbound_flights}{' '}
                  {flightOrigin && flightOrigin !== 'ALL' ? 'Options' : 'Global Inbound Routes'}
                </span>
              </div>
            )}

            {/* Country Filter Pills (shown when viewing All Origins) */}
            {(!flightOrigin || flightOrigin === 'ALL') &&
              flightPlansResponse &&
              flightPlansResponse.origin_countries.length > 1 && (
                <div className="origin-country-filter-wrap">
                  <span className="filter-label">FROM COUNTRY:</span>
                  <div className="country-pills-row">
                    <button
                      className={`country-pill ${selectedCountryFilter === 'ALL' ? 'active' : ''}`}
                      onClick={() => setSelectedCountryFilter('ALL')}
                    >
                      All Countries ({flightPlansResponse.flights.length})
                    </button>
                    {flightPlansResponse.origin_countries.map((c) => (
                      <button
                        key={c}
                        className={`country-pill ${selectedCountryFilter === c ? 'active' : ''}`}
                        onClick={() => setSelectedCountryFilter(c)}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              )}
          </div>

          {/* Active Flight Plan Banner */}
          {activeFlightPlan && (
            <div className="active-flight-banner">
              <div className="active-banner-info">
                <Plane size={15} className="text-cyan-400" />
                <span>
                  Active on 3D Globe: <strong>{activeFlightPlan.flight_number}</strong> ({activeFlightPlan.airline})
                </span>
              </div>
              <button
                className="banner-clear-btn"
                onClick={() => onSelectFlightPlan(null)}
                title="Clear 3D flight corridor"
              >
                <X size={13} />
              </button>
            </div>
          )}

          {/* Error Message */}
          {flightError && <div className="nav-error-banner">{flightError}</div>}

          {/* Flights List */}
          <div className="nav-cards-list">
            {isFlightLoading ? (
              <div className="nav-loading-state">
                <Loader2 size={24} className="animate-spin text-cyan-400" />
                <p>Analyzing global air routes into {flightDestination}...</p>
              </div>
            ) : visibleFlights.length === 0 ? (
              <div className="nav-empty-state">
                <Plane size={28} className="text-gray-500" />
                <p>No inbound flights found for this filter.</p>
              </div>
            ) : (
              visibleFlights.map((flight) => {
                const isActive = activeFlightPlan?.flight_id === flight.flight_id;
                return (
                  <div
                    key={flight.flight_id}
                    className={`flight-plan-card ${isActive ? 'active-corridor' : ''}`}
                  >
                    <div className="flight-card-header">
                      <div className="flight-airline-group">
                        <span className="airline-badge">{flight.airline_code}</span>
                        <div>
                          <strong className="flight-number">{flight.flight_number}</strong>
                          <span className="flight-airline-name">{flight.airline}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className={flight.is_direct ? 'flight-direct-badge' : 'flight-connecting-badge'}>
                          {flight.is_direct ? 'DIRECT' : '1-STOP'}
                        </span>
                        <span className="flight-frequency-badge">{flight.frequency}</span>
                      </div>
                    </div>

                    {/* Origin to Destination Flow */}
                    <div className="flight-route-flow">
                      <div className="flow-airport">
                        <span className="flow-iata">{flight.origin_airport.iata}</span>
                        <span className="flow-city">{flight.origin_city}</span>
                        <span className="flow-country">{flight.origin_country}</span>
                      </div>

                      <div className="flow-middle">
                        <span className="flow-duration">{flight.duration_formatted}</span>
                        <div className="flow-line">
                          <Plane size={12} className="flow-plane-icon" />
                        </div>
                        <span className="flow-dist">{flight.distance_km.toLocaleString()} km</span>
                      </div>

                      <div className="flow-airport text-right">
                        <span className="flow-iata text-emerald-400">
                          {flight.destination_airport.iata}
                        </span>
                        <span className="flow-city">{flight.destination_city}</span>
                        <span className="flow-country">{flight.destination_airport.country}</span>
                      </div>
                    </div>

                    {/* Flight Specs & Schedule */}
                    <div className="flight-specs-row">
                      <div className="flight-spec-item">
                        <span className="spec-label">AIRCRAFT:</span>
                        <span className="spec-val">{flight.aircraft_type}</span>
                      </div>
                      <div className="flight-spec-item">
                        <span className="spec-label">SCHEDULE:</span>
                        <span className="spec-val">{flight.departure_time_schedule}</span>
                      </div>
                    </div>

                    {/* Action */}
                    <div className="flight-card-footer">
                      <button
                        className={`flight-view-globe-btn ${isActive ? 'active' : ''}`}
                        onClick={() => handleFlyToFlightArc(flight)}
                      >
                        <Globe2 size={14} />
                        <span>{isActive ? 'Showing on 3D Globe' : 'Show 3D Flight Corridor'}</span>
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* TAB 2: ROAD ROUTE SHORT NAVIGATION SYSTEM */}
      {activeTab === 'road' && (
        <div className="navigation-tab-content">
          {/* Preset City Corridors Bar */}
          <div className="navigation-presets-bar">
            <span className="presets-label">CITY CORRIDORS:</span>
            <div className="presets-scroll">
              {ROAD_CORRIDOR_PRESETS.map((p) => {
                const isActive =
                  originName.toLowerCase().includes(p.city.toLowerCase()) ||
                  destName.toLowerCase().includes(p.city.toLowerCase());
                return (
                  <button
                    key={p.city}
                    className={`preset-pill ${isActive ? 'active' : ''}`}
                    onClick={() => handleSelectRoadPreset(p)}
                  >
                    {p.city}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Origin & Destination Config */}
          <div className="road-route-builder">
            <div className="road-input-block">
              <div className="road-input-label-row">
                <label className="road-input-label">
                  <span className="dot origin-dot" />
                  <span>START POINT (Airport, Hotel, or Address)</span>
                </label>
                <button
                  type="button"
                  className="use-gps-btn"
                  onClick={handleUseCurrentLocation}
                  disabled={isLocatingUser}
                  title="Use My Current GPS Location"
                >
                  {isLocatingUser ? (
                    <Loader2 size={11} className="animate-spin text-cyan-400" />
                  ) : (
                    <LocateFixed size={11} className="text-cyan-400" />
                  )}
                  <span>{isLocatingUser ? 'Locating...' : 'My Location'}</span>
                </button>
              </div>
              <div className="road-input-row">
                <input
                  type="text"
                  value={originName}
                  onChange={(e) => setOriginName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCalculateRoadRoute()}
                  placeholder="Departure airport, address, or landmark..."
                  className="road-text-input"
                />
              </div>
              <div className="road-coords-badge">
                <MapPin size={10} className="text-cyan-400" />
                <span>
                  {originCoords[1].toFixed(4)}°N, {originCoords[0].toFixed(4)}°E
                </span>
              </div>
            </div>

            <div className="road-swap-row">
              <button
                className="road-swap-btn"
                onClick={handleSwapRoadEndpoints}
                title="Swap Start and Destination"
              >
                <ArrowLeftRight size={14} />
                <span>⇄ Swap</span>
              </button>
            </div>

            <div className="road-input-block">
              <label className="road-input-label">
                <span className="dot dest-dot" />
                <span>DESTINATION (Place, Attraction, or City)</span>
              </label>
              <div className="road-input-row">
                <input
                  type="text"
                  value={destName}
                  onChange={(e) => setDestName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCalculateRoadRoute()}
                  placeholder="Attraction, restaurant, or city..."
                  className="road-text-input"
                />
              </div>
              <div className="road-coords-badge">
                <MapPin size={10} className="text-emerald-400" />
                <span>
                  {destCoords[1].toFixed(4)}°N, {destCoords[0].toFixed(4)}°E
                </span>
              </div>
            </div>

            <button
              className="nav-action-btn primary full-width mt-2"
              onClick={() => handleCalculateRoadRoute()}
              disabled={isRoadLoading}
            >
              {isRoadLoading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Navigation size={16} />
              )}
              <span>Calculate Road Route</span>
            </button>
          </div>

          {/* Road Error */}
          {roadError && <div className="nav-error-banner">{roadError}</div>}

          {/* Active Road Route Summary */}
          {activeRoadRoute && (
            <div className="road-route-summary-card">
              <div className="road-summary-header">
                <div>
                  <div className="road-metrics-row">
                    <span className="road-metric-big text-cyan-400">
                      {activeRoadRoute.total_distance_formatted}
                    </span>
                    <span className="road-metric-divider">•</span>
                    <span className="road-metric-big text-emerald-400">
                      {activeRoadRoute.total_duration_formatted}
                    </span>
                  </div>
                  <p className="road-summary-roads">{activeRoadRoute.summary}</p>
                </div>
                <button
                  className="road-clear-btn"
                  onClick={() => onSelectRoadRoute(null)}
                  title="Clear road route"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Start Live Navigation / Driving Mode Action */}
              <div className="nav-drive-mode-actions">
                <button
                  className="nav-start-drive-btn primary"
                  onClick={() => onStartNavigation?.('simulate')}
                  title="Start 3D Turn-by-Turn Navigation with simulated car driving along route"
                >
                  <Play size={15} />
                  <span>Simulate Drive (3D Follow)</span>
                </button>
                <button
                  className="nav-start-drive-btn secondary"
                  onClick={() => onStartNavigation?.('gps')}
                  title="Track real-time device GPS coordinates along this route"
                >
                  <Radio size={14} className="text-emerald-400" />
                  <span>Live GPS Track</span>
                </button>
              </div>

              {/* Turn-by-Turn Navigation Feed */}
              <div className="turn-by-turn-section">
                <div className="turn-by-turn-title">
                  <span>SHORT NAVIGATION MANEUVERS</span>
                  <span className="turn-count">{activeRoadRoute.steps.length} turns</span>
                </div>

                <div className="turn-steps-list">
                  {activeRoadRoute.steps.map((step, idx) => {
                    const isSelected = activeStepIndex === idx;
                    return (
                      <div
                        key={step.step_number}
                        className={`turn-step-item ${isSelected ? 'selected' : ''}`}
                        onClick={() => handleFlyToStep(step, idx)}
                      >
                        <div className="step-num-badge">{step.step_number}</div>
                        <div className="step-icon-badge">
                          {getManeuverIcon(step.maneuver_type)}
                        </div>
                        <div className="step-details">
                          <p className="step-instruction">{step.instruction}</p>
                          <span className="step-distance">
                            {step.distance_formatted}
                            {step.duration_formatted ? ` • ${step.duration_formatted}` : ''}
                          </span>
                        </div>
                        <button
                          className="step-fly-btn"
                          title="Fly 3D Camera to this turn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleFlyToStep(step, idx);
                          }}
                        >
                          <Eye size={13} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

