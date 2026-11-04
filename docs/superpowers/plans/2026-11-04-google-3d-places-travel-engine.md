# Google Photorealistic 3D, Places Discovery & YouTube Travel Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

---

## Overview
Implement the full Google Maps Platform & YouTube multimodal travel ecosystem in WORLDOS:
1. **Photorealistic 3D Tiles**: Direct integration with Google Map Tiles API in CesiumJS, loading real 3D city buildings, streets, and terrain across global metropolitan areas.
2. **Backend Places & Media Engine**: Fast endpoints for Google Places API (New), Aerial View API (cinematic drone flyovers), and YouTube Data API v3 (room tours, walking vlogs).
3. **Place Discovery Deck (`PlaceDiscoveryDeck.tsx`)**: Google Maps-style mini-block cards for Stays/Hotels, Food & Dining, Scenery & Viewpoints, and Nightlife/Clubs with photo galleries, star ratings, price tiers, and reviews.
4. **Interactive 3D Pins & Flight**: Glowing Cesium markers on the 3D globe for discovered places, with cinematic camera fly-to and pitch angles.
5. **Roger Voice Assistant Integration**: Natural voice-command tool calling (`discover_places`) enabling Roger to suggest and reveal places in conversation.
6. **Git Hygiene & Push**: Full verification, commit via Conventional Commits, and push to GitHub `origin/main`.

---

## File Structure & Responsibilities

- `backend/app/places.py`: Ingestion, normalization, and caching for Google Places API (New), Aerial View API, and YouTube Data API v3, with deterministic offline fallbacks.
- `backend/app/main.py`: REST routes for `/places/search`, `/places/details`, `/places/aerial-view`, and `/places/youtube-tours`.
- `backend/tests/test_places.py`: Pytest suite testing places retrieval, YouTube tour searches, and error handling.
- `frontend/src/api.ts`: API clients and TypeScript types for `PlaceItem`, `AerialVideo`, `YouTubeTour`, and place search parameters.
- `frontend/src/components/GlobeEngine3D.tsx`: Google 3D Tileset initialization using `VITE_GOOGLE_MAPS_API_KEY`, 3D place pin rendering, and cinematic camera focus.
- `frontend/src/components/PlaceDiscoveryDeck.tsx`: Google Maps-style interactive mini-block card deck with photo carousel, ratings, price tier, YouTube vlog player modal, and Aerial View 3D video.
- `frontend/src/components/AssistantPanel.tsx`: Roger agent tool definition for `discover_places`.
- `frontend/src/App.tsx`: State coordination between globe, places deck, route planner, and assistant.
- `docs/adr/0004-google-maps-3d-and-multimodal-places.md`: Architecture Decision Record.
- `WORLDOS_PROGRESS.md`: Project progress tracker update.

---

## Task Decomposition

### Task 1: Backend Multimodal Places, Aerial View & YouTube Engine
- [ ] Create `backend/app/places.py` with:
  - `search_places_nearby(lat, lon, query, category, radius_m)`
  - `get_aerial_view_video(address, lat, lon)`
  - `search_youtube_travel_vlogs(place_name, location_name)`
  - In-memory TTL cache to optimize API quota
  - Resilient mock/fallback generator when offline or if quota is exceeded
- [ ] Wire endpoints in `backend/app/main.py`:
  - `GET /places/discover`
  - `GET /places/aerial-view`
  - `GET /places/youtube-tours`
- [ ] Add unit test suite in `backend/tests/test_places.py` and run `pytest backend/tests` to verify.

### Task 2: Frontend API Client & Types
- [ ] In `frontend/src/api.ts`:
  - Define interfaces: `PlaceItem`, `PlacePhoto`, `AerialViewVideo`, `YouTubeVideoTour`, `PlaceCategory`
  - Implement `fetchPlacesDiscovery(params)`, `fetchAerialView(placeId, address)`, `fetchYouTubeTours(query)`
  - Update `AssistantAction` with `discover_places` action payload

### Task 3: CesiumJS Google Photorealistic 3D Tiles & 3D Markers
- [ ] In `frontend/src/components/GlobeEngine3D.tsx`:
  - Configure `Cesium.GoogleMaps.defaultApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY`
  - Invoke `createGooglePhotorealistic3DTileset({ key: apiKey })` when API key is provided
  - Render glowing 3D billboards / markers for active places on the globe
  - Implement smooth camera fly-to with 45° pitch and bounding sphere framing

### Task 4: Place Discovery Deck Component (`PlaceDiscoveryDeck.tsx`)
- [ ] Create `frontend/src/components/PlaceDiscoveryDeck.tsx`:
  - Category selector tabs: 🏨 Stays, 🍽️ Food & Dining, 🌄 Scenery, 🍸 Nightlife
  - Google Maps-style mini-block card with high-res photo carousel
  - Star rating badge (`★ 4.8 (1,240)`), price level (`$$$$`), editorial summary
  - Action buttons: `[🎯 Fly To 3D]`, `[🎥 Video Tours]`, `[➕ Add to Itinerary]`
  - Modal/flyout for YouTube travel vlogs / 4K room tours
  - Modal/flyout for Google Aerial View 3D cinematic drone videos

### Task 5: App Integration & Assistant Tool Calling
- [ ] Connect `PlaceDiscoveryDeck` in `frontend/src/App.tsx`
- [ ] Register `discover_places` tool in `frontend/src/components/AssistantPanel.tsx` so Roger can trigger place recommendations directly via voice
- [ ] Test end-to-end frontend build (`npm run build`)

### Task 6: Documentation, ADR & Git Push
- [ ] Write ADR `docs/adr/0004-google-maps-3d-and-multimodal-places.md`
- [ ] Update `WORLDOS_PROGRESS.md`
- [ ] Stage and commit changes with Conventional Commits
- [ ] Push to GitHub `origin/main`

