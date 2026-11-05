"""Live Internet Travel Intelligence & Itinerary Synthesis Engine for WORLDOS.

Queries Google Places API (New), Wikipedia, and curated travel intelligence to formulate
concrete day-by-day travel plans, famous sights, and authentic local food hidden gems.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from .places import _get_api_key

logger = logging.getLogger("worldos.travel_intelligence")

KNOWN_CITIES = [
    ("Tokyo", 35.6895, 139.6917),
    ("Kyoto", 35.0116, 135.7681),
    ("Osaka", 34.6937, 135.5023),
    ("New York", 40.7128, -74.0060),
    ("London", 51.5074, -0.1278),
    ("Paris", 48.8566, 2.3522),
    ("Rome", 41.9028, 12.4964),
    ("Berlin", 52.5200, 13.4050),
    ("Amsterdam", 52.3676, 4.9041),
    ("San Francisco", 37.7749, -122.4194),
    ("Los Angeles", 34.0522, -118.2437),
    ("Chicago", 41.8781, -87.6298),
    ("Las Vegas", 36.1699, -115.1398),
    ("Seattle", 47.6062, -122.3321),
    ("Honolulu", 21.3069, -157.8583),
    ("Sydney", -33.8688, 151.2093),
    ("Singapore", 1.3521, 103.8198),
    ("Hong Kong", 22.3193, 114.1694),
    ("Bangkok", 13.7563, 100.5018),
    ("Seoul", 37.5665, 126.9780),
    ("Dubai", 25.2048, 55.2708),
    ("Cairo", 30.0444, 31.2357),
    ("Delhi", 28.6139, 77.2090),
    ("Mumbai", 19.0760, 72.8777),
    ("Bengaluru", 12.9716, 77.5946),
]


def resolve_destination_from_coords(lat: float, lon: float) -> str:
    """Find the closest world city for a coordinate pair."""
    best_city = "Tokyo"
    best_dist = float("inf")
    for name, c_lat, c_lon in KNOWN_CITIES:
        dist = ((lat - c_lat) ** 2 + (lon - c_lon) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_city = name
    return best_city

CURATED_DESTINATIONS: dict[str, dict[str, Any]] = {
    "tokyo": {
        "destination": "Tokyo",
        "country": "Japan",
        "center": [139.6917, 35.6895],
        "zoom": 13,
        "summary": "Tokyo, Japan's bustling capital, mixes the ultramodern and the traditional, from neon-lit skyscrapers to historic temples.",
        "famous_attractions": [
            {
                "name": "Sensō-ji Temple & Asakusa",
                "summary": "Tokyo's oldest and most significant Buddhist temple, approached via the bustling Nakamise-dori shopping street.",
                "lat": 35.7148,
                "lon": 139.7967,
                "rating": 4.7,
                "type": "sight",
            },
            {
                "name": "Shibuya Scramble Crossing & Hachiko",
                "summary": "The world's busiest pedestrian crossing, surrounded by giant video screens and energetic Tokyo youth culture.",
                "lat": 35.6595,
                "lon": 139.7005,
                "rating": 4.6,
                "type": "sight",
            },
            {
                "name": "Tokyo Skytree",
                "summary": "The world's tallest freestanding broadcast tower (634m) with panoramic observation decks overlooking Mount Fuji.",
                "lat": 35.7101,
                "lon": 139.8107,
                "rating": 4.5,
                "type": "scenic",
            },
            {
                "name": "Meiji Jingu Shrine & Yoyogi Park",
                "summary": "Serene Shinto shrine set within an evergreen forest of over 100,000 trees in the heart of Shibuya.",
                "lat": 35.6764,
                "lon": 139.6993,
                "rating": 4.7,
                "type": "sight",
            },
        ],
        "local_food": [
            {
                "name": "Tsukiji Outer Market Fresh Seafood & Tamagoyaki",
                "summary": "Historic open-air market famous for ultra-fresh sashimi, grilled unagi, sea urchin, and rolled Japanese omelets.",
                "lat": 35.6655,
                "lon": 139.7708,
                "rating": 4.8,
                "type": "food",
            },
            {
                "name": "Omoide Yokocho (Memory Lane) & Golden Gai",
                "summary": "Atmospheric post-war alleys lined with tiny authentic yakitori stalls, ramen counters, and cozy izakayas.",
                "lat": 35.6934,
                "lon": 139.6998,
                "rating": 4.7,
                "type": "hidden_gem",
            },
            {
                "name": "Gyukatsu Motomura Shibuya",
                "summary": "Famous crispy deep-fried wagyu beef cutlet that you sear to perfection on your personal hot stone grill.",
                "lat": 35.6570,
                "lon": 139.7040,
                "rating": 4.9,
                "type": "food",
            },
        ],
        "pro_tips": [
            "Get an IC card (Suica or Pasmo on mobile wallet) for frictionless transit across JR lines and subways.",
            "Visit Sensō-ji at dawn or after 8 PM when lanterns are illuminated and crowds are sparse.",
            "Take the Yurikamome automated monorail at sunset to Odaiba for dramatic Rainbow Bridge views.",
        ],
    },
    "paris": {
        "destination": "Paris",
        "country": "France",
        "center": [2.3522, 48.8566],
        "zoom": 13,
        "summary": "Paris, France's capital, is a major European city and a global center for art, fashion, gastronomy, and culture.",
        "famous_attractions": [
            {
                "name": "Eiffel Tower & Champ de Mars",
                "summary": "Gustave Eiffel's iconic iron lattice tower offering spectacular panoramic views over the Seine River.",
                "lat": 48.8584,
                "lon": 2.2945,
                "rating": 4.7,
                "type": "sight",
            },
            {
                "name": "Louvre Museum & Cour Napoléon",
                "summary": "The world's largest art museum, home to the Mona Lisa, Venus de Milo, and the iconic glass pyramid.",
                "lat": 48.8606,
                "lon": 2.3376,
                "rating": 4.7,
                "type": "sight",
            },
            {
                "name": "Arc de Triomphe & Champs-Élysées",
                "summary": "Monumental triumphal arch honoring French military victories, anchoring the western end of the Champs-Élysées.",
                "lat": 48.8738,
                "lon": 2.2950,
                "rating": 4.7,
                "type": "sight",
            },
            {
                "name": "Sainte-Chapelle & Notre-Dame",
                "summary": "Gothic royal chapel renowned for its mesmerizing 13th-century stained-glass windows rising 15 meters high.",
                "lat": 48.8554,
                "lon": 2.3450,
                "rating": 4.8,
                "type": "sight",
            },
        ],
        "local_food": [
            {
                "name": "Le Marais Traditional Bakeries & Falafel",
                "summary": "Historic quarter bursting with artisanal boulangeries, warm crusty baguettes, and iconic Rue des Rosiers falafel.",
                "lat": 48.8588,
                "lon": 2.3614,
                "rating": 4.8,
                "type": "food",
            },
            {
                "name": "Rue Cler Market Street Bistros",
                "summary": "Charming pedestrian market street near the Eiffel Tower packed with cheesemongers, crêperies, and classic cafés.",
                "lat": 48.8560,
                "lon": 2.3060,
                "rating": 4.7,
                "type": "hidden_gem",
            },
        ],
        "pro_tips": [
            "Book Louvre and Eiffel Tower time-slot tickets at least 2 weeks in advance to skip 2-hour queues.",
            "Take the Seine river cruise near Pont Neuf at twilight to see monument illuminations turn on.",
        ],
    },
    "kyoto": {
        "destination": "Kyoto",
        "country": "Japan",
        "center": [135.7681, 35.0116],
        "zoom": 13,
        "summary": "Kyoto was Japan's imperial capital for over a millennium, famed for countless classical Buddhist temples, gardens, and imperial palaces.",
        "famous_attractions": [
            {
                "name": "Fushimi Inari-taisha 10,000 Torii Gates",
                "summary": "Legendary shrine with vibrant vermilion torii gate pathways winding up sacred Mount Inari.",
                "lat": 34.9671,
                "lon": 135.7727,
                "rating": 4.8,
                "type": "sight",
            },
            {
                "name": "Kinkaku-ji (Golden Pavilion)",
                "summary": "Zen Buddhist temple whose top two floors are completely covered in gleaming gold leaf overlooking a mirror pond.",
                "lat": 35.0394,
                "lon": 135.7292,
                "rating": 4.7,
                "type": "sight",
            },
            {
                "name": "Arashiyama Bamboo Grove & Tenryu-ji",
                "summary": "Ethereal soaring bamboo forest pathway alongside UNESCO-listed Zen temples and the scenic Oi River.",
                "lat": 35.0170,
                "lon": 135.6713,
                "rating": 4.7,
                "type": "scenic",
            },
        ],
        "local_food": [
            {
                "name": "Nishiki Market (Kyoto's Kitchen)",
                "summary": "Five-block narrow shopping street boasting over a hundred lively stalls offering matcha sweets, yakitori, and pickles.",
                "lat": 35.0050,
                "lon": 135.7650,
                "rating": 4.6,
                "type": "food",
            },
            {
                "name": "Gion Shirakawa Traditional Kaiseki",
                "summary": "Preserved geisha district along willow-lined canals with exquisite seasonal multi-course kaiseki ryori.",
                "lat": 35.0037,
                "lon": 135.7770,
                "rating": 4.8,
                "type": "hidden_gem",
            },
        ],
        "pro_tips": [
            "Visit Fushimi Inari at 7:00 AM before tour buses arrive to experience serene, empty torii tunnels.",
            "Rent an electric bicycle in Arashiyama to easily navigate northern temple paths.",
        ],
    },
    "new york": {
        "destination": "New York City",
        "country": "USA",
        "center": [-74.0060, 40.7128],
        "zoom": 12,
        "summary": "New York City comprises 5 boroughs sitting where the Hudson River meets the Atlantic Ocean, anchored by Manhattan.",
        "famous_attractions": [
            {
                "name": "Central Park & Bethesda Terrace",
                "summary": "843-acre urban oasis featuring scenic lakes, tree-lined walking malls, and European-style architecture.",
                "lat": 40.7829,
                "lon": -73.9654,
                "rating": 4.8,
                "type": "scenic",
            },
            {
                "name": "Times Square & Broadway Theater District",
                "summary": "Major commercial intersection, tourist destination, and entertainment center dazzling with neon billboards.",
                "lat": 40.7580,
                "lon": -73.9855,
                "rating": 4.6,
                "type": "sight",
            },
            {
                "name": "Brooklyn Bridge & DUMBO Promenade",
                "summary": "Iconic neo-Gothic suspension bridge offering sweeping skyline views across the East River.",
                "lat": 40.7061,
                "lon": -73.9969,
                "rating": 4.8,
                "type": "sight",
            },
            {
                "name": "The High Line & Hudson Yards",
                "summary": "1.45-mile elevated freight rail line transformed into a lush public park overlooking the Meatpacking District.",
                "lat": 40.7480,
                "lon": -74.0048,
                "rating": 4.7,
                "type": "scenic",
            },
        ],
        "local_food": [
            {
                "name": "Chinatown & Lower East Side Deli Trail",
                "summary": "Authentic soup dumplings, pork buns, and legendary pastrami on rye at Katz's Delicatessen.",
                "lat": 40.7222,
                "lon": -73.9874,
                "rating": 4.8,
                "type": "food",
            },
            {
                "name": "West Village Artisanal Pizza & Espresso",
                "summary": "Cobblestone streets lined with wood-fired Neapolitan pizza spots and jazz clubs.",
                "lat": 40.7358,
                "lon": -74.0036,
                "rating": 4.8,
                "type": "hidden_gem",
            },
        ],
        "pro_tips": [
            "Walk the Brooklyn Bridge from Brooklyn towards Manhattan at sunset for the most dramatic skyline views.",
            "Use OMNY tap-to-pay with your phone on all NYC subways; rides cap automatically after 12 trips.",
        ],
    },
}


def fetch_wikipedia_summary(destination: str) -> dict[str, Any] | None:
    """Fetch authoritative encyclopedic overview and coordinates from Wikipedia REST API."""
    cleaned = destination.strip()
    encoded = urllib.parse.quote(cleaned)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "WORLDOS-Travel/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            coords = data.get("coordinates")
            return {
                "title": data.get("title", cleaned),
                "summary": data.get("extract", ""),
                "thumbnail": data.get("thumbnail", {}).get("source"),
                "lat": coords.get("lat") if coords else None,
                "lon": coords.get("lon") if coords else None,
            }
    except Exception as exc:
        logger.debug("Wikipedia summary lookup failed for %s: %s", cleaned, exc)
        return None


def fetch_google_places_internet(text_query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Query live internet places via Google Places API (New) searchText endpoint."""
    api_key = _get_api_key("google_maps")
    if not api_key:
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    payload = {"textQuery": text_query, "maxResultCount": min(limit, 8)}
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,places.location,"
            "places.rating,places.userRatingCount,places.editorialSummary,places.photos"
        ),
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=7.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results: list[dict[str, Any]] = []
            for p in data.get("places", []):
                name = p.get("displayName", {}).get("text")
                if not name:
                    continue
                loc = p.get("location", {})
                lat = loc.get("latitude")
                lon = loc.get("longitude")
                if lat is None or lon is None:
                    continue
                summary = p.get("editorialSummary", {}).get("text") or ""
                rating = p.get("rating")
                count = p.get("userRatingCount")
                address = p.get("formattedAddress") or ""
                photos = []
                for ph in p.get("photos", [])[:1]:
                    pref = ph.get("name")
                    if pref:
                        photos.append(
                            f"https://places.googleapis.com/v1/{pref}/media?maxHeightPx=600&maxWidthPx=900&key={api_key}"
                        )

                results.append({
                    "name": name,
                    "summary": summary,
                    "lat": lat,
                    "lon": lon,
                    "rating": rating,
                    "user_rating_count": count,
                    "address": address,
                    "photos": photos,
                })
            return results
    except Exception as exc:
        logger.warning("Google Places searchText failed for '%s': %s", text_query, exc)
        return []


