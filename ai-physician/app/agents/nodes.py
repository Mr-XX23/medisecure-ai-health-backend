"""LangGraph node functions for Symptom Analyst workflow."""

from app.agents.state import SymptomCheckState
from app.agents.prompts import (
    GREETING_PROMPT,
    ANALYZE_INPUT_PROMPT,
    EMERGENCY_PROMPT,
    ASSESSMENT_PROMPT,
    TRIAGE_PROMPT,
    RECOMMENDATION_PROMPT,
    SYMPTOM_ANALYST_SYSTEM_PROMPT,
    FINAL_RESPONDER_PROMPT,
    SUMMARIZATION_PROMPT,
)
from app.agents.preventive_chronic_agent import (
    analyze_preventive_care,
    format_preventive_recommendations,
    format_chronic_care_plans,
)
from app.agents.drug_agent import (
    analyze_drug_interactions,
    should_check_interactions,
)
from app.utils.red_flags import detect_red_flags, get_red_flag_description
from app.config.llm_config import (
    get_interview_model,
    get_triage_model,
    get_final_model,
    get_supervisor_model,
)
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json
import logging
import re

logger = logging.getLogger(__name__)


def _strip_md_fences(text: str) -> str:
    """Strip markdown code fences that the LLM sometimes wraps JSON in.

    Handles patterns like:
        ```json\n{...}\n```
        ```\n{...}\n```
    """
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


_OFF_TOPIC_PATTERNS = re.compile(
    r"\b(how|what|why|when|where|can you|could you|please|help|understand|"
    r"manage|tell me|explain|advice|information|suggest|recommend|"
    r"from scratch|everything|general|overview|tips|ways to)\b",
    re.IGNORECASE,
)


def _is_off_topic_answer(message: str) -> bool:
    """Return True when the user's message looks like an informational request
    rather than a direct answer to a clinical question (location, duration, etc.).

    Triggers on: question marks, interrogative/imperative opener words, or any
    pattern from _OFF_TOPIC_PATTERNS.
    """
    msg = message.strip()
    if "?" in msg:
        return True
    if _OFF_TOPIC_PATTERNS.search(msg):
        return True
    return False


async def greeting_node(state: SymptomCheckState) -> dict:
    """Greet the user and explain the process."""
    logger.info(f"Greeting node for session: {state['session_id']}")

    existing_messages = state.get("messages", [])
    for msg in existing_messages:
        if isinstance(msg, AIMessage):
            logger.info("Greeting already sent, skipping")
            return {
                "current_stage": "gathering",
                "should_continue": True,
            }

    # Phi-4-mini-instruct (3.8B) - Golden 4 Interview: ultra-fast conversational greeting
    llm = get_interview_model()

    system_msg = SystemMessage(
        content=SYMPTOM_ANALYST_SYSTEM_PROMPT.format(
            stage="greeting", golden_4_complete=False
        )
    )

    response = await llm.ainvoke([system_msg, HumanMessage(content=GREETING_PROMPT)])

    return {
        "messages": [response],
        "current_stage": "gathering",
        "should_continue": True,
    }


