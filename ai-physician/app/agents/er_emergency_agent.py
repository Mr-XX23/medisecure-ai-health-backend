"""ER Emergency Agent — Phase 2: Location acquisition + Phase 3: Parallel data gathering.

This node activates immediately after emergency_node sets emergency_mode=True.
It is responsible for:
  1. Emitting STATUS:EMERGENCY_DETECTED so the frontend shows the red alert banner.
  2. Reading user_location from state (sent by frontend on message).
  3. Running two parallel lookups:
       - search_er_hospitals(lat, lng)
       - get_regional_emergency_numbers(lat, lng)
  4. Caching results in state so final_responder_node can synthesise the ER response.
  5. Handling all edge cases: no location, API failures, repeat ER triggers.
"""

import asyncio
import logging
from typing import Dict, Any

from app.agents.state import SymptomCheckState
from app.tools.er_search import search_er_hospitals, get_regional_emergency_numbers

logger = logging.getLogger(__name__)


async def er_emergency_node(state: SymptomCheckState) -> Dict[str, Any]:
    """
    ER Emergency Agent node.

    This node runs AFTER emergency_node has set classification=ER_NOW and
    emergency_mode=True.  It performs the location-aware hospital search
    so that final_responder can include real, actionable ER recommendations.

    Args:
        state: Current SymptomCheckState (must have emergency_mode=True)

    Returns:
        State update with er_hospitals, er_emergency_numbers, er_search_triggered
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"🚨 ER Emergency Agent activated for session: {session_id}")

    # ─── Phase 1: Check if already searched (prevent duplicate work on re-trigger) ───
    if state.get("er_search_triggered") and state.get("er_hospitals"):
        logger.info("ER search already completed — using cached hospital data")
        return {
            "status_events": ["STATUS:EMERGENCY_DETECTED"],
            "should_continue": True,
        }

    # ─── Phase 2: Emit detection status event ────────────────────────────────────────
    # STATUS:EMERGENCY_DETECTED causes the frontend to show the red alert banner.
    status_events = ["STATUS:EMERGENCY_DETECTED"]

    # ─── Phase 3: Acquire location ────────────────────────────────────────────────────
    user_location = state.get("user_location")
    er_hospitals = []
    er_emergency_numbers = {}
    location_timeout = False

    if user_location and isinstance(user_location, dict):
        lat = user_location.get("lat")
        lng = user_location.get("lng")

        if lat is not None and lng is not None:
            logger.info(
                f"Location available: lat={lat}, lng={lng} — searching ER hospitals"
            )
            status_events.append("STATUS:ER_SEARCH")

            # ─── Phase 3: Parallel lookups ──────────────────────────────────────────
            try:
                hospitals_task = search_er_hospitals(lat, lng)
                numbers_task = get_regional_emergency_numbers(lat, lng)

                er_hospitals, er_emergency_numbers = await asyncio.gather(
                    hospitals_task, numbers_task, return_exceptions=False
                )

                if er_hospitals:
                    logger.info(f"Found {len(er_hospitals)} verified ER hospitals")
                    status_events.append("STATUS:ER_FOUND")
                else:
                    logger.warning(
                        "No ER hospitals found — will use national number fallback"
                    )

            except Exception as e:
                logger.error(f"ER parallel lookup failed: {e}", exc_info=True)
                er_hospitals = []
                er_emergency_numbers = {}
                status_events.append("STATUS:ER_SEARCH_FAILED")
        else:
            logger.warning("user_location dict missing lat/lng — location timeout path")
            location_timeout = True
    else:
        # No location provided — frontend will trigger geolocation and resend.
        # For now, fall back to national numbers only so the response isn't empty.
        logger.info("No user_location in state — using location timeout fallback")
        location_timeout = True
        status_events.append("STATUS:WAITING_LOCATION")

    # ─── Phase 4: Normalise edge cases ────────────────────────────────────────────────
    # If location timed out or all hospitals closed, use default emergency numbers
    if not er_emergency_numbers:
        er_emergency_numbers = {
            "ambulance": "112",
            "police": "112",
            "fire": "112",
            "general": "112",
        }

    # If all hospitals are "May be closed", still return them — never show empty list
    # (The ER prompt will add ⚠️ notes per hospital)

    return {
        "er_hospitals": er_hospitals,
        "er_emergency_numbers": er_emergency_numbers,
        "er_search_triggered": True,
        "location_timeout": location_timeout,
        "status_events": status_events,
        "should_continue": True,
    }
