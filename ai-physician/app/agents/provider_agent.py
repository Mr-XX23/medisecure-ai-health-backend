"""Provider Locator Agent.

This agent finds nearby healthcare providers based on user location
and optional specialty filter. It ranks results by quality and proximity.
"""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.state import SymptomCheckState
from app.agents.prompts import PROVIDER_RESPONSE_PROMPT
from app.config.llm_config import get_final_model
from app.tools.provider_search import (
    search_providers,
    format_provider_message,
)

logger = logging.getLogger(__name__)


async def provider_locator_node(state: SymptomCheckState) -> Dict[str, Any]:
    """Locate nearby healthcare providers based on user location and preferences.

    This node:
    1. Checks if user location is available
    2. Extracts any specialty/intent from provider_query
    3. Calls Google Places API to find providers
    4. Ranks results by quality score and distance
    5. Formats results into a user-friendly message

    Args:
        state: Current symptom check state

    Returns:
        Updated state with provider results
    """
    logger.info("🔍 Provider Locator Agent: Starting provider search")

    # Emit status event for frontend
    status_events = ["STATUS:SEARCHING_PROVIDERS"]

    try:
        # Check if location is provided
        user_location = state.get("user_location")
        if not user_location:
            logger.warning("No user location provided")
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "To find nearby healthcare providers, I need your location. "
                            "Please enable location sharing in your browser, or let me know "
                            "your city/area and I'll help you search."
                        )
                    )
                ],
                "provider_search_done": False,
            }

        # Extract coordinates
        lat = user_location.get("lat")
        lng = user_location.get("lng")

        if lat is None or lng is None:
            logger.error(f"Invalid location format: {user_location}")
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "The location information seems incomplete. "
                            "Please try sharing your location again or tell me your city."
                        )
                    )
                ],
                "provider_search_done": False,
            }

        # Get specialty filter if provided
        provider_query = state.get("provider_query")

        logger.info(
            f"Searching for providers at ({lat}, {lng})"
            + (f" with specialty: {provider_query}" if provider_query else "")
        )

        # Search for providers
        providers = await search_providers(lat=lat, lng=lng, specialty=provider_query)

        logger.info(f"Found {len(providers)} providers")

        # Format raw provider data for the LLM
        raw_message = format_provider_message(providers, provider_query)

        # Synthesise a clinical response via LLM using full patient context
        classification = state.get("classification", "GP_SOON")
        urgency_score = state.get("urgency_score", 5)
        chief_complaint = state.get("chief_complaint", "not specified")
        user_location_label = (
            user_location.get("city")
            or user_location.get("address")
            or f"{lat:.3f}, {lng:.3f}"
        )

        try:
            llm = get_final_model()
            provider_prompt = PROVIDER_RESPONSE_PROMPT.format(
                triage_classification=classification,
                chief_complaint=chief_complaint,
                patient_location=user_location_label,
                urgency_score=urgency_score,
                provider_data=raw_message,
            )
            llm_response = await llm.ainvoke([HumanMessage(content=provider_prompt)])
            message_content = (
                llm_response.content
                if isinstance(llm_response.content, str)
                else str(llm_response.content)
            )
        except Exception as llm_err:
            logger.error(f"Provider LLM synthesis failed: {llm_err}")
            message_content = raw_message  # graceful degradation

        return {
            "messages": [AIMessage(content=message_content)],
            "nearby_providers": providers,
            "provider_search_done": True,
            "status_events": status_events,
        }

    except ValueError as e:
        # Handle configuration or API errors
        logger.error(f"Configuration error in provider search: {e}")
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"I encountered an issue searching for providers: {str(e)}. "
                        "Please contact support if this issue persists."
                    )
                )
            ],
            "provider_search_done": False,
            "error": str(e),
        }

    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Error in provider locator: {e}", exc_info=True)
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I'm having trouble searching for providers right now. "
                        "Please try again in a moment, or contact support if the issue persists."
                    )
                )
            ],
            "provider_search_done": False,
            "error": str(e),
        }


def extract_provider_intent(user_message: str) -> tuple[bool, str | None]:
    """Detect if user is asking for provider recommendations.

    This is a simple keyword-based detector. In production, you might
    use the LLM to classify intent more accurately.

    Args:
        user_message: User's message text

    Returns:
        Tuple of (is_provider_request, specialty)
        - is_provider_request: True if user wants provider recommendations
        - specialty: Extracted specialty/type if any (e.g., "cardiologist", "dentist")
    """
    message_lower = user_message.lower()

    # Keywords that indicate provider search intent
    provider_keywords = [
        "find doctor",
        "find hospital",
        "near me",
        "nearby",
        "closest",
        "where can i",
        "recommend a doctor",
        "recommend a hospital",
        "find clinic",
        "locate provider",
        "provider near",
        "hospital near",
        "doctor near",
    ]

    is_request = any(keyword in message_lower for keyword in provider_keywords)

    if not is_request:
        return False, None

    # Try to extract specialty
    specialties = [
        "cardiologist",
        "dermatologist",
        "dentist",
        "pediatrician",
        "psychiatrist",
        "orthopedist",
        "ophthalmologist",
        "neurologist",
        "gynecologist",
        "urologist",
        "oncologist",
        "endocrinologist",
        "gastroenterologist",
        "pulmonologist",
        "rheumatologist",
        "allergist",
        "surgeon",
        "emergency room",
        "urgent care",
        "primary care",
        "general practitioner",
        "gp",
        "hospital",
        "clinic",
        "pharmacy",
    ]

    for specialty in specialties:
        if specialty in message_lower:
            return True, specialty

    return True, None
