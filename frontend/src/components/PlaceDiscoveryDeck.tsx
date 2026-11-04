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
  ChevronRight,
  Maximize2,
} from 'lucide-react';

interface PlaceDiscoveryDeckProps {
  currentCoordinates: [number, number]; // [lon, lat]
  onFlyToPlace: (lon: number, lat: number) => void;
  onSelectPlace?: (place: PlaceItem) => void;
  onAddToRoute?: (place: PlaceItem) => void;
  selectedPlace?: PlaceItem | null;
  isOpen: boolean;
  onToggle: () => void;
}

export const PlaceDiscoveryDeck: React.FC<PlaceDiscoveryDeckProps> = ({
  currentCoordinates,
  onFlyToPlace,
  onSelectPlace,
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

  const categories: { key: PlaceCategory; label: string; icon: React.ReactNode; color: string }[] = [
    { key: 'stays', label: 'Stays & Luxury', icon: <Building2 className="w-4 h-4" />, color: 'text-amber-400 border-amber-500/40' },
    { key: 'food', label: 'Food & Dining', icon: <Utensils className="w-4 h-4" />, color: 'text-rose-400 border-rose-500/40' },
    { key: 'scenery', label: 'Scenery & Views', icon: <Mountain className="w-4 h-4" />, color: 'text-emerald-400 border-emerald-500/40' },
    { key: 'nightlife', label: 'Nightlife & Clubs', icon: <GlassWater className="w-4 h-4" />, color: 'text-purple-400 border-purple-500/40' },
  ];

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 px-4 py-2.5 bg-slate-900/90 hover:bg-slate-800 border border-amber-500/40 text-amber-300 rounded-full shadow-2xl backdrop-blur-md transition-all hover:scale-105 active:scale-95 text-xs font-semibold tracking-wider uppercase"
      >
        <Building2 className="w-4 h-4 text-amber-400 animate-pulse" />
        <span>Explore Stays & Places</span>
      </button>
    );
  }

  return (
    <>
      <div className="fixed bottom-6 right-6 z-40 w-96 max-h-[82vh] bg-slate-950/95 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl flex flex-col overflow-hidden text-slate-100 font-sans transition-all animate-in fade-in slide-in-from-bottom-4">
        {/* Header */}
        <div className="p-4 border-b border-slate-800/80 bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-950 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <Building2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold tracking-tight text-slate-100">Places & Stays Engine</h3>
              <p className="text-[11px] text-slate-400">Google Places (New) · 3D Photorealistic Mesh</p>
            </div>
          </div>
          <button
            onClick={onToggle}
            className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Category Tabs */}
        <div className="p-2.5 grid grid-cols-2 gap-1.5 bg-slate-900/40 border-b border-slate-800/50">
          {categories.map((cat) => {
            const isActive = activeCategory === cat.key;
            return (
              <button
                key={cat.key}
                onClick={() => setActiveCategory(cat.key)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? `bg-slate-800/90 ${cat.color} border shadow-sm`
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent'
                }`}
              >
                {cat.icon}
                <span className="truncate">{cat.label}</span>
              </button>
            );
          })}
        </div>

        {/* Search Bar */}
        <div className="p-3 border-b border-slate-800/40 bg-slate-900/20">
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 absolute left-3 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={`Search ${activeCategory} (e.g. Michelin, boutique, rooftop)...`}
              className="w-full bg-slate-900/80 border border-slate-800 text-slate-200 text-xs rounded-xl pl-9 pr-3 py-2 focus:outline-none focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/30 placeholder:text-slate-600 transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 text-slate-500 hover:text-slate-300"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Places List (Google Maps-style Mini-Blocks) */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3.5 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500 text-xs">
              <Loader2 className="w-6 h-6 animate-spin text-amber-500 mb-2" />
              <span>Scanning metropolitan coordinates...</span>
            </div>
          )}

          {!loading && error && (
            <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-900/40 text-rose-300 text-xs text-center">
              {error}
            </div>
          )}

          {!loading && !error && places.length === 0 && (
            <div className="text-center py-10 text-slate-500 text-xs">
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
                  className={`group rounded-xl border transition-all cursor-pointer overflow-hidden ${
                    isSelected
                      ? 'bg-slate-900/90 border-amber-500/80 ring-2 ring-amber-500/20 shadow-lg shadow-amber-500/10'
                      : 'bg-slate-900/40 hover:bg-slate-900/70 border-slate-800/80 hover:border-slate-700'
                  }`}
                >
                  {/* Photo Thumbnail Banner */}
                  <div className="relative h-32 w-full overflow-hidden bg-slate-950">
                    <img
                      src={heroPhoto}
                      alt={place.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      loading="lazy"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-transparent" />

                    {/* Price Pill & Category Badge */}
                    <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5">
                      <span className="px-2 py-0.5 rounded-full bg-slate-950/80 backdrop-blur-md border border-slate-800 text-[10px] font-semibold text-emerald-400">
                        {place.price_level || '$$$'} · {place.price_display || 'Upscale'}
                      </span>
                    </div>

                    {/* Star Rating Badge */}
                    <div className="absolute top-2.5 right-2.5 flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-950/85 backdrop-blur-md border border-amber-500/40 text-[11px] font-bold text-amber-300">
                      <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                      <span>{place.rating ? place.rating.toFixed(1) : '4.8'}</span>
                      <span className="text-[9px] text-slate-400 font-normal">
                        ({place.user_rating_count ? place.user_rating_count.toLocaleString() : '1k+'})
                      </span>
                    </div>

                    {/* Venue Title Overlay */}
                    <div className="absolute bottom-2 left-3 right-3">
                      <h4 className="text-sm font-bold text-white tracking-tight truncate drop-shadow-md">
                        {place.name}
                      </h4>
                      <p className="text-[11px] text-slate-300 flex items-center gap-1 truncate">
                        <MapPin className="w-2.5 h-2.5 text-slate-400 shrink-0" />
                        <span className="truncate">{place.formatted_address}</span>
                      </p>
                    </div>
                  </div>

                  {/* Summary & Actions */}
                  <div className="p-3 space-y-2.5">
                    <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                      {place.summary}
                    </p>

                    {/* Action Bar */}
                    <div className="grid grid-cols-3 gap-1.5 pt-1 border-t border-slate-800/60">
                      {/* Fly To 3D */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onFlyToPlace(place.longitude, place.latitude);
                          onSelectPlace?.(place);
                        }}
                        className="flex items-center justify-center gap-1 py-1.5 px-2 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 rounded-lg text-[10px] font-medium transition-colors"
                        title="Fly camera to 3D photorealistic buildings"
                      >
                        <Compass className="w-3 h-3 text-amber-400" />
                        <span>3D Fly</span>
                      </button>

                      {/* YouTube Tours */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenYouTube(place);
                        }}
                        className="flex items-center justify-center gap-1 py-1.5 px-2 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 rounded-lg text-[10px] font-medium transition-colors"
                        title="Watch 4K room tours and walking vlogs"
                      >
                        <Video className="w-3 h-3 text-rose-400" />
                        <span>Vlogs</span>
                      </button>

                      {/* Add to Itinerary */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAddToRoute(place);
                        }}
                        className={`flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg text-[10px] font-medium transition-all ${
                          isAdded
                            ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-300'
                            : 'bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 text-slate-300'
                        }`}
                        title="Add to active travel route planner"
                      >
                        {isAdded ? (
                          <>
                            <CheckCircle className="w-3 h-3 text-emerald-400" />
                            <span>Added</span>
                          </>
                        ) : (
                          <>
                            <PlusCircle className="w-3 h-3 text-slate-400" />
                            <span>Route</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* YouTube Multimodal Video Modal */}
      {activeYouTubePlace && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400">
                  <Play className="w-4 h-4 fill-rose-400" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white tracking-tight">
                    {activeYouTubePlace.name} · Video Tours
                  </h3>
                  <p className="text-[11px] text-slate-400">Powered by YouTube Data API v3</p>
                </div>
              </div>
              <button
                onClick={() => setActiveYouTubePlace(null)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Video Player */}
            <div className="relative aspect-video w-full bg-black">
              {loadingYouTube && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 text-xs">
                  <Loader2 className="w-8 h-8 animate-spin text-rose-500 mb-2" />
                  <span>Loading 4K walkthroughs...</span>
                </div>
              )}
              {!loadingYouTube && selectedVideoId && (
                <iframe
                  className="w-full h-full"
                  src={`https://www.youtube.com/embed/${selectedVideoId}?autoplay=1`}
                  title="YouTube video player"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              )}
              {!loadingYouTube && !selectedVideoId && (
                <div className="flex items-center justify-center h-full text-slate-500 text-xs">
                  No video streams available for this venue.
                </div>
              )}
            </div>

            {/* Alternative Tours List */}
            {youTubeTours.length > 1 && (
              <div className="p-3 bg-slate-950/40 border-t border-slate-800/80 overflow-x-auto flex gap-2 scrollbar-none">
                {youTubeTours.map((tour) => (
                  <button
                    key={tour.video_id}
                    onClick={() => setSelectedVideoId(tour.video_id)}
                    className={`flex items-center gap-2 p-2 rounded-xl text-left border shrink-0 transition-all ${
                      selectedVideoId === tour.video_id
                        ? 'bg-rose-950/30 border-rose-500/50 text-white'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <img
                      src={tour.thumbnail_url}
                      alt={tour.title}
                      className="w-14 h-9 object-cover rounded-md"
                    />
                    <div className="max-w-[180px]">
                      <p className="text-[11px] font-medium line-clamp-1">{tour.title}</p>
                      <p className="text-[9px] text-slate-500 truncate">{tour.channel_title}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Aerial View Drone Video Modal */}
      {activeAerialPlace && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-400">
                  <Compass className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white tracking-tight">
                    {activeAerialPlace.name} · 3D Aerial Flyover
                  </h3>
                  <p className="text-[11px] text-slate-400">Google Aerial View API · High Altitude Drone Cinematic</p>
                </div>
              </div>
              <button
                onClick={() => setActiveAerialPlace(null)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="relative aspect-video w-full bg-black">
              {loadingAerial && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 text-xs">
                  <Loader2 className="w-8 h-8 animate-spin text-sky-500 mb-2" />
                  <span>Fetching 3D cinematic video...</span>
                </div>
              )}
              {!loadingAerial && aerialVideo?.video_url && (
                <video
                  src={aerialVideo.video_url}
                  autoPlay
                  controls
                  loop
                  className="w-full h-full object-contain"
                />
              )}
              {!loadingAerial && !aerialVideo?.video_url && (
                <div className="flex flex-col items-center justify-center h-full p-6 text-center text-slate-400 text-xs">
                  <p>Aerial View cinematic video is processing or currently exclusive to major metropolitan landmarks.</p>
                  <p className="text-[10px] text-slate-500 mt-2">Use "3D Fly" to explore Google Photorealistic 3D Tiles directly on the globe.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
