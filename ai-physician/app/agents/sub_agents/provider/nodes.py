"""Provider Locator nodes for Vaidya sub-agent."""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage
from app.agents.common.state import VaidyaState
from app.agents.sub_agents.provider.prompts import PROVIDER_RESPONSE_PROMPT
from app.config.llm_config import get_final_model
from app.tools.provider_search import search_providers, format_provider_message

logger = logging.getLogger(__name__)

async def provider_locator_node(state: VaidyaState) -> Dict[str, Any]:
    """Locate nearby healthcare providers."""
    logger.info("\ud83d\udd0d Provider Locator Agent: Starting provider search")
    status_events = ["STATUS:SEARCHING_PROVIDERS"]

    try:
        user_location = state.get("user_location")
        if not user_location:
            return {
                "messages": [AIMessage(content="Please enable location sharing to find nearby providers.")],
                "provider_search_done": False,
            }

        lat, lng = user_location.get("lat"), user_location.get("lng")
        provider_query = state.get("provider_query")

        providers = await search_providers(lat=lat, lng=lng, specialty=provider_query)
        raw_message = format_provider_message(providers, provider_query)

        llm = get_final_model()
        provider_prompt = PROVIDER_RESPONSE_PROMPT.format(
            triage_classification=state.get("classification", "GP_SOON"),
            chief_complaint=state.get("chief_complaint", "not specified"),
            patient_location=user_location.get("city") or f"{lat}, {lng}",
            urgency_score=state.get("urgency_score", 5),
            provider_data=raw_message,
        )
        llm_response = await llm.ainvoke([HumanMessage(content=provider_prompt)])
        
        return {
            "messages": [AIMessage(content=str(llm_response.content))],
            "nearby_providers": providers,
            "provider_search_done": True,
            "status_events": status_events,
        }
    except Exception as e:
        logger.error(f"Error in provider locator: {e}")
        return {"provider_search_done": False}