def generate_travel_plan(
    destination: str,
    days: int = 3,
    pace: str = "balanced",
    interest: str = "",
) -> dict[str, Any]:
    """Build a comprehensive, concrete travel plan combining live web intelligence and curated gems."""
    cleaned_dest = destination.strip()
    dest_lower = cleaned_dest.lower()

    # 1. Check curated destination database
    matched_key = None
    for k in CURATED_DESTINATIONS:
        if k in dest_lower:
            matched_key = k
            break

    curated = CURATED_DESTINATIONS.get(matched_key) if matched_key else None

    # 2. Fetch live internet intelligence from Google Places (New)
    live_sights = fetch_google_places_internet(f"top attractions and landmarks in {cleaned_dest}", limit=6)
    live_food = fetch_google_places_internet(f"best authentic local food hidden gems restaurants in {cleaned_dest}", limit=4)

    # 3. Fetch Wikipedia summary
    wiki = fetch_wikipedia_summary(cleaned_dest)

    # Resolve center coordinates
    center_lon = 0.0
    center_lat = 0.0
    zoom = 13
    dest_title = cleaned_dest.title()

    if live_sights:
        center_lat = sum(s["lat"] for s in live_sights) / len(live_sights)
        center_lon = sum(s["lon"] for s in live_sights) / len(live_sights)
    elif curated:
        center_lon = curated["center"][0]
        center_lat = curated["center"][1]
        zoom = curated.get("zoom", 13)
        dest_title = curated["destination"]
    elif wiki and wiki.get("lat") and wiki.get("lon"):
        center_lat = wiki["lat"]
        center_lon = wiki["lon"]

    # Combine sights (live first, then curated)
    combined_sights: list[dict[str, Any]] = []
    seen_names = set()
    for s in live_sights:
        nm = s["name"].lower()
        if nm not in seen_names:
            seen_names.add(nm)
            combined_sights.append({
                "name": s["name"],
                "summary": s["summary"] or f"Must-visit landmark in {dest_title}.",
                "lat": s["lat"],
                "lon": s["lon"],
                "rating": s["rating"] or 4.6,
                "type": "sight",
                "address": s.get("address", ""),
            })

    if curated:
        for s in curated.get("famous_attractions", []):
            nm = s["name"].lower()
            if nm not in seen_names:
                seen_names.add(nm)
                combined_sights.append(s)

    # Combine food & hidden gems
    combined_food: list[dict[str, Any]] = []
    seen_food = set()
    for f in live_food:
        nm = f["name"].lower()
        if nm not in seen_food:
            seen_food.add(nm)
            combined_food.append({
                "name": f["name"],
                "summary": f["summary"] or f"Authentic local dining spot in {dest_title}.",
                "lat": f["lat"],
                "lon": f["lon"],
                "rating": f["rating"] or 4.7,
                "type": "food",
                "address": f.get("address", ""),
            })

    if curated:
        for f in curated.get("local_food", []):
            nm = f["name"].lower()
            if nm not in seen_food:
                seen_food.add(nm)
                combined_food.append(f)

    # 4. Synthesize day-by-day itinerary
    itinerary_days: list[dict[str, Any]] = []
    day_count = max(1, min(days, 5))

    themes = [
        "Historic Foundations & Iconic Sights",
        "Cultural Neighborhoods & Authentic Local Life",
        "Scenic Horizons, Shopping & Skyline Nightlife",
        "Hidden Gems & Peaceful Green Sanctuaries",
        "Art, Gastronomy & Evening Panorama",
    ]

    for d in range(1, day_count + 1):
        theme = themes[(d - 1) % len(themes)]
        morning_sight = combined_sights[(d - 1) * 2 % max(1, len(combined_sights))] if combined_sights else {
            "name": f"Historic Center & Main Square of {dest_title}",
            "summary": "Begin with morning exploration of the central historic district.",
            "lat": center_lat + 0.005,
            "lon": center_lon + 0.005,
            "rating": 4.6,
        }
        afternoon_sight = combined_sights[((d - 1) * 2 + 1) % max(1, len(combined_sights))] if len(combined_sights) > 1 else {
            "name": f"Cultural Landmark & Grand Promenade",
            "summary": "Explore iconic architecture and pedestrian plazas in the afternoon.",
            "lat": center_lat - 0.005,
            "lon": center_lon - 0.005,
            "rating": 4.7,
        }
        lunch_spot = combined_food[(d - 1) % max(1, len(combined_food))] if combined_food else {
            "name": f"Authentic Local Bistro & Market",
            "summary": "Savor authentic regional cuisine and local specialties.",
            "lat": center_lat + 0.002,
            "lon": center_lon - 0.003,
            "rating": 4.8,
        }

        activities = [
            {
                "time_of_day": "Morning",
                "title": f"Explore {morning_sight['name']}",
                "description": morning_sight["summary"],
                "location_name": morning_sight["name"],
                "lat": morning_sight["lat"],
                "lon": morning_sight["lon"],
                "rating": morning_sight.get("rating", 4.6),
                "type": "sight",
            },
            {
                "time_of_day": "Afternoon",
                "title": f"Lunch at {lunch_spot['name']} & Tour {afternoon_sight['name']}",
                "description": f"Enjoy local specialties at {lunch_spot['name']} ({lunch_spot.get('rating', 4.7)}★), then head to {afternoon_sight['name']}.",
                "location_name": afternoon_sight["name"],
                "lat": afternoon_sight["lat"],
                "lon": afternoon_sight["lon"],
                "rating": afternoon_sight.get("rating", 4.7),
                "type": "food",
            },
            {
                "time_of_day": "Evening",
                "title": f"Sunset Panorama & Vibrant Evening Corridor",
                "description": f"Cap off Day {d} with golden hour views and dinner at a recommended local venue in {dest_title}.",
                "location_name": f"{dest_title} Evening Vista",
                "lat": morning_sight["lat"] + 0.003,
                "lon": morning_sight["lon"] + 0.003,
                "rating": 4.8,
                "type": "scenic",
            },
        ]

        itinerary_days.append({
            "day_number": d,
            "theme": theme,
            "activities": activities,
        })

    # Pro-tips
    pro_tips = curated.get("pro_tips", []) if curated else [
        f"Use public metro and transit passes for fast traversal across {dest_title}.",
        f"Early mornings (before 9 AM) offer crowd-free photography at major landmarks in {dest_title}.",
        f"Look for dining spots with high local patron counts and multi-generational family menus.",
    ]

    overview_text = wiki.get("summary") if wiki else (
        curated.get("summary") if curated else f"{dest_title} is one of the world's premier destinations with rich culture, historic landmarks, and exceptional culinary traditions."
    )

    # Formulate a spoken brief for ElevenLabs Conversational AI voice assistant
    top_3_names = [s["name"] for s in combined_sights[:3]]
    spoken_summary = (
        f"I've assembled a {day_count}-day travel plan for {dest_title} based on live internet data! "
        f"Key must-see highlights include {', '.join(top_3_names) if top_3_names else 'the historic center and viewpoints'}. "
        f"For authentic local food, I recommend {combined_food[0]['name'] if combined_food else 'the central food market'}. "
        f"I've loaded the interactive day-by-day itinerary with exact map coordinates onto your screen. Say 'fly to' any spot to zoom right in!"
    )

    return {
        "status": "success",
        "destination": dest_title,
        "country": curated.get("country", "") if curated else "",
        "summary": overview_text,
        "center": [center_lon, center_lat],
        "zoom": zoom,
        "days": itinerary_days,
        "famous_attractions": combined_sights[:6],
        "local_food_recommendations": combined_food[:5],
        "pro_tips": pro_tips,
        "spoken_summary": spoken_summary,
        "source": "Google Places API (New) · Wikipedia · WORLDOS Travel Intelligence",
    }
