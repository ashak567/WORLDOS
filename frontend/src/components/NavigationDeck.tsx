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
} from 'lucide-react';
import {
  FlightPlansResponse,
  InboundFlightPlan,
  RoadRouteResponse,
  RoadRouteStep,
  fetchInboundFlightPlans,
  fetchRoadRoute,
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
}) => {
  const [activeTab, setActiveTab] = useState<'flights' | 'road'>('flights');

  // Flight Plan state
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
      handleLoadFlightPlans(flightDestination);
    }
  }, [isOpen, flightDestination]);

  const handleLoadFlightPlans = async (targetDest: string) => {
    setIsFlightLoading(true);
    setFlightError(null);
    try {
      const resp = await fetchInboundFlightPlans(targetDest);
      setFlightPlansResponse(resp);
      setSelectedCountryFilter('ALL');
    } catch (err: any) {
      setFlightError(err.message || 'Failed to fetch flight plans');
    } finally {
      setIsFlightLoading(false);
    }
  };

  const handleCalculateRoadRoute = async () => {
    setIsRoadLoading(true);
    setRoadError(null);
    try {
      const resp = await fetchRoadRoute(
        originCoords[1], // originLat
        originCoords[0], // originLon
        destCoords[1],   // destLat
        destCoords[0],   // destLon
        originName,
        destName
      );
      onSelectRoadRoute(resp);
      // Fly camera to midpoint of road route
      const midLon = (originCoords[0] + destCoords[0]) / 2.0;
      const midLat = (originCoords[1] + destCoords[1]) / 2.0;
      onFlyToCoordinates([midLon, midLat], 13);
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
    handleLoadFlightPlans(city.name);
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
          {/* Destination & Country Filters */}
          <div className="nav-filter-section">
            <div className="nav-input-row">
              <div className="nav-input-wrap flex-1">
                <Search size={14} className="nav-input-icon" />
                <input
                  type="text"
                  placeholder="Enter destination city (e.g. Tokyo, Paris, Rome)..."
                  value={flightDestination}
                  onChange={(e) => setFlightDestination(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleLoadFlightPlans(flightDestination)}
                  className="nav-input"
                />
              </div>
              <button
                className="nav-action-btn primary"
                onClick={() => handleLoadFlightPlans(flightDestination)}
                disabled={isFlightLoading}
              >
                {isFlightLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                <span>Lookup</span>
              </button>
            </div>

            {/* Country Filter Pills */}
            {flightPlansResponse && flightPlansResponse.origin_countries.length > 0 && (
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
                      <span className="flight-frequency-badge">{flight.frequency}</span>
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
          {/* Origin & Destination Config */}
          <div className="road-route-builder">
            <div className="road-input-block">
              <label className="road-input-label">
                <span className="dot origin-dot" />
                <span>START POINT (Airport or Landmark)</span>
              </label>
              <div className="road-input-row">
                <input
                  type="text"
                  value={originName}
                  onChange={(e) => setOriginName(e.target.value)}
                  placeholder="Departure airport or hotel..."
                  className="road-text-input"
                />
              </div>
            </div>

            <div className="road-swap-row">
              <button
                className="road-swap-btn"
                onClick={handleSwapRoadEndpoints}
                title="Swap Start and Destination"
              >
                <ArrowLeftRight size={14} />
                <span>Swap</span>
              </button>
            </div>

            <div className="road-input-block">
              <label className="road-input-label">
                <span className="dot dest-dot" />
                <span>DESTINATION (Place or Attraction)</span>
              </label>
              <div className="road-input-row">
                <input
                  type="text"
                  value={destName}
                  onChange={(e) => setDestName(e.target.value)}
                  placeholder="Attraction, restaurant, or hotel..."
                  className="road-text-input"
                />
              </div>
            </div>

            <button
              className="nav-action-btn primary full-width mt-2"
              onClick={handleCalculateRoadRoute}
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
