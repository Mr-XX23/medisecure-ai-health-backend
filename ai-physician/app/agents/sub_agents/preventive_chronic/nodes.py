"""Preventive/Chronic Care nodes for Vaidya sub-agent."""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage
from app.agents.common.state import VaidyaState
from app.agents.sub_agents.preventive_chronic.preventive_chronic_agent import (
    analyze_preventive_care,
    format_preventive_recommendations,
    format_chronic_care_plans,
)

logger = logging.getLogger(__name__)

async def preventive_chronic_node(state: VaidyaState) -> Dict[str, Any]:
    """
    Generate preventive care recommendations and chronic disease management plans.
    """
    logger.info(f"Preventive/Chronic Care node for session: {state.get('session_id')}")

    if state.get("classification") == "ER_NOW":
        return {
            "preventive_recommendations": [],
            "chronic_care_plans": [],
            "preventive_care_analyzed": False,
        }

    status_msg = AIMessage(
        content="\ud83d\udcad Analyzing preventive care needs and chronic disease management..."
    )

    try:
        result = await analyze_preventive_care(
            age=state.get("age"),
            sex=state.get("sex"),
            chronic_conditions=state.get("chronic_conditions", []),
            recent_labs=state.get("recent_labs", []),
            current_medications=state.get("current_medications", []),
            history_summary=state.get("history_summary"),
            risk_level=state.get("risk_level"),
        )

        prev_recommendations = result.get("preventive_recommendations", [])
        chronic_plans = result.get("chronic_care_plans", [])
        summary = result.get("summary", "")

        # Format for response
        formatted_text = []
        if summary:
            formatted_text.append(f"**\ud83c\udf1f Preventive Care & Chronic Management Summary:**\\n{summary}\\n")
        
        if prev_recommendations:
            formatted_text.append(format_preventive_recommendations(prev_recommendations))
        if chronic_plans:
            formatted_text.append(format_chronic_care_plans(chronic_plans))

        response_content = "\\n".join(formatted_text) if formatted_text else "No specific recommendations at this time."
        response_msg = AIMessage(content=response_content)

        return {
            "messages": [status_msg, response_msg],
            "preventive_recommendations": prev_recommendations,
            "chronic_care_plans": chronic_plans,
            "preventive_care_analyzed": True,
            "status_events": ["STATUS:PREVENTIVE_CARE"],
        }

    except Exception as e:
        logger.error(f"Error in preventive/chronic care node: {e}")
        return {"preventive_care_analyzed": False}
