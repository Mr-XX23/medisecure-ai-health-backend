"""Symptom Analyst nodes for Vaidya sub-agent."""

import json
import logging
import re
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agents.common.state import VaidyaState
from app.agents.common.utils import strip_md_fences, is_off_topic_answer, parse_json_safely
from app.agents.sub_agents.symptom_analyst.prompts import (
    SYMPTOM_ANALYST_SYSTEM_PROMPT,
    ANALYZE_INPUT_PROMPT,
    ASSESSMENT_PROMPT,
    ASSESSMENT_FALLBACK_PROMPT,
    TRIAGE_PROMPT,
    RECOMMENDATION_PROMPT
)
from app.config.llm_config import (
    get_interview_model,
    get_triage_model,
    get_final_model
)
from app.utils.red_flags import detect_red_flags

logger = logging.getLogger(__name__)

async def analyze_input_node(state: VaidyaState) -> Dict[str, Any]:
    """Parse user message based on question context."""
    logger.info(f"Analyzing input for session: {state.get('session_id')}")

    latest_message = None
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            latest_message = msg.content
            break

    if not latest_message:
        return {"should_continue": True}

    collected = state.get("collected_fields", [])
    llm = get_interview_model()

    print("=========== Checking Data ================")
    print("chief_complaint",state.get("chief_complaint"))
    print("location",state.get("location"))
    print("duration",state.get("duration"))
    print("severity",state.get("severity"))
    print("triggers",state.get("triggers"))
    print("relievers",state.get("relievers"))
    print("associated_symptoms",state.get("associated_symptoms"))
    print("last_question_type",state.get("last_question_type"))
    
    # Pass all clinical fields and last_question_type for context
    prompt = ANALYZE_INPUT_PROMPT.format(
        message=latest_message,
        chief_complaint=state.get("chief_complaint") or "null",
        location=state.get("location") or "null",
        duration=state.get("duration") or "null",
        severity=state.get("severity") or "null",
        triggers=state.get("triggers") or "null",
        relievers=state.get("relievers") or "null",
        associated_symptoms=", ".join(state.get("associated_symptoms", [])) or "[]",
        last_question_type=state.get("last_question_type") or "null"
    )

    print("SYMPTOM ANALYST INTENT PROMPT", prompt)

    response = await llm.ainvoke([SystemMessage(content=SYMPTOM_ANALYST_SYSTEM_PROMPT),HumanMessage(content=prompt)])

    print("SYMPTOM ANALYST RESPONSE FOR INTENT_ANALYSIS", response.content)

    try:
        content = str(response.content)
        extracted = parse_json_safely(content)
        
        if not extracted:
            logger.error("JSON extraction failed, skipping updates.")
            return {"should_continue": True}
            
        updates = {}
        new_collected = list(collected)
        
        # Merge Intelligence: Protect established fields.
        for field in ["chief_complaint", "location", "duration", "severity", "triggers", "relievers"]:
            new_val = extracted.get(field)
            existing_val = state.get(field)
            
            # If we have a truly new value
            if new_val and str(new_val).strip().lower() not in ["null", "none", ""]:
                # Logic: If existing is generic ("pain") or null, or if new info is fundamentally different, update.
                is_generic = existing_val and str(existing_val).lower() in ["pain", "symptom", "problem"]
                if not existing_val or is_generic or (new_val != existing_val):
                    updates[field] = new_val
                    if field not in new_collected:
                        new_collected.append(field)
            elif existing_val:
                # Keep existing value if LLM returned null for an already known field
                updates[field] = existing_val
        
        # Calculate if all required info is gathered (Golden 4)
        required = ["chief_complaint", "location", "duration", "severity"]
        all_present = all(r in new_collected for r in required)
        updates["golden_4_complete"] = all_present
        
        return updates
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"should_continue": True}

async def red_flag_check_node(state: VaidyaState) -> Dict[str, Any]:
    """Check for emergency red flags."""
    user_messages = [msg.content for msg in state.get("messages", []) if isinstance(msg, HumanMessage)]
    combined_text = " ".join(filter(None, map(str, user_messages)))
    has_red_flags, detected_categories = detect_red_flags(combined_text)
    if has_red_flags:
        return {"red_flags_detected": detected_categories, "current_stage": "emergency"}
    return {}

async def emergency_node(state: VaidyaState) -> Dict[str, Any]:
    """Handle emergency triage trigger."""
    red_flags = state.get("red_flags_detected", [])
    return {
        "classification": "ER_NOW",
        "urgency_score": 10,
        "emergency_mode": True,
        "emergency_type": red_flags[0] if red_flags else "medical_emergency",
        "current_stage": "complete"
    }

async def assessment_node(state: VaidyaState) -> Dict[str, Any]:
    """Generate differential diagnosis."""
    llm = get_triage_model()
    prompt = ASSESSMENT_PROMPT.format(
        chief_complaint=state.get("chief_complaint", "unknown"),
        location=state.get("location", "not specified"),
        duration=state.get("duration", "not specified"),
        severity=state.get("severity", "not specified"),
        triggers=state.get("triggers", "not specified"),
        associated_symptoms=", ".join(state.get("associated_symptoms", [])),
        history_context=state.get("history_summary") or "None"
    )

    print("SYMPTOM ANALYST ASSESSMENT PROMPT",prompt)

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    print("SYMPTOM ANALYST RESPONSE FOR ASSESSMENT",response)

    try:
        assessment = json.loads(strip_md_fences(str(response.content)))
        return {"differential_diagnosis": [d["condition"] for d in assessment.get("differential", [])]}
    except:
        return {"differential_diagnosis": ["Assessment unavailable"]}

async def triage_node(state: VaidyaState) -> Dict[str, Any]:
    """Classify triage level."""
    llm = get_triage_model()
    prompt = TRIAGE_PROMPT.format(
        chief_complaint=state.get("chief_complaint", "unknown"),
        severity=state.get("severity", "not specified"),
        duration=state.get("duration", "not specified"),
        red_flags=", ".join(state.get("red_flags_detected", [])) or "none",
        differential=", ".join(state.get("differential_diagnosis", [])),
        history_context=state.get("history_summary") or "None"
    )

    print("SYMPTOM ANALYST TRIAGE PROMPT",prompt)

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    print("SYMPTOM ANALYST RESPONSE FOR TRIAGE",response)
    
    try:
        triage = json.loads(strip_md_fences(str(response.content)))
        return {
            "classification": triage.get("classification"),
            "urgency_score": triage.get("urgency_score"),
            "recommendations": triage.get("recommendations", [])
        }
    except:
        return {"classification": "GP_SOON", "urgency_score": "5"}

async def gather_info_node(state: VaidyaState) -> Dict[str, Any]:
    """Check if all necessary information is gathered."""
    collected = state.get("collected_fields", [])
    required = ["chief_complaint", "location", "duration", "severity"]
    all_present = all(r in collected for r in required)
    
    if all_present:
        print("SYMPTOM ANALYST GOLDEN 4 COMPLETE",all_present)
        return {"golden_4_complete": True, "should_continue": True}
    print("SYMPTOM ANALYST GOLDEN 4 COMPLETE",all_present)
    return {"golden_4_complete": False, "should_continue": True}
