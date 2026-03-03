"""ER Emergency nodes for Vaidya sub-agent."""

import asyncio
import logging
from typing import Dict, Any
from app.agents.common.state import VaidyaState
from app.tools.er_search import search_er_hospitals, get_regional_emergency_numbers

logger = logging.getLogger(__name__)

async def er_emergency_node(state: VaidyaState) -> Dict[str, Any]:
    """ER Emergency Agent node for location-aware hospital search."""
    logger.info(f"\ud83d\udea8 ER Emergency Agent activated for session: {state.get('session_id')}")

    if state.get("er_search_triggered") and state.get("er_hospitals"):
        return {"status_events": ["STATUS:EMERGENCY_DETECTED"], "should_continue": True}

    status_events = ["STATUS:EMERGENCY_DETECTED"]
    user_location = state.get("user_location")
    er_hospitals = []
    er_emergency_numbers = {}
    location_timeout = False

    if user_location and isinstance(user_location, dict):
        lat, lng = user_location.get("lat"), user_location.get("lng")
        if lat is not None and lng is not None:
            status_events.append("STATUS:ER_SEARCH")
            try:
                er_hospitals, er_emergency_numbers = await asyncio.gather(
                    search_er_hospitals(lat, lng),
                    get_regional_emergency_numbers(lat, lng)
                )
                if er_hospitals: status_events.append("STATUS:ER_FOUND")
            except Exception as e:
                logger.error(f"ER parallel lookup failed: {e}")
                status_events.append("STATUS:ER_SEARCH_FAILED")
        else: location_timeout = True
    else: location_timeout = True

    if not er_emergency_numbers:
        er_emergency_numbers = {"ambulance": "112", "police": "112", "fire": "112", "general": "112"}

    return {
        "er_hospitals": er_hospitals,
        "er_emergency_numbers": er_emergency_numbers,
        "er_search_triggered": True,
        "location_timeout": location_timeout,
        "status_events": status_events,
        "should_continue": True,
    }
