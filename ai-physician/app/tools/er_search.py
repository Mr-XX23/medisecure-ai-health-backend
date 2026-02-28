"""ER Emergency Search Tool.

Dedicated tool for regional emergency numbers when an ER_NOW triage is triggered.
Note: Google Maps integration has been removed. This module now provides only
regional emergency numbers and formatted prompts for ER responses.
"""

import logging
from typing import Dict, List
from app.config.settings import settings

logger = logging.getLogger(__name__)

_EMERGENCY_NUMBERS: Dict[str, Dict[str, str]] = {
    "NP": {"ambulance": "102", "police": "100", "fire": "101", "general": "102"},
    "IN": {"ambulance": "108", "police": "100", "fire": "101", "general": "112"},
    "US": {"ambulance": "911", "police": "911", "fire": "911", "general": "911"},
    "GB": {"ambulance": "999", "police": "999", "fire": "999", "general": "999"},
    "CA": {"ambulance": "911", "police": "911", "fire": "911", "general": "911"},
    "AU": {"ambulance": "000", "police": "000", "fire": "000", "general": "000"},
    "DE": {"ambulance": "112", "police": "110", "fire": "112", "general": "112"},
    "FR": {"ambulance": "15", "police": "17", "fire": "18", "general": "112"},
    "PK": {"ambulance": "115", "police": "15", "fire": "16", "general": "115"},
    "BD": {"ambulance": "199", "police": "999", "fire": "199", "general": "999"},
    "CN": {"ambulance": "120", "police": "110", "fire": "119", "general": "120"},
    "JP": {"ambulance": "119", "police": "110", "fire": "119", "general": "119"},
    "SG": {"ambulance": "995", "police": "999", "fire": "995", "general": "995"},
    "MY": {"ambulance": "999", "police": "999", "fire": "994", "general": "999"},
    "LK": {"ambulance": "110", "police": "119", "fire": "111", "general": "110"},
    "PH": {"ambulance": "911", "police": "911", "fire": "911", "general": "911"},
    "NG": {"ambulance": "199", "police": "199", "fire": "199", "general": "199"},
    "ZA": {"ambulance": "10177", "police": "10111", "fire": "10111", "general": "112"},
    "BR": {"ambulance": "192", "police": "190", "fire": "193", "general": "192"},
    "MX": {"ambulance": "065", "police": "060", "fire": "068", "general": "911"},
    # EU fallback
    "EU": {"ambulance": "112", "police": "112", "fire": "112", "general": "112"},
}

_DEFAULT_EMERGENCY = {
    "ambulance": "112",
    "police": "112",
    "fire": "112",
    "general": "112",
}

async def search_er_hospitals(
    lat: float,
    lng: float,
    min_results: int = 3,
) -> List[Dict]:
    """
    Search for verified ER hospitals near (lat, lng).

    NOTE: Google Maps API integration has been removed.
          This function now returns an empty list.
          The frontend should use Google Maps directly or implement
          alternative location-based hospital search.

    Args:
        lat: Latitude coordinate
        lng: Longitude coordinate
        min_results: Minimum results requested (deprecated)

    Returns:
        Empty list (no local hospital search available)
    """
    logger.info("ER hospital search unavailable — Google Maps integration removed")
    return []

async def get_regional_emergency_numbers(lat: float, lng: float) -> Dict[str, str]:
    """
    Return regional emergency numbers.

    NOTE: Country detection via Google Geocoding has been removed.
          This function now returns default international emergency numbers (112).

    Args:
        lat: Latitude coordinate (currently unused)
        lng: Longitude coordinate (currently unused)

    Returns:
        Dictionary with emergency numbers (ambulance, police, fire, general)
    """
    logger.info(
        "Returning default emergency numbers (Google reverse-geocoding removed)"
    )
    return _DEFAULT_EMERGENCY.copy()

def format_er_hospitals_for_prompt(
    hospitals: List[Dict], emergency_numbers: Dict
) -> str:
    """
    Format ER hospital results and emergency numbers into a structured string
    for injection into the ER_RESPONSE_PROMPT.

    NOTE: Currently returns only emergency numbers since hospital search
          requires Google Maps integration (removed).
    """
    ambulance = emergency_numbers.get("ambulance", "112")
    police = emergency_numbers.get("police", "112")
    fire = emergency_numbers.get("fire", "112")

    return (
        f"EMERGENCY NUMBERS:\n"
        f"🚑 AMBULANCE: {ambulance}\n"
        f"🚔 POLICE: {police}\n"
        f"🚒 FIRE: {fire}\n\n"
        f"⚠️ Hospital location search unavailable.\n"
        f"Please call the ambulance number or search Google Maps for nearby hospitals."
    )