async def analyze_input_node(state: SymptomCheckState) -> dict:
    """Parse user message based on question context (context-aware interpretation)."""
    logger.info(f"Analyzing input for session: {state['session_id']}")

    latest_message = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            latest_message = msg.content
            break

    if not latest_message:
        return {"should_continue": True}

    last_question = state.get("last_question_type")
    collected = state.get("collected_fields", [])

    logger.info(
        f"Analyzing with context: last_question={last_question}, collected={collected}"
    )

    if last_question and _is_off_topic_answer(latest_message):
        logger.info(
            f"Message looks off-topic for {last_question}, falling through to general extraction "
            f"(message: {latest_message[:60]!r})"
        )
        # Clear the stale question context so the next turn starts fresh
        last_question = None

    if last_question == "ASK_SEVERITY":
        try:
            severity = int(latest_message.strip())
            if 1 <= severity <= 10:
                logger.info(f"Extracted severity: {severity}")
                return {
                    "severity": severity,
                    "collected_fields": list(set(collected + ["severity"])),
                    "last_question_type": None,  # Clear question context
                    "should_continue": True,
                }
        except ValueError:
            numbers = re.findall(r"\b([1-9]|10)\b", latest_message)
            if numbers:
                severity = int(numbers[0])
                logger.info(f"Extracted severity from text: {severity}")
                return {
                    "severity": severity,
                    "collected_fields": list(set(collected + ["severity"])),
                    "last_question_type": None,
                    "should_continue": True,
                }

    elif last_question == "ASK_LOCATION":
        logger.info(f"Extracted location: {latest_message}")
        return {
            "location": latest_message,
            "collected_fields": list(set(collected + ["location"])),
            "last_question_type": None,
            "should_continue": True,
        }

    elif last_question == "ASK_DURATION":
        logger.info(f"Extracted duration: {latest_message}")
        return {
            "duration": latest_message,
            "collected_fields": list(set(collected + ["duration"])),
            "last_question_type": None,
            "should_continue": True,
        }

    elif last_question == "ASK_TRIGGERS":
        logger.info(f"Extracted triggers: {latest_message}")
        return {
            "triggers": latest_message,
            "collected_fields": list(set(collected + ["triggers"])),
            "last_question_type": None,
            "should_continue": True,
        }

    elif last_question == "ASK_CHIEF_COMPLAINT":
        logger.info(f"Extracted chief complaint: {latest_message}")
        return {
            "chief_complaint": latest_message,
            "collected_fields": list(set(collected + ["chief_complaint"])),
            "last_question_type": None,
            "should_continue": True,
        }

    # Otherwise, do general LLM-based extraction (for unsolicited info)
    # General LLM-based extraction (for unsolicited / multi-field input)
    # Phi-4-mini-instruct (3.8B) - Golden 4 Interview: fast input parsing
    llm = get_interview_model()
    prompt = ANALYZE_INPUT_PROMPT.format(message=latest_message)
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        content = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        extracted = json.loads(_strip_md_fences(content))

        updates = {}
        new_collected = list(collected)

        if extracted.get("chief_complaint") and "chief_complaint" not in collected:
            updates["chief_complaint"] = extracted.get("chief_complaint")
            new_collected.append("chief_complaint")
        elif extracted.get("chief_complaint"):
            updates["chief_complaint"] = extracted.get("chief_complaint") or state.get(
                "chief_complaint"
            )

        if extracted.get("location") and "location" not in collected:
            updates["location"] = extracted.get("location")
            new_collected.append("location")
        elif extracted.get("location"):
            updates["location"] = extracted.get("location") or state.get("location")

        if extracted.get("duration") and "duration" not in collected:
            updates["duration"] = extracted.get("duration")
            new_collected.append("duration")
        elif extracted.get("duration"):
            updates["duration"] = extracted.get("duration") or state.get("duration")

        if extracted.get("severity") and "severity" not in collected:
            updates["severity"] = extracted.get("severity")
            new_collected.append("severity")
        elif extracted.get("severity"):
            updates["severity"] = extracted.get("severity") or state.get("severity")

        if extracted.get("triggers") and "triggers" not in collected:
            updates["triggers"] = extracted.get("triggers")
            new_collected.append("triggers")
        elif extracted.get("triggers"):
            updates["triggers"] = extracted.get("triggers") or state.get("triggers")

        # Extract relievers (what makes symptoms better)
        if extracted.get("relievers") and "relievers" not in collected:
            updates["relievers"] = extracted.get("relievers")
            new_collected.append("relievers")
        elif extracted.get("relievers"):
            updates["relievers"] = extracted.get("relievers") or state.get("relievers")

        # Merge associated symptoms
        new_symptoms = extracted.get("associated_symptoms", [])
        existing_symptoms = state.get("associated_symptoms", [])
        all_symptoms = list(set(existing_symptoms + new_symptoms))

        updates["associated_symptoms"] = all_symptoms
        updates["collected_fields"] = new_collected
        updates["should_continue"] = True

        logger.info(
            f"General extraction found: {list(updates.keys())}, new_collected: {new_collected}"
        )
        return updates

    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM response as JSON: {response.content}")
        return {"should_continue": True}


async def red_flag_check_node(state: SymptomCheckState) -> dict:
    """Check for emergency red flags in symptoms."""
    logger.info(f"Red flag check for session: {state['session_id']}")

    user_messages = [
        msg.content if isinstance(msg.content, str) else str(msg.content)
        for msg in state["messages"]
        if isinstance(msg, HumanMessage)
    ]
    combined_text = " ".join(user_messages)

    has_red_flags, detected_categories = detect_red_flags(combined_text)

    if has_red_flags:
        logger.warning(f"Red flags detected: {detected_categories}")
        return {
            "red_flags_detected": detected_categories,
            "current_stage": "emergency",
            "should_continue": True,
        }

    return {"should_continue": True}


async def emergency_node(state: SymptomCheckState) -> dict:
    """Handle emergency situations with immediate ER recommendation."""
    logger.info(f"Emergency node activated for session: {state['session_id']}")

    # Llama-3.3-70B - Triage: safety-critical emergency response accuracy
    llm = get_triage_model()

    red_flag_descriptions = [
        get_red_flag_description(cat) for cat in state["red_flags_detected"]
    ]

    prompt = EMERGENCY_PROMPT.format(red_flags=", ".join(red_flag_descriptions))
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    return {
        "messages": [response],
        "classification": "ER_NOW",
        "urgency_score": 10,
        "current_stage": "complete",
        "should_continue": False,
    }


