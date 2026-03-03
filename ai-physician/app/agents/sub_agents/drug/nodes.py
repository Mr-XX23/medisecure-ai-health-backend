"""Drug agent nodes for Vaidya sub-agent."""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage
from app.agents.common.state import VaidyaState
from app.agents.sub_agents.drug.drug_agent import analyze_drug_interactions

logger = logging.getLogger(__name__)

async def drug_interaction_node(state: VaidyaState) -> Dict[str, Any]:
    """Check for drug-drug interactions in patient's medication list."""
    logger.info(f"Drug Interaction node for session: {state.get('session_id')}")

    if state.get("classification") == "ER_NOW":
        return {"interaction_check_done": False}

    current_medications = state.get("current_medications", [])
    med_list_from_user = state.get("med_list_from_user", [])

    all_meds = list(set(current_medications + med_list_from_user))
    if len(all_meds) < 2:
        return {"interaction_check_done": True}

    status_msg = AIMessage(content="\ud83d\udc8a Checking for potential drug interactions...")

    try:
        result = await analyze_drug_interactions(
            medications=current_medications,
            user_medications=med_list_from_user,
            patient_age=str(state.get("age", "unknown")),
            patient_conditions=state.get("chronic_conditions", []),
            patient_allergies=state.get("allergies", []),
            chief_complaint=state.get("chief_complaint") or "",
        )

        summary = result.get("summary", "")
        response_msg = AIMessage(content=f"**Drug Interaction Analysis**\\n\\n{summary}")

        return {
            "messages": [status_msg, response_msg],
            "interaction_results": result.get("interactions", []),
            "interaction_check_done": True,
            "status_events": ["STATUS:CHECKING_MEDICATIONS"],
        }
    except Exception as e:
        logger.error(f"Error in drug interaction node: {e}")
        return {"interaction_check_done": False}
