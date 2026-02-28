"""Provider search tool using Serper API.

This tool queries the Serper API (Google Search API alternative) to find 
nearby healthcare providers based on user location and optional specialty filter.
"""

import httpx
import json
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
    """Search for healthcare providers near a location using Serper API.

    Args:
        lat: Latitude of search location
        lng: Longitude of search location
        specialty: Optional specialty or type (e.g., "cardiologist", "dentist", "hospital")
        radius_m: Search radius in meters (default from settings) 
        max_results: Maximum number of results to return (default from settings)

    Returns:
        List of provider dictionaries with details

    Raises:
        ValueError: If Serper API key is not configured
        httpx.HTTPError: If API request fails
    """
    if not settings.serper_api_key:
        raise ValueError(
            "Serper API key not configured. "
            "Please set SERPER_API_KEY in your .env file."
        )

    # Use defaults from settings if not provided
    if radius_m is None:
        radius_m = settings.provider_search_radius_m
    if max_results is None:
        max_results = settings.provider_search_max_results

    # Build search query
    if specialty and specialty.lower():
        # If user specified a specialty, include it in the search
        search_query = f"{specialty} near me"
    else:
        # Default to searching for hospitals
        search_query = "hospital near me"

    # Calculate approximate zoom level from radius
    # Serper uses zoom format like "11z" 
    # Rough approximation: 5000m ≈ 13z, 10000m ≈ 12z, 20000m ≈ 11z
    zoom = max(10, min(15, int(15 - (radius_m / 5000))))

    # Build Serper API request
    url = "https://google.serper.dev/maps"
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": search_query,
        "ll": f"@{lat},{lng},{zoom}z",
        "type": "maps",
        "num": max_results
    }

    # Make API request
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Process results
    providers = []
    places = data.get("places", [])
    
    for place in places:
        place_lat = place.get("latitude")
        place_lng = place.get("longitude")
        
        # Skip places without coordinates
        if place_lat is None or place_lng is None:
            continue
            
        distance_km = calculate_distance_km(lat, lng, place_lat, place_lng)
        
        # Filter by radius
        if distance_km > (radius_m / 1000):
            continue

        rating = place.get("rating", 0.0)
        reviews = place.get("ratingCount", 0)

        providers.append(
            {
                "place_id": place.get("placeId", ""),
                "name": place.get("title", "Unknown"),
                "address": place.get("address", ""),
                "lat": place_lat,
                "lng": place_lng,
                "rating": rating,
                "reviews": reviews,
                "score": calculate_provider_score(rating, reviews),
                "types": place.get("types", []),
                "type": place.get("type", "Healthcare Provider"),
                "distance_km": distance_km,
                "phone": place.get("phoneNumber", ""),
                "website": place.get("website", ""),
                "opening_hours": place.get("openingHours", {}),
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
        place_id: Optional Place ID for more accurate link

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
        provider_type = p.get("type", "Healthcare Provider")
        if not provider_type or provider_type == "Healthcare Provider":
            types = p.get("types", [])
            if "Hospital" in types or "hospital" in [t.lower() for t in types]:
                provider_type = "Hospital"
            elif "Doctor" in types or "doctor" in [t.lower() for t in types]:
                provider_type = "Doctor"
            elif "Clinic" in types or "clinic" in [t.lower() for t in types]:
                provider_type = "Clinic"
            elif "Dentist" in types or "dentist" in [t.lower() for t in types]:
                provider_type = "Dentist"
            elif "Pharmacy" in types or "pharmacy" in [t.lower() for t in types]:
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
        )
        
        # Add phone if available
        if p.get("phone"):
            line += f"   📞 {p['phone']}\n"
        
        # Add website if available
        if p.get("website"):
            line += f"   🌐 {p['website']}\n"
            
        # Add maps link
        line += f"   [Open in Maps]({maps_link})\n"
        
        lines.append(line)

    return header + "\n".join(lines)
