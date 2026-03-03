"""History agent nodes for Vaidya sub-agent."""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage
from app.agents.common.state import VaidyaState
from app.agents.sub_agents.history.history_agent import analyze_medical_history

logger = logging.getLogger(__name__)

async def history_node(state: VaidyaState) -> Dict[str, Any]:
    """Analyze patient's medical history and correlate with current symptoms."""
    logger.info(f"History analysis node for session: {state.get('session_id')}")

    if state.get("history_analyzed"):
        return {"should_continue": True}

    patient_id = state.get("patient_id") or state.get("user_id") or "patient_001"

    try:
        current_symptoms = {
            "location": state.get("location"),
            "duration": state.get("duration"),
            "severity": state.get("severity"),
            "triggers": state.get("triggers"),
        }

        history_data = await analyze_medical_history(
            patient_id=patient_id,
            chief_complaint=state.get("chief_complaint"),
            current_symptoms=current_symptoms,
        )

        status_message = AIMessage(
            content="\u2713 Reviewing your medical history and current medications..."
        )

        demographics = history_data.get("demographics", {})
        
        return {
            "messages": [status_message],
            "patient_id": patient_id,
            "age": demographics.get("age"),
            "sex": demographics.get("gender"),
            "history_summary": history_data.get("history_summary"),
            "chronic_conditions": history_data.get("chronic_conditions", []),
            "recent_labs": history_data.get("recent_labs", []),
            "current_medications": history_data.get("current_medications", []),
            "allergies": history_data.get("allergies", []),
            "risk_level": history_data.get("risk_level", "UNKNOWN"),
            "history_analyzed": True,
            "status_events": ["STATUS:CHECKING_HISTORY"],
            "should_continue": True,
        }
    except Exception as e:
        logger.error(f"Error analyzing medical history: {str(e)}")
        return {
            "history_analyzed": True,
            "history_summary": "Unable to retrieve medical history.",
            "should_continue": True,
        }