async def gather_info_node(state: SymptomCheckState) -> dict:
    """Determine if Golden 4 is complete or ask follow-up questions with context tracking."""
    logger.info(f"Gathering info for session: {state['session_id']}")

    collected = state.get("collected_fields", [])
    required = ["chief_complaint", "location", "duration", "severity"]
    all_collected = all(field in collected for field in required)
    all_have_values = (
        state.get("chief_complaint") is not None
        and state.get("location") is not None
        and state.get("duration") is not None
        and state.get("severity") is not None
    )

    golden_4_complete = all_collected and all_have_values

    if golden_4_complete:
        logger.info("Golden 4 complete, moving to assessment")
        return {
            "golden_4_complete": True,
            "current_stage": "assessing",
            "should_continue": True,
        }

    # Determine what to ask next based on what's missing — Phi-4-mini-instruct (3.8B)
    llm = get_interview_model()
    question_type = None
    question_prompt = None

    if "chief_complaint" not in collected or not state.get("chief_complaint"):
        question_type = "ASK_CHIEF_COMPLAINT"
        question_prompt = (
            "What symptom or health concern would you like to discuss today?"
        )

    elif "location" not in collected or not state.get("location"):
        question_type = "ASK_LOCATION"
        chief_complaint = state.get("chief_complaint", "symptom")
        question_prompt = f"Where are you experiencing the {chief_complaint}?"

    elif "duration" not in collected or not state.get("duration"):
        question_type = "ASK_DURATION"
        chief_complaint = state.get("chief_complaint", "symptom")
        question_prompt = f"How long have you been experiencing this {chief_complaint}?"

    elif "severity" not in collected or not state.get("severity"):
        question_type = "ASK_SEVERITY"
        chief_complaint = state.get("chief_complaint", "symptom")
        question_prompt = f"On a scale of 1 to 10, how severe is the {chief_complaint}?"

    elif "triggers" not in collected or not state.get("triggers"):
        question_type = "ASK_TRIGGERS"
        question_prompt = "What makes your symptoms worse?"

    # IMPORTANT: System message is mandatory — without it the LLM interprets the
    # question_prompt as the patient asking IT about its own sensations.
    gather_system = SystemMessage(
        content=(
            "You are Vaidya, an AI primary care physician assistant conducting a structured "
            "clinical interview. You are about to ask the PATIENT the question below. "
            "Rephrase it in a professional, medically clear tone. "
            "Keep it to 1-2 sentences. Do NOT answer the question yourself — "
            "output only the question directed at the patient. "
            "Do NOT open with acknowledgment phrases like 'I understand', 'Thank you for sharing', "
            "'Great', 'Of course', or any other filler — go straight to the question."
        )
    )
    response = await llm.ainvoke([gather_system, HumanMessage(content=question_prompt)])

    logger.info(f"Asking question type: {question_type}, collected fields: {collected}")

    return {
        "messages": [response],
        "questions_asked": state.get("questions_asked", 0) + 1,
        "last_question_type": question_type,  # CRITICAL: Record what we asked
        "should_continue": False,  # Wait for user response
    }


