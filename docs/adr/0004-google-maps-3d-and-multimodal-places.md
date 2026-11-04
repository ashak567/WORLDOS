# ADR 0004: Google Maps 3D Photorealistic Tiles, Multimodal Places & YouTube Video Tours

## Status
Accepted

## Context
WORLDOS requires hyper-immersive metropolitan exploration, travel planning, and venue reconnaissance (stays/hotels, fine dining, scenic viewpoints, nightlife) directly within the 3D globe. Traditional raster basemaps lack 3D building geometry, and static 2D pin popups provide insufficient experiential context for discerning travelers. Users require:
1. Photorealistic 3D building and street geometry across global metropolitan centers.
2. Verified venue discovery with reviews, star ratings, price tiers, and high-resolution photo galleries.
3. Immersive video walkthroughs (4K hotel room tours, walking vlogs) and cinematic 3D drone flyovers.
4. Voice-commanded assistant tool calling for natural recommendations and 3D camera navigation.

## Decision
1. **Google Map Tiles API (3D)**: Configure CesiumJS with `createGooglePhotorealistic3DTileset` powered directly by Google Map Tiles API keys (`GOOGLE_MAPS_API_KEY` / `VITE_GOOGLE_MAPS_API_KEY`).
2. **Google Places API (New)**: Expose backend endpoints `/places/discover` with in-memory TTL caching (15 min) and category-specific semantic searches (`stays`, `food`, `scenery`, `nightlife`).
3. **YouTube Data API v3**: Integrate `/places/youtube-tours` to retrieve top 4K room walkthroughs and travel vlogs for selected venues.
4. **Google Aerial View API**: Integrate `/places/aerial-view` for cinematic high-altitude 3D drone video streaming.
5. **Interactive 3D Places Deck & Markers**: Deploy `PlaceDiscoveryDeck.tsx` and custom glowing 3D vector pins on Cesium with cinematic camera fly-to at 45° pitch.
6. **Voice Assistant Tool (`discover_places`)**: Enable Roger to trigger place recommendations directly via voice commands.

## Consequences
### Positive
- High-fidelity 3D building meshes rendered worldwide without third-party tile proxies.
- Google Maps-style mini-block cards with star ratings, price tiers, reviews, and photo galleries.
- Instant access to real YouTube video walkthroughs and Aerial View drone footage.
- Seamless connection between venue discovery and the strategic route planner.
- Deterministic fallback modes ensure uninterrupted offline and quota-safe operation.

### Negative / Trade-offs
- Requires Google Maps Platform and YouTube Data API keys with billing configured.
- Heavy 3D tilesets require WebGL2 and modern GPU support on client browsers.

