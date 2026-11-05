import React, { useState, useEffect } from 'react';
import {
  PlaceCategory,
  PlaceItem,
  YouTubeTour,
  AerialViewVideo,
  fetchDiscoveredPlaces,
  fetchPlaceYouTubeTours,
  fetchPlaceAerialView,
} from '../api';
import {
  Building2,
  Utensils,
  Mountain,
  GlassWater,
  Star,
  MapPin,
  ExternalLink,
  Compass,
  Video,
  Play,
  X,
  Search,
  PlusCircle,
  CheckCircle,
  Loader2,
} from 'lucide-react';

interface PlaceDiscoveryDeckProps {
  currentCoordinates: [number, number]; // [lon, lat]
  onFlyToPlace: (lon: number, lat: number) => void;
  onSelectPlace?: (place: PlaceItem) => void;
  onPlacesLoaded?: (places: PlaceItem[]) => void;
  onAddToRoute?: (place: PlaceItem) => void;
  selectedPlace?: PlaceItem | null;
  isOpen: boolean;
  onToggle: () => void;
}

export const PlaceDiscoveryDeck: React.FC<PlaceDiscoveryDeckProps> = ({
  currentCoordinates,
  onFlyToPlace,
  onSelectPlace,
  onPlacesLoaded,
  onAddToRoute,
  selectedPlace,
  isOpen,
  onToggle,
}) => {
  const [activeCategory, setActiveCategory] = useState<PlaceCategory>('stays');
  const [searchQuery, setSearchQuery] = useState('');
  const [places, setPlaces] = useState<PlaceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Multimodal modals
  const [activeYouTubePlace, setActiveYouTubePlace] = useState<PlaceItem | null>(null);
  const [youTubeTours, setYouTubeTours] = useState<YouTubeTour[]>([]);
  const [loadingYouTube, setLoadingYouTube] = useState(false);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);

  const [activeAerialPlace, setActiveAerialPlace] = useState<PlaceItem | null>(null);
  const [aerialVideo, setAerialVideo] = useState<AerialViewVideo | null>(null);
  const [loadingAerial, setLoadingAerial] = useState(false);

  // Added to itinerary notification
  const [addedIds, setAddedIds] = useState<Set<string>>(new Set());

  const [lon, lat] = currentCoordinates;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const timer = setTimeout(() => {
      fetchDiscoveredPlaces({
        latitude: lat,
        longitude: lon,
        category: activeCategory,
        query: searchQuery.trim() || undefined,
        limit: 10,
      })
        .then((items) => {
          if (!cancelled) {
            setPlaces(items);
            onPlacesLoaded?.(items);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setError(err.message || 'Failed to fetch places');
            setLoading(false);
          }
        });
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [lat, lon, activeCategory, searchQuery]);

  const handleOpenYouTube = async (place: PlaceItem) => {
    setActiveYouTubePlace(place);
    setLoadingYouTube(true);
    setSelectedVideoId(null);
    try {
      const tours = await fetchPlaceYouTubeTours(place.name, place.formatted_address, 4);
      setYouTubeTours(tours);
      if (tours.length > 0) {
        setSelectedVideoId(tours[0].video_id);
      }
    } catch {
      setYouTubeTours([]);
    } finally {
      setLoadingYouTube(false);
    }
  };

  const handleOpenAerialView = async (place: PlaceItem) => {
    setActiveAerialPlace(place);
    setLoadingAerial(true);
    try {
      const vid = await fetchPlaceAerialView(place.formatted_address, place.latitude, place.longitude);
      setAerialVideo(vid);
    } catch {
      setAerialVideo(null);
    } finally {
      setLoadingAerial(false);
    }
  };

  const handleAddToRoute = (place: PlaceItem) => {
    onAddToRoute?.(place);
    setAddedIds((prev) => new Set(prev).add(place.id));
    setTimeout(() => {
      setAddedIds((prev) => {
        const next = new Set(prev);
        next.delete(place.id);
        return next;
      });
    }, 2500);
  };

  const categories: { key: PlaceCategory; label: string; icon: React.ReactNode }[] = [
    { key: 'stays', label: 'Stays & Luxury', icon: <Building2 size={13} /> },
    { key: 'food', label: 'Food & Dining', icon: <Utensils size={13} /> },
    { key: 'scenery', label: 'Scenery & Views', icon: <Mountain size={13} /> },
    { key: 'nightlife', label: 'Nightlife & Bars', icon: <GlassWater size={13} /> },
  ];

  if (!isOpen) {
    return null;
  }

  return (
    <>
      <aside className="places-deck" aria-label="Places & Stays Engine">
        {/* Header */}
        <div className="places-deck-header">
          <div className="places-deck-title-group">
            <div className="places-deck-icon-badge">
              <Building2 size={16} />
            </div>
            <div>
              <h3 className="places-deck-title">PLACES &amp; STAYS</h3>
              <p className="places-deck-subtitle">Google Places (New) · 3D Mesh</p>
            </div>
          </div>
          <button
            onClick={onToggle}
            className="places-deck-close-btn"
            title="Close Places Deck"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Category Tabs */}
        <div className="places-deck-categories">
          {categories.map((cat) => {
            const isActive = activeCategory === cat.key;
            return (
              <button
                key={cat.key}
                onClick={() => setActiveCategory(cat.key)}
                className={`places-cat-btn ${isActive ? 'active' : ''}`}
              >
                {cat.icon}
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>

        {/* Search Bar */}
        <div className="places-deck-search">
          <div className="places-search-input-wrap">
            <Search size={13} className="places-search-icon" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={`Search ${activeCategory} (e.g. Michelin, boutique, rooftop)...`}
              className="places-search-input"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="places-search-clear">
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Places Cards List */}
        <div className="places-deck-list">
          {loading && (
            <div style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-muted)', fontSize: '11px' }}>
              <Loader2 size={24} style={{ animation: 'spin 1s linear infinite', color: '#eab308', margin: '0 auto 8px auto', display: 'block' }} />
              <span>Scanning coordinates for {activeCategory}...</span>
            </div>
          )}

          {!loading && error && (
            <div style={{ padding: '12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '4px', color: '#fca5a5', fontSize: '11px', textAlign: 'center' }}>
              {error}
            </div>
          )}

          {!loading && !error && places.length === 0 && (
            <div style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-muted)', fontSize: '11px' }}>
              No matching locations found within current area.
            </div>
          )}

          {!loading &&
            places.map((place) => {
              const isSelected = selectedPlace?.id === place.id;
              const isAdded = addedIds.has(place.id);
              const heroPhoto = place.photos?.[0] || 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=600';

              return (
                <div
                  key={place.id}
                  onClick={() => onSelectPlace?.(place)}
                  className={`places-card ${isSelected ? 'selected' : ''}`}
                >
                  <div className="places-card-img-wrap">
                    <img src={heroPhoto} alt={place.name} className="places-card-img" loading="lazy" />
                    <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', gap: 6 }}>
                      <span style={{ background: 'rgba(5, 8, 12, 0.85)', padding: '2px 8px', borderRadius: 4, fontSize: '10px', color: '#38bdf8', fontWeight: 700, border: '1px solid rgba(255,255,255,0.1)' }}>
                        {place.price_level || '$$$'} · {place.price_display || 'Upscale'}
                      </span>
                    </div>

                    <div style={{ position: 'absolute', top: 8, right: 8 }}>
                      <span className="places-card-rating" style={{ background: 'rgba(5, 8, 12, 0.85)', padding: '2px 8px', borderRadius: 4, border: '1px solid rgba(234, 179, 8, 0.3)' }}>
                        <Star size={11} fill="#eab308" color="#eab308" />
                        <span>{place.rating ? place.rating.toFixed(1) : '4.8'}</span>
                        <span style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                          ({place.user_rating_count ? place.user_rating_count.toLocaleString() : '350+'})
                        </span>
                      </span>
                    </div>

                    <div style={{ position: 'absolute', bottom: 8, left: 10, right: 10, textShadow: '0 2px 8px rgba(0,0,0,0.9)' }}>
                      <div className="places-card-name" style={{ color: '#fff', fontSize: '13px' }}>{place.name}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'rgba(255,255,255,0.8)', fontSize: '10px' }}>
                        <MapPin size={10} color="#eab308" />
                        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{place.formatted_address}</span>
                      </div>
                    </div>
                  </div>

                  <div className="places-card-body">
                    <p style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.4, margin: 0, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {place.summary}
                    </p>

                    <div className="places-card-actions">
                      <button
                        className="places-card-btn primary"
                        onClick={(e) => {
                          e.stopPropagation();
                          onFlyToPlace(place.longitude, place.latitude);
                          onSelectPlace?.(place);
                        }}
                        title="Fly camera to location"
                      >
                        <Compass size={11} />
                        <span>Fly 3D</span>
                      </button>

                      <button
                        className="places-card-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenYouTube(place);
                        }}
                        title="Watch 4K room tours and walking vlogs"
                      >
                        <Video size={11} color="#f43f5e" />
                        <span>Vlogs</span>
                      </button>

                      <button
                        className="places-card-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAddToRoute(place);
                        }}
                        title="Add to multi-modal route planner"
                      >
                        {isAdded ? (
                          <>
                            <CheckCircle size={11} color="#10b981" />
                            <span>Added</span>
                          </>
                        ) : (
                          <>
                            <PlusCircle size={11} />
                            <span>Route</span>
                          </>
                        )}
                      </button>

                      {place.google_maps_url && (
                        <a
                          href={place.google_maps_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="places-card-btn"
                          onClick={(e) => e.stopPropagation()}
                          title="Open in Google Maps"
                        >
                          <ExternalLink size={10} />
                          <span>Maps</span>
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </aside>

      {/* YouTube Multimodal Video Modal */}
      {activeYouTubePlace && (
        <div className="places-modal-backdrop" onClick={() => setActiveYouTubePlace(null)}>
          <div className="places-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="places-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ padding: 6, background: 'rgba(244, 63, 94, 0.15)', borderRadius: 4, color: '#f43f5e', display: 'flex' }}>
                  <Play size={14} fill="#f43f5e" />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-brand)' }}>
                    {activeYouTubePlace.name} · Video Tours
                  </h3>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Powered by YouTube Data API v3</span>
                </div>
              </div>
              <button
                onClick={() => setActiveYouTubePlace(null)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 4 }}
              >
                <X size={16} />
              </button>
            </div>

            <div className="places-modal-body">
              {loadingYouTube && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '11px' }}>
                  <Loader2 size={28} style={{ animation: 'spin 1s linear infinite', color: '#f43f5e', marginBottom: 8 }} />
                  <span>Loading 4K walkthroughs...</span>
                </div>
              )}
              {!loadingYouTube && selectedVideoId && (
                <iframe
                  style={{ width: '100%', height: '100%', border: 'none' }}
                  src={`https://www.youtube.com/embed/${selectedVideoId}?autoplay=1`}
                  title="YouTube video player"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              )}
              {!loadingYouTube && !selectedVideoId && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '11px' }}>
                  No video streams available for this venue.
                </div>
              )}
            </div>

            {youTubeTours.length > 1 && (
              <div style={{ padding: '8px 12px', background: 'rgba(5, 8, 12, 0.7)', borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 8, overflowX: 'auto' }}>
                {youTubeTours.map((tour) => (
                  <button
                    key={tour.video_id}
                    onClick={() => setSelectedVideoId(tour.video_id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 8px',
                      background: selectedVideoId === tour.video_id ? 'rgba(244, 63, 94, 0.2)' : 'rgba(16, 26, 38, 0.6)',
                      border: selectedVideoId === tour.video_id ? '1px solid #f43f5e' : '1px solid var(--border-subtle)',
                      borderRadius: 4,
                      color: 'var(--text-primary)',
                      cursor: 'pointer',
                      flexShrink: 0,
                      textAlign: 'left',
                    }}
                  >
                    <img src={tour.thumbnail_url} alt={tour.title} style={{ width: 48, height: 32, objectFit: 'cover', borderRadius: 2 }} />
                    <div style={{ maxWidth: 160 }}>
                      <div style={{ fontSize: '10px', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tour.title}</div>
                      <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>{tour.channel_title}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Aerial View Modal */}
      {activeAerialPlace && (
        <div className="places-modal-backdrop" onClick={() => setActiveAerialPlace(null)}>
          <div className="places-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="places-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ padding: 6, background: 'rgba(56, 189, 248, 0.15)', borderRadius: 4, color: '#38bdf8', display: 'flex' }}>
                  <Compass size={14} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-brand)' }}>
                    {activeAerialPlace.name} · 3D Aerial Flyover
                  </h3>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Google Aerial View API</span>
                </div>
              </div>
              <button
                onClick={() => setActiveAerialPlace(null)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 4 }}
              >
                <X size={16} />
              </button>
            </div>

            <div className="places-modal-body">
              {loadingAerial && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '11px' }}>
                  <Loader2 size={28} style={{ animation: 'spin 1s linear infinite', color: '#38bdf8', marginBottom: 8 }} />
                  <span>Fetching 3D cinematic video...</span>
                </div>
              )}
              {!loadingAerial && aerialVideo?.video_url && (
                <video src={aerialVideo.video_url} autoPlay controls loop style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              )}
              {!loadingAerial && !aerialVideo?.video_url && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 24, textAlign: 'center', color: 'var(--text-secondary)', fontSize: '11px' }}>
                  <p style={{ margin: 0 }}>Aerial View cinematic drone video is currently in generation or exclusive to major landmarks.</p>
                  <p style={{ margin: '8px 0 0 0', fontSize: '10px', color: 'var(--text-muted)' }}>Use "Fly 3D" to view this building in Google Photorealistic 3D on the globe.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