async def history_node(state: SymptomCheckState) -> dict:
    """Analyze patient's medical history and correlate with current symptoms."""
    logger.info(f"History analysis node for session: {state['session_id']}")

    # Check if history already analyzed
    if state.get("history_analyzed"):
        logger.info("History already analyzed, skipping")
        return {"should_continue": True}

    # Get patient_id (in production, this would come from authentication)
    # For now, use user_id or a default test patient
    patient_id = state.get("patient_id") or state.get("user_id") or "patient_001"

    logger.info(f"Fetching history for patient: {patient_id}")

    try:
        from app.agents.history_agent import analyze_medical_history

        # Prepare current symptom data
        current_symptoms = {
            "location": state.get("location"),
            "duration": state.get("duration"),
            "severity": state.get("severity"),
            "triggers": state.get("triggers"),
        }

        # Analyze medical history
        history_data = await analyze_medical_history(
            patient_id=patient_id,
            chief_complaint=state.get("chief_complaint"),
            current_symptoms=current_symptoms,
        )

        # Log status message for UI
        status_message = AIMessage(
            content="✓ Reviewing your medical history and current medications..."
        )

        # Extract demographics for preventive care
        demographics = history_data.get("demographics", {})
        age = demographics.get("age")
        sex = demographics.get("gender")  # FHIR uses "gender", we map to "sex" in state

        updates = {
            "messages": [status_message],
            "patient_id": patient_id,
            "age": age,
            "sex": sex,
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

        logger.info(
            f"History analyzed - Risk level: {history_data.get('risk_level')}, "
            f"Conditions: {len(history_data.get('chronic_conditions', []))}, "
            f"Age: {age}, Sex: {sex}"
        )

        return updates

    except Exception as e:
        logger.error(f"Error analyzing medical history: {str(e)}")
        # Continue workflow even if history analysis fails
        return {
            "history_analyzed": True,
            "history_summary": "Unable to retrieve medical history.",
            "chronic_conditions": [],
            "recent_labs": [],
            "current_medications": [],
            "allergies": [],
            "risk_level": "UNKNOWN",
            "should_continue": True,
        }


async def assessment_node(state: SymptomCheckState) -> dict:
    """Generate differential diagnosis."""
    logger.info(f"Assessment node for session: {state['session_id']}")

    # Llama-3.3-70B - Triage: MedQA accuracy for differential diagnosis
    llm = get_triage_model()

    # Build history context
    history_context = "No medical history available."
    if state.get("history_analyzed"):
        history_summary = state.get("history_summary", "")
        risk_level = state.get("risk_level", "UNKNOWN")
        conditions = state.get("chronic_conditions", [])
        medications = state.get("current_medications", [])

        history_parts = [f"Risk Level: {risk_level}"]
        if history_summary:
            history_parts.append(f"Summary: {history_summary}")
        if conditions:
            history_parts.append(f"Chronic Conditions: {', '.join(conditions[:3])}")
        if medications:
            history_parts.append(f"Current Medications: {len(medications)} active")

        history_context = "\n".join(history_parts)

    prompt = ASSESSMENT_PROMPT.format(
        chief_complaint=state.get("chief_complaint", "unknown"),
        location=state.get("location", "not specified"),
        duration=state.get("duration", "not specified"),
        severity=state.get("severity", "not specified"),
        triggers=state.get("triggers", "not specified"),
        associated_symptoms=", ".join(state.get("associated_symptoms", [])),
        history_context=history_context,
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        content = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        assessment = json.loads(_strip_md_fences(content))
        differential = assessment.get("differential", [])

        return {
            "differential_diagnosis": [d["condition"] for d in differential],
            "current_stage": "triaging",
            "should_continue": True,
        }
    except json.JSONDecodeError:
        logger.error(f"Failed to parse assessment response: {response.content}")
        return {
            "differential_diagnosis": ["Unable to assess"],
            "current_stage": "triaging",
            "should_continue": True,
        }


async def triage_node(state: SymptomCheckState) -> dict:
    """Classify triage level."""
    logger.info(f"Triage node for session: {state['session_id']}")

    # Llama-3.3-70B - Triage: 92.55% MedQA, safety-critical triage classification
    llm = get_triage_model()

    # Build history context for triage
    history_context = "No medical history available."
    if state.get("history_analyzed"):
        from app.agents.history_agent import format_history_for_triage

        history_context = format_history_for_triage(
            {
                "patient_found": True,
                "history_summary": state.get("history_summary"),
                "risk_level": state.get("risk_level"),
                "chronic_conditions": state.get("chronic_conditions", []),
                "current_medications": state.get("current_medications", []),
                "allergies": state.get("allergies", []),
                "recent_labs": state.get("recent_labs", []),
            }
        )

    prompt = TRIAGE_PROMPT.format(
        chief_complaint=state.get("chief_complaint", "unknown"),
        severity=state.get("severity", "not specified"),
        duration=state.get("duration", "not specified"),
        red_flags=", ".join(state.get("red_flags_detected", [])) or "none",
        differential=", ".join(state.get("differential_diagnosis", [])),
        history_context=history_context,
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        content = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        triage = json.loads(_strip_md_fences(content))

        return {
            "classification": triage.get("classification"),
            "urgency_score": triage.get("urgency_score"),
            "recommendations": triage.get("recommendations", []),
            "current_stage": "recommendation",
            "should_continue": True,
        }
    except json.JSONDecodeError:
        logger.error(f"Failed to parse triage response: {response.content}")
        return {
            "classification": "GP_SOON",
            "urgency_score": 5,
            "current_stage": "recommendation",
            "should_continue": True,
        }


async def recommendation_node(state: SymptomCheckState) -> dict:
    """Generate final recommendations for the user."""
    logger.info(f"Recommendation node for session: {state['session_id']}")

    # Llama-3.3-70B - Final Responder: clinically accurate, clearly worded patient output
    llm = get_final_model()

    prompt = RECOMMENDATION_PROMPT.format(
        chief_complaint=state.get("chief_complaint", "your symptoms"),
        severity=state.get("severity", "not specified"),
        classification=state.get("classification", "GP_SOON"),
        differential=", ".join(state.get("differential_diagnosis", [])),
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    return {
        "messages": [response],
        "current_stage": "complete",
        "should_continue": False,  # End workflow
    }


async def preventive_chronic_node(state: SymptomCheckState) -> dict:
    """
    Generate preventive care recommendations and chronic disease management plans.

    This node analyzes patient demographics, chronic conditions, and recent labs
    to provide:
    - Age-appropriate preventive screenings
    - Vaccination recommendations
    - Chronic disease care plans

    Only runs for non-emergency triage classifications (not ER_NOW).
    """
    logger.info(f"Preventive/Chronic Care node for session: {state['session_id']}")

    # Skip if emergency triage
    classification = state.get("classification")
    if classification == "ER_NOW":
        logger.info("Skipping preventive care for emergency classification")
        return {
            "preventive_recommendations": [],
            "chronic_care_plans": [],
            "preventive_care_analyzed": False,
        }

    # Status message to user
    status_msg = AIMessage(
        content="💭 Analyzing preventive care needs and chronic disease management..."
    )

    try:
        # Get patient data from state
        age = state.get("age")
        sex = state.get("sex")
        chronic_conditions = state.get("chronic_conditions", [])
        recent_labs = state.get("recent_labs", [])
        current_medications = state.get("current_medications", [])
        history_summary = state.get("history_summary")
        risk_level = state.get("risk_level")

        # Call preventive care analysis
        result = await analyze_preventive_care(
            age=age,
            sex=sex,
            chronic_conditions=chronic_conditions,
            recent_labs=recent_labs,
            current_medications=current_medications,
            history_summary=history_summary,
            risk_level=risk_level,
        )

        # Extract results
        preventive_recommendations = result.get("preventive_recommendations", [])
        chronic_care_plans = result.get("chronic_care_plans", [])
        summary = result.get("summary", "")

        # Format for user display
        formatted_text = []

        if summary:
            formatted_text.append(
                f"**🌟 Preventive Care & Chronic Management Summary:**\n{summary}\n"
            )

        # Format preventive recommendations
        if preventive_recommendations:
            prev_text = format_preventive_recommendations(preventive_recommendations)
            formatted_text.append(prev_text)

        # Format chronic care plans
        if chronic_care_plans:
            chronic_text = format_chronic_care_plans(chronic_care_plans)
            formatted_text.append(chronic_text)

        # Create user-facing message
        if formatted_text:
            formatted_message = "\n".join(formatted_text)
            formatted_message += "\n\n*These are general recommendations based on clinical guidelines. Please discuss with your healthcare provider for personalized advice.*"
        else:
            formatted_message = "No specific preventive care recommendations at this time. Continue routine health maintenance as advised by your doctor."

        response_msg = AIMessage(content=formatted_message)

        logger.info(
            f"Generated {len(preventive_recommendations)} preventive recommendations "
            f"and {len(chronic_care_plans)} chronic care plans"
        )

        return {
            "messages": [status_msg, response_msg],
            "preventive_recommendations": preventive_recommendations,
            "chronic_care_plans": chronic_care_plans,
            "preventive_care_analyzed": True,
            "status_events": ["STATUS:PREVENTIVE_CARE"],
        }

    except Exception as e:
        logger.error(f"Error in preventive/chronic care node: {e}", exc_info=True)
        error_msg = AIMessage(
            content="I encountered an issue analyzing preventive care recommendations. "
            "Your symptom assessment is complete, but please consult your doctor "
            "about age-appropriate screenings and chronic disease management."
        )
        return {
            "messages": [error_msg],
            "preventive_recommendations": [],
            "chronic_care_plans": [],
            "preventive_care_analyzed": False,
            "error": str(e),
        }


async def drug_interaction_node(state: SymptomCheckState) -> dict:
    """
    Check for drug-drug interactions in patient's medication list.

    Analyzes medications from medical history and any mentioned by user
    to identify potential interactions and provide safety guidance.

    Skips if:
    - Emergency triage (ER_NOW)
    - Less than 2 medications
    """
    logger.info(f"Drug Interaction node for session: {state['session_id']}")

    # Skip if emergency triage
    classification = state.get("classification")
    if classification == "ER_NOW":
        logger.info("Skipping drug interaction check for emergency classification")
        return {
            "interaction_results": [],
            "interaction_check_done": False,
        }

    # Get medications from history and user
    current_medications = state.get("current_medications", [])
    med_list_from_user = state.get("med_list_from_user", [])

    # Skip if less than 2 total medications
    all_meds = list(set(current_medications + med_list_from_user))
    if len(all_meds) < 2:
        logger.info("Less than 2 medications, skipping interaction check")
        return {
            "interaction_results": [],
            "interaction_check_done": True,
        }

    # Status message to user
    status_msg = AIMessage(
        content="💊 Checking for potential drug interactions in your medications..."
    )

    # Emit status event
    status_events = ["STATUS:CHECKING_MEDICATIONS"]

    try:
        # Run drug interaction analysis
        result = await analyze_drug_interactions(
            medications=current_medications,
            user_medications=med_list_from_user,
        )

        interactions = result.get("interactions", [])
        summary = result.get("summary", "")
        has_major = result.get("has_major_interactions", False)
        has_moderate = result.get("has_moderate_interactions", False)

        # Format response based on findings
        if not interactions:
            response_text = summary
        else:
            # Add emoji based on severity
            if has_major:
                emoji = "⚠️"
            elif has_moderate:
                emoji = "⚡"
            else:
                emoji = "ℹ️"

            response_text = f"{emoji} **Drug Interaction Analysis**\n\n{summary}"

        response_msg = AIMessage(content=response_text)

        logger.info(
            f"Drug interaction check complete: {len(interactions)} interactions found "
            f"(Major: {has_major}, Moderate: {has_moderate})"
        )

        return {
            "messages": [status_msg, response_msg],
            "interaction_results": interactions,
            "interaction_check_done": True,
            "status_events": status_events,
        }

    except Exception as e:
        logger.error(f"Error in drug interaction node: {e}", exc_info=True)
        error_msg = AIMessage(
            content="I encountered an issue checking drug interactions. "
            "Please ask your doctor or pharmacist to review your medications "
            "for potential interactions."
        )
        return {
            "messages": [error_msg],
            "interaction_results": [],
            "interaction_check_done": False,
            "error": str(e),
        }


async def save_assessment_node(state: SymptomCheckState) -> dict:
    """Save completed assessment to MongoDB."""
    logger.info(f"Saving assessment for session: {state['session_id']}")

    # Only save if we have a classification (triage completed)
    classification = state.get("classification")
    if classification:
        from app.services.assessment_service import get_assessment_service
        from app.models.assessment import TriageAssessment, DifferentialDiagnosis
        from app.models.triage import Probability, TriageClassification
        import uuid
        from datetime import datetime

        # Calculate conversation metrics
        conversation_length = len(state.get("messages", []))

        # Build differential diagnosis list
        differential_list = []
        for condition in state.get("differential_diagnosis", []):
            differential_list.append(
                DifferentialDiagnosis(
                    condition=condition,
                    probability=Probability.MODERATE,  # Default probability
                    reasoning="Based on symptom analysis",
                )
            )

        # Determine when to seek care based on classification
        when_to_seek_care_map = {
            "ER_NOW": "Seek emergency care immediately - call 911 or go to the nearest emergency room",
            "GP_24H": "See a doctor within 24 hours",
            "GP_SOON": "Schedule an appointment with your doctor within 1-2 weeks",
            "HOME": "Monitor symptoms at home and seek care if symptoms worsen",
        }
        when_to_seek_care = when_to_seek_care_map.get(
            str(classification), "Consult with a healthcare provider"
        )

        # Get chief complaint with fallback
        chief_complaint = state.get("chief_complaint") or "Not specified"

        # Convert classification string to enum
        try:
            triage_classification = TriageClassification(classification)
        except (ValueError, TypeError):
            triage_classification = TriageClassification.GP_SOON

        # Create assessment
        assessment = TriageAssessment(
            assessment_id=str(uuid.uuid4()),
            session_id=state["session_id"],
            user_id=state["user_id"],
            chief_complaint=chief_complaint,
            clinical_summary=f"Patient presented with {state.get('chief_complaint', 'symptoms')}. "
            f"Location: {state.get('location', 'not specified')}. "
            f"Duration: {state.get('duration', 'not specified')}. "
            f"Severity: {state.get('severity', 'not specified')}/10.",
            classification=triage_classification,
            confidence_score=0.8,  # Default confidence
            urgency_score=state.get("urgency_score") or 5,  # Default to 5 if not set
            red_flags_detected=state.get("red_flags_detected", []),
            differential_diagnosis=differential_list,
            recommendations=state.get("recommendations", []),
            when_to_seek_care=when_to_seek_care,
            emergency_advised=classification == "ER_NOW",
            conversation_length=conversation_length,
            processing_time_seconds=0.0,  # Will be calculated by service layer if needed
        )

        assessment_service = get_assessment_service()
        await assessment_service.create_assessment(assessment)
        logger.info(f"Assessment {assessment.assessment_id} saved successfully")

    return {"current_stage": "complete", "should_continue": False}


async def final_responder_node(state: SymptomCheckState) -> dict:
    """
    Final Responder: Synthesizes all specialist agent findings into a comprehensive response.

    This node:
    1. Gathers results from all completed agents
    2. Uses LLM to synthesize a clear, actionable response
    3. Prioritizes by urgency (emergency > immediate > routine)
    4. Includes appropriate disclaimers
    5. Marks workflow as complete

    Args:
        state: Current state with all agent results

    Returns:
        Updated state with final synthesized message
    """
    logger.info(
        f"🎬 Final Responder: Synthesizing comprehensive response for session {state['session_id']}"
    )

    try:
        # Llama-3.3-70B - Final Responder: clinically accurate, clearly worded patient output
        llm = get_final_model()

        # Gather all available information
        symptom_info = _format_symptom_info(state)
        history_info = _format_history_info(state)
        preventive_info = _format_preventive_info(state)
        chronic_info = _format_chronic_info(state)
        interaction_info = _format_interaction_info(state)
        provider_info = _format_provider_info(state)

        # Build the prompt
        prompt = FINAL_RESPONDER_PROMPT.format(
            chief_complaint=state.get("chief_complaint") or "Not specified",
            triage_classification=state.get("classification") or "Not assessed",
            differential_diagnosis=", ".join(state.get("differential_diagnosis", []))
            or "Not determined",
            red_flags=", ".join(state.get("red_flags_detected", [])) or "None detected",
            history_summary=history_info,
            preventive_recommendations=preventive_info,
            chronic_care_plans=chronic_info,
            interaction_results=interaction_info,
            nearby_providers=provider_info,
            # Include conversation summary so final responder has full context
            conversation_summary=state.get("conversation_summary")
            or "N/A (conversation is current)",
        )

        # Generate comprehensive response
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        final_message = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )

        # Add urgency banner if needed
        classification = state.get("classification")
        if classification == "ER_NOW":
            final_message = (
                "🚨 **SEEK EMERGENCY CARE IMMEDIATELY** 🚨\n\n" + final_message
            )
        elif classification == "GP_24H":
            final_message = "⚠️ **See a doctor within 24 hours** ⚠️\n\n" + final_message

        logger.info("Final response synthesized successfully")

        return {
            "messages": [AIMessage(content=final_message)],
            "current_stage": "complete",
            "should_continue": False,
        }

    except Exception as e:
        logger.error(f"Error in final responder: {e}", exc_info=True)

        # Fallback: send basic summary
        fallback_msg = _generate_fallback_response(state)

        return {
            "messages": [AIMessage(content=fallback_msg)],
            "current_stage": "complete",
            "should_continue": False,
            "error": str(e),
        }


def _format_symptom_info(state: SymptomCheckState) -> str:
    """Format symptom analysis information."""
    info = []

    if state.get("chief_complaint"):
        info.append(f"Chief Complaint: {state['chief_complaint']}")
    if state.get("location"):
        info.append(f"Location: {state['location']}")
    if state.get("duration"):
        info.append(f"Duration: {state['duration']}")
    if state.get("severity"):
        info.append(f"Severity: {state['severity']}/10")

    return "\n".join(info) if info else "No symptom information available"


def _format_history_info(state: SymptomCheckState) -> str:
    """Format medical history information."""
    if not state.get("history_analyzed", False):
        return "Medical history not analyzed"

    summary = state.get("history_summary", "")
    if summary:
        return summary

    # Build from components
    info = []

    if state.get("chronic_conditions"):
        info.append(f"Chronic Conditions: {', '.join(state['chronic_conditions'])}")

    if state.get("current_medications"):
        info.append(f"Current Medications: {', '.join(state['current_medications'])}")

    if state.get("allergies"):
        info.append(f"Allergies: {', '.join(state['allergies'])}")

    risk_level = state.get("risk_level")
    if risk_level:
        info.append(f"Risk Level: {risk_level}")

    return "\n".join(info) if info else "No significant medical history"


def _format_preventive_info(state: SymptomCheckState) -> str:
    """Format preventive care recommendations."""
    if not state.get("preventive_care_analyzed", False):
        return "Preventive care not analyzed"

    recommendations = state.get("preventive_recommendations", [])

    if not recommendations:
        return "No specific preventive care recommendations at this time"

    # Format top 3-5 recommendations
    formatted = []
    for i, rec in enumerate(recommendations[:5], 1):
        name = rec.get("name", "Unknown")
        reason = rec.get("reason", "")
        status = rec.get("status", "")

        formatted.append(f"{i}. {name} - {reason} ({status})")

    return "\n".join(formatted)


def _format_chronic_info(state: SymptomCheckState) -> str:
    """Format chronic care plans."""
    if not state.get("preventive_care_analyzed", False):
        return "Chronic care not analyzed"

    care_plans = state.get("chronic_care_plans", [])

    if not care_plans:
        return "No chronic disease care plans"

    # Format each care plan
    formatted = []
    for plan in care_plans:
        condition = plan.get("condition", "Unknown")
        risk = plan.get("risk_level", "")
        targets = plan.get("targets", [])

        formatted.append(f"• {condition} (Risk: {risk})")
        if targets:
            # targets is a list of strings (e.g. ["BP <130/80"]), not a dict
            if isinstance(targets, list):
                formatted.append(f"  Targets: {', '.join(str(t) for t in targets)}")
            elif isinstance(targets, dict):
                formatted.append(
                    f"  Targets: {', '.join(f'{k}: {v}' for k, v in targets.items())}"
                )

    return "\n".join(formatted)


def _format_interaction_info(state: SymptomCheckState) -> str:
    """Format drug interaction information."""
    if not state.get("interaction_check_done", False):
        return "Drug interactions not checked"

    interactions = state.get("interaction_results", [])

    if not interactions:
        return "No significant drug interactions found"

    # Count by severity
    major = sum(1 for i in interactions if i.get("severity") == "MAJOR")
    moderate = sum(1 for i in interactions if i.get("severity") == "MODERATE")
    minor = sum(1 for i in interactions if i.get("severity") == "MINOR")

    summary = f"Found {len(interactions)} interactions: "
    parts = []
    if major > 0:
        parts.append(f"{major} major")
    if moderate > 0:
        parts.append(f"{moderate} moderate")
    if minor > 0:
        parts.append(f"{minor} minor")

    return summary + ", ".join(parts)


def _format_provider_info(state: SymptomCheckState) -> str:
    """Format nearby provider information."""
    if not state.get("provider_search_done", False):
        return "Provider search not performed"

    providers = state.get("nearby_providers", [])

    if not providers:
        return "No nearby providers found"

    # Format top 3 providers
    formatted = []
    for i, provider in enumerate(providers[:3], 1):
        name = provider.get("name", "Unknown")
        rating = provider.get("rating", "N/A")
        distance = provider.get("distance_km", "N/A")

        formatted.append(f"{i}. {name} - {rating}⭐ ({distance} km away)")

    return "\n".join(formatted)


def _generate_fallback_response(state: SymptomCheckState) -> str:
    """Generate a basic fallback response when synthesis fails."""
    parts = []

    parts.append("I've analyzed your information. Here's what I found:\n")

    # Chief complaint
    if state.get("chief_complaint"):
        parts.append(f"**Your concern:** {state['chief_complaint']}\n")

    # Triage
    classification = state.get("classification")
    if classification:
        urgency_map = {
            "ER_NOW": "🚨 Seek emergency care immediately",
            "GP_24H": "⚠️ See a doctor within 24 hours",
            "GP_SOON": "Schedule an appointment within 1-2 weeks",
            "HOME": "Monitor at home, seek care if symptoms worsen",
        }
        parts.append(
            f"**Urgency:** {urgency_map.get(classification, 'Consult a healthcare provider')}\n"
        )

    # Recommendations
    recommendations = state.get("recommendations", [])
    if recommendations:
        parts.append("**Recommendations:**")
        for rec in recommendations[:3]:
            parts.append(f"• {rec}")
        parts.append("")

    # Disclaimer
    parts.append(
        "**Important:** I'm an AI assistant, not a doctor. This is not a medical diagnosis. "
        "Please consult with a healthcare professional for proper evaluation and treatment."
    )

    return "\n".join(parts)


# ==============================================================================
# CONTEXT SUMMARIZATION NODE
# ==============================================================================


async def summarization_node(state: SymptomCheckState) -> dict:
    """
    Summarize conversation when it gets too long (20+ messages).

    Creates a concise clinical summary and trims old messages to keep context manageable.
    Triggered by Vaidya before routing to heavy agents.
    """
    messages = state.get("messages", [])
    message_count = len(messages)

    # Only summarize if we have 20+ messages and no existing summary
    # OR if we have 40+ messages (need another summary)
    existing_summary = state.get("conversation_summary")

    should_summarize = False
    if not existing_summary and message_count >= 20:
        should_summarize = True
        logger.info(f"Triggering first summarization at {message_count} messages")
    elif existing_summary and message_count >= 40:
        should_summarize = True
        logger.info(f"Triggering re-summarization at {message_count} messages")

    if not should_summarize:
        # Just update message count and continue
        return {
            "message_count": message_count,
            "should_continue": True,
        }

    logger.info(f"Summarizing conversation for session {state['session_id']}")

    try:
        # Phi-4 (14B) - Supervisor: structured summarization for context management
        llm = get_supervisor_model()

        # Build conversation history for summarization
        conversation_history = []
        for msg in messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            conversation_history.append(f"{role}: {content}")

        conversation_text = "\n\n".join(conversation_history)

        # Build symptom summary
        symptoms_parts = []
        if state.get("chief_complaint"):
            symptoms_parts.append(f"Chief Complaint: {state['chief_complaint']}")
        if state.get("location"):
            symptoms_parts.append(f"Location: {state['location']}")
        if state.get("duration"):
            symptoms_parts.append(f"Duration: {state['duration']}")
        if state.get("severity"):
            symptoms_parts.append(f"Severity: {state['severity']}/10")
        if state.get("triggers"):
            symptoms_parts.append(f"Triggers: {state['triggers']}")
        if state.get("associated_symptoms"):
            symptoms_parts.append(
                f"Associated: {', '.join(state['associated_symptoms'])}"
            )

        symptoms_summary = (
            "; ".join(symptoms_parts) if symptoms_parts else "Not yet collected"
        )

        # Create summarization prompt
        prompt = SUMMARIZATION_PROMPT.format(
            conversation_history=conversation_text,
            chief_complaint=state.get("chief_complaint") or "Not specified",
            symptoms_summary=symptoms_summary,
            classification=state.get("classification") or "Not yet triaged",
            history_summary=state.get("history_summary") or "Not available",
            medications=", ".join(state.get("current_medications", []))
            or "None listed",
            allergies=", ".join(state.get("allergies", [])) or "None listed",
        )

        # Generate summary
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        summary = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )

        logger.info(f"Generated summary ({len(summary)} chars)")

        # Do NOT return a trimmed message list — the `messages` field uses the
        # LangGraph `add` (append) reducer, so returning a list here would DUPLICATE
        # all those messages rather than replacing them.
        # Instead: store the summary in `conversation_summary` and let vaidya.py
        # apply the context window at state-reconstruction time (between turns).
        return {
            "conversation_summary": summary,
            "message_count": message_count,
            "should_continue": True,
        }

    except Exception as e:
        logger.error(f"Error in summarization: {e}", exc_info=True)
        # On error, just update count and continue without summarization
        return {
            "message_count": message_count,
            "should_continue": True,
            "last_error": f"Summarization failed: {str(e)}",
        }
