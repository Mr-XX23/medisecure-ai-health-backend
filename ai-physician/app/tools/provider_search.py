"""Provider search tool using Google Places API.

This tool queries the Google Places API to find nearby healthcare providers
based on user location and optional specialty filter.
"""

import httpx
from math import log, radians, cos, sin, asin, sqrt
from typing import Optional, List, Dict
from app.config.settings import settings


def calculate_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great circle distance between two points in kilometers.

    Uses the Haversine formula.

    Args:
        lat1: Latitude of first point
        lng1: Longitude of first point
        lat2: Latitude of second point
        lng2: Longitude of second point

    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])

    # Haversine formula
    dlng = lng2 - lng1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))

    # Radius of earth in kilometers
    r = 6371

    return round(c * r, 2)


def calculate_provider_score(rating: float, reviews: int) -> float:
    """Calculate a quality score for a provider.

    Uses rating weighted by log of review count to favor both
    high-rated and well-reviewed providers.

    Args:
        rating: Average rating (0-5 scale)
        reviews: Total number of reviews

    Returns:
        Quality score (higher is better)
    """
    return round(rating * log(reviews + 1), 2)


async def search_providers(
    lat: float,
    lng: float,
    specialty: Optional[str] = None,
    radius_m: Optional[int] = None,
    max_results: Optional[int] = None,
) -> List[Dict]:
    """Search for healthcare providers near a location.

    Args:
        lat: Latitude of search location
        lng: Longitude of search location
        specialty: Optional specialty or type (e.g., "cardiologist", "dentist")
        radius_m: Search radius in meters (default from settings)
        max_results: Maximum number of results to return (default from settings)

    Returns:
        List of provider dictionaries with details

    Raises:
        ValueError: If Google Maps API key is not configured
        httpx.HTTPError: If API request fails
    """
    if not settings.google_maps_api_key:
        raise ValueError(
            "Google Maps API key not configured. "
            "Please set GOOGLE_MAPS_API_KEY in your .env file."
        )

    # Use defaults from settings if not provided
    if radius_m is None:
        radius_m = settings.provider_search_radius_m
    if max_results is None:
        max_results = settings.provider_search_max_results

    # Build API request
    base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "key": settings.google_maps_api_key,
    }

    # Choose type and keyword based on specialty
    if specialty and specialty.lower():
        # If user specified a specialty, search for doctors with that keyword
        params["type"] = "doctor"
        params["keyword"] = specialty.lower()
    else:
        # Default to searching for hospitals
        params["type"] = "hospital"

    # Make API request
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # Check for API errors
    if data.get("status") not in ["OK", "ZERO_RESULTS"]:
        error_msg = data.get("error_message", data.get("status"))
        raise ValueError(f"Google Places API error: {error_msg}")

    # Process results
    providers = []
    for place in data.get("results", []):
        rating = place.get("rating", 0.0)
        reviews = place.get("user_ratings_total", 0)

        place_lat = place["geometry"]["location"]["lat"]
        place_lng = place["geometry"]["location"]["lng"]
        distance_km = calculate_distance_km(lat, lng, place_lat, place_lng)

        providers.append(
            {
                "place_id": place["place_id"],
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "lat": place_lat,
                "lng": place_lng,
                "rating": rating,
                "reviews": reviews,
                "score": calculate_provider_score(rating, reviews),
                "types": place.get("types", []),
                "distance_km": distance_km,
            }
        )

    # Sort by quality score (descending), then by distance (ascending)
    providers.sort(key=lambda p: (-p["score"], p["distance_km"]))

    # Return top results
    return providers[:max_results]


def generate_maps_link(lat: float, lng: float, place_id: Optional[str] = None) -> str:
    """Generate a Google Maps link for a location or place.

    Args:
        lat: Latitude
        lng: Longitude
        place_id: Optional Google Place ID for more accurate link

    Returns:
        Google Maps URL
    """
    if place_id:
        return f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    else:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def format_provider_message(
    providers: List[Dict], specialty: Optional[str] = None
) -> str:
    """Format provider search results into a user-friendly message.

    Args:
        providers: List of provider dictionaries
        specialty: Optional specialty that was searched

    Returns:
        Formatted message string
    """
    if not providers:
        if specialty:
            return f"No {specialty} providers found near your location. Try expanding your search radius or searching for a different specialty."
        else:
            return "No healthcare providers found near your location. Please try a different location or expand your search radius."

    # Build header
    if specialty:
        header = f"Here are the top {specialty} providers near you:\n\n"
    else:
        header = "Here are the top healthcare providers near you:\n\n"

    # Build provider list
    lines = []
    for i, p in enumerate(providers, 1):
        # Extract primary type
        provider_type = "Healthcare Provider"
        types = p.get("types", [])
        if "hospital" in types:
            provider_type = "Hospital"
        elif "doctor" in types:
            provider_type = "Doctor"
        elif "clinic" in types or "health" in types:
            provider_type = "Clinic"
        elif "dentist" in types:
            provider_type = "Dentist"
        elif "pharmacy" in types:
            provider_type = "Pharmacy"

        # Format rating
        rating_str = f"⭐{p['rating']:.1f}" if p["rating"] > 0 else "No rating"
        review_str = f"({p['reviews']} reviews)" if p["reviews"] > 0 else ""

        # Build maps link
        maps_link = generate_maps_link(p["lat"], p["lng"], p.get("place_id"))

        # Format line
        line = (
            f"{i}. **{p['name']}** ({provider_type})\n"
            f"   📍 {p['address']} — {p['distance_km']} km away\n"
            f"   {rating_str} {review_str}\n"
            f"   [Open in Maps]({maps_link})\n"
        )
        lines.append(line)

    return header + "\n".join(lines)
