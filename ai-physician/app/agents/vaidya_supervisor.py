"""Vaidya Supervisor Agent - Central orchestrator for the AI Primary Care Physician.

Vaidya analyzes user messages, detects intent, and intelligently routes to specialist agents
while maintaining conversation context and handling errors gracefully.
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.agents.state import SymptomCheckState
from app.agents.prompts import (
    VAIDYA_SYSTEM_PROMPT,
    VAIDYA_INTENT_ANALYSIS_PROMPT,
    VAIDYA_QUESTIONER_PROMPT,
)
from app.config.llm_config import get_supervisor_model, get_interview_model
from app.config.settings import settings

logger = logging.getLogger(__name__)


def _strip_md_fences(text: str) -> str:
    """Strip markdown code fences that the LLM sometimes wraps JSON in."""
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


# ==============================================================================
# INTENT DETECTION & ROUTING
# ==============================================================================


async def vaidya_supervisor_node(state: SymptomCheckState) -> Dict[str, Any]:
    """
    Vaidya Supervisor: Analyzes user message, detects intent, and routes to next agent.

    This is the central decision-making node that:
    1. Analyzes the current state and user message
    2. Detects user intent
    3. Determines the best next agent to call
    4. Emits status events for UX
    5. Handles errors and edge cases

    Args:
        state: Current conversation state

    Returns:
        Updated state with intent, next_agent, and status_events
    """
    logger.info("🎯 Vaidya Supervisor: Analyzing intent and routing")

    try:
        latest_user_message = _get_latest_user_message(state)

        if not latest_user_message:
            logger.warning("No user message found, skipping supervision")
            return {
                "next_agent": None,
                "should_continue": False,
            }

        context = _build_context(state)

        decision = await _analyze_intent_and_route(latest_user_message, context, state)

        logger.info(
            f"Vaidya decision: intent={decision['intent']}, "
            f"next_agent={decision['next_agent']}, "
            f"reason={decision['reason']}"
        )

        status_events = []
        if decision.get("emit_status") and decision["emit_status"] != "STATUS:NONE":
            status_events.append(decision["emit_status"])

        # Add to active workflows if starting a new agent
        active_workflows = state.get("active_workflows", [])
        next_agent = decision["next_agent"]

        if next_agent not in ["Vaidya_Questioner", "Final_Responder"]:
            if next_agent not in active_workflows:
                active_workflows.append(next_agent)

        return {
            "intent": decision["intent"],
            "next_agent": next_agent,
            "active_workflows": active_workflows,
            "status_events": status_events,
            "should_continue": True,
        }

    except Exception as e:
        logger.error(f"Error in Vaidya supervisor: {e}", exc_info=True)

        # Graceful degradation: default to safe routing
        return {
            "next_agent": _get_fallback_agent(state),
            "last_error": str(e),
            "tool_failures": state.get("tool_failures", []) + ["vaidya_supervisor"],
            "should_continue": True,
        }


async def _analyze_intent_and_route(
    user_message: str,
    context: Dict[str, Any],
    state: SymptomCheckState,
) -> Dict[str, Any]:
    """
    Use LLM to analyze user message and determine intent + next agent.

    Args:
        user_message: Latest message from user
        context: Conversation context dictionary
        state: Current state

    Returns:
        Dictionary with intent, next_agent, emit_status, reason
    """
    if _is_inappropriate_content(user_message):
        logger.warning(f"Inappropriate content detected: {user_message}")
        return {
            "intent": "INAPPROPRIATE",
            "next_agent": "Vaidya_Questioner",
            "emit_status": "STATUS:NONE",
            "reason": "Request contains inappropriate content",
            "needs_followup": True,
        }

    greeting_response = _handle_greeting(user_message, state)
    if greeting_response:
        return greeting_response

    # Phi-4 (14B) — fast structured JSON routing for supervisor decisions
    llm = get_supervisor_model()

    prompt = VAIDYA_INTENT_ANALYSIS_PROMPT.format(
        user_message=user_message,
        message_count=context["message_count"],
        chief_complaint=context["chief_complaint"],
        triage_classification=context["triage_classification"],
        golden_4_complete=context["golden_4_complete"],
        history_analyzed=context["history_analyzed"],
        preventive_care_analyzed=context["preventive_care_analyzed"],
        interaction_check_done=context["interaction_check_done"],
        provider_search_done=context["provider_search_done"],
        conversation_summary=context.get("conversation_summary")
        or "No summary yet (conversation still short)",
    )

    system_msg = SystemMessage(
        content=VAIDYA_SYSTEM_PROMPT.format(
            golden_4_complete=context["golden_4_complete"],
            history_analyzed=context["history_analyzed"],
            preventive_care_analyzed=context["preventive_care_analyzed"],
            interaction_check_done=context["interaction_check_done"],
            provider_search_done=context["provider_search_done"],
            triage_classification=context["triage_classification"],
        )
    )

    response = await llm.ainvoke([system_msg, HumanMessage(content=prompt)])

    try:
        content = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        decision = json.loads(_strip_md_fences(content))

        required_fields = ["intent", "next_agent", "reason"]
        for field in required_fields:
            if field not in decision:
                raise ValueError(f"Missing required field: {field}")

        decision = _apply_safety_overrides(decision, state)

        return decision

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse LLM decision: {e}, content: {response.content}")

        # Fallback to rule-based routing
        return _fallback_routing(user_message, context, state)


def _apply_safety_overrides(
    decision: Dict[str, Any],
    state: SymptomCheckState,
) -> Dict[str, Any]:
    """
    Apply safety rules to override LLM decisions when necessary.

    Args:
        decision: Original decision from LLM
        state: Current state

    Returns:
        Modified decision with safety overrides applied
    """
    # Override 1: Emergency triage takes precedence
    triage = state.get("classification")
    emergency_mode = state.get("emergency_mode", False)

    # Sticky emergency mode: once ER_NOW is triggered, ALL follow-up messages
    # go directly to Final_Responder for reassurance/first-aid only.
    if emergency_mode and decision["next_agent"] not in ["Final_Responder"]:
        logger.warning(
            "Sticky emergency mode active — overriding routing to Final_Responder for follow-up"
        )
        decision["next_agent"] = "Final_Responder"
        decision["reason"] = (
            "Emergency mode is active — providing follow-up first-aid guidance"
        )
        decision["emit_status"] = "STATUS:GENERATING_RESPONSE"

    # Standard ER_NOW safety override (first trigger, before emergency_mode flag is sticky)
    elif triage == "ER_NOW" and decision["next_agent"] not in [
        "Final_Responder",
        "Provider_Locator_Agent",
        "ER_Emergency_Agent",
    ]:
        logger.warning(
            "Overriding routing: ER triage detected, proceeding to final response"
        )
        decision["next_agent"] = "Final_Responder"
        decision["reason"] = (
            "Emergency triage - proceeding to final urgent recommendations"
        )

    # Override 2: Can't check drug interactions without medications
    if decision["next_agent"] == "Drug_Interaction_Agent":
        med_list = state.get("med_list_from_user", []) or state.get(
            "current_medications", []
        )
        if not med_list or len(med_list) < 2:
            logger.info("Insufficient medications for interaction check")
            decision["next_agent"] = "Vaidya_Questioner"
            decision["reason"] = "Need at least 2 medications to check interactions"

    return decision


def _fallback_routing(
    user_message: str,
    context: Dict[str, Any],
    state: SymptomCheckState,
) -> Dict[str, Any]:
    """
    Rule-based fallback routing when LLM parsing fails.

    Args:
        user_message: User's message
        context: Context dictionary
        state: Current state

    Returns:
        Decision dictionary
    """
    logger.info("Using fallback rule-based routing")

    msg_lower = user_message.lower()

    # FIRST: Sticky emergency mode — all follow-up messages go to Final_Responder
    if context.get("emergency_mode") or state.get("emergency_mode"):
        return {
            "intent": "FOLLOWUP_QUESTION",
            "next_agent": "Final_Responder",
            "emit_status": "STATUS:GENERATING_RESPONSE",
            "reason": "Emergency mode active \u2014 follow-up first-aid guidance",
        }

    # Check for mental health / suicidal ideation FIRST — these are emergencies
    # (removed from inappropriate filter so they reach here)
    crisis_keywords = [
        "kill myself",
        "suicide",
        "end my life",
        "want to die",
        "take my life",
        "overdose on",
        "lethal dose",
        "ways to die",
        "harm myself",
        "hurt myself",
    ]
    if any(kw in msg_lower for kw in crisis_keywords):
        return {
            "intent": "SYMPTOM_CHECK",
            "next_agent": "Symptom_Analyst",
            "emit_status": "STATUS:SYMPTOM_ANALYSIS",
            "reason": "Potential mental health crisis detected — routing to emergency triage",
        }

    # Check for provider search keywords — require explicit find/locate intent
    # Do NOT trigger on incidental words like "my doctor said" or "nearby park"
    provider_keywords = [
        "find a doctor",
        "find a hospital",
        "find a clinic",
        "find a cardiologist",
        "nearest hospital",
        "nearest er",
        "near me",
        "nearby clinic",
        "nearby hospital",
        "locate a provider",
        "where can i go",
        "which hospital",
    ]
    if any(keyword in msg_lower for keyword in provider_keywords):
        return {
            "intent": "PROVIDER_SEARCH",
            "next_agent": "Provider_Locator_Agent",
            "emit_status": "STATUS:SEARCHING_PROVIDERS",
            "reason": "Detected explicit provider search keywords",
        }

    # Check for medication keywords — require explicit drug/interaction intent
    # Do NOT trigger on incidental "taking" (e.g., "taking a walk")
    med_keywords = [
        "drug interaction",
        "medication interaction",
        "are my medications safe",
        "my medications",
        "my medicines",
        "side effect",
        "prescription interaction",
        "safe to take together",
        "can i take",
    ]
    if any(keyword in msg_lower for keyword in med_keywords):
        return {
            "intent": "MEDICATION_SAFETY",
            "next_agent": "Drug_Interaction_Agent",
            "emit_status": "STATUS:CHECKING_MED_INTERACTIONS",
            "reason": "Detected medication safety keywords",
        }

    # Default: route based on workflow progress
    if not context["golden_4_complete"]:
        return {
            "intent": "SYMPTOM_CHECK",
            "next_agent": "Symptom_Analyst",
            "emit_status": "STATUS:SYMPTOM_ANALYSIS",
            "reason": "Default: symptom analysis not complete",
        }
    elif not context["history_analyzed"]:
        return {
            "intent": "SYMPTOM_CHECK",
            "next_agent": "History_Agent",
            "emit_status": "STATUS:CHECKING_HISTORY",
            "reason": "Default: history not yet analyzed",
        }
    else:
        return {
            "intent": "FOLLOWUP_QUESTION",
            "next_agent": "Final_Responder",
            "emit_status": "STATUS:NONE",
            "reason": "Default: providing final response",
        }


# ==============================================================================
# VAIDYA QUESTIONER NODE
# ==============================================================================


async def vaidya_questioner_node(state: SymptomCheckState) -> Dict[str, Any]:
    """
    Vaidya Questioner: Asks targeted clarifying questions when supervisor
    identifies missing critical information, handles greetings, and manages
    inappropriate content.

    Args:
        state: Current state

    Returns:
        Updated state with clarifying question added to messages
    """
    logger.info("❓ Vaidya Questioner: Asking clarifying question")

    try:
        # Determine what information is missing
        missing_info = _identify_missing_info(state)

        if not missing_info:
            logger.info("No missing information identified by Vaidya Questioner")

            # Check if Golden 4 is incomplete - if so, route to Symptom Analyst
            golden_4_complete = state.get("golden_4_complete", False)
            chief_complaint = state.get("chief_complaint")

            if chief_complaint and not golden_4_complete:
                logger.info("Golden 4 incomplete, routing back to Symptom Analyst")
                return {
                    "next_agent": "Symptom_Analyst",
                    "should_continue": True,
                }

            # No specific missing info and no active symptom workflow
            # Generate conversational response using LLM
            logger.info("Generating conversational response via LLM")
            try:
                response = await asyncio.wait_for(
                    _generate_conversational_response(state),
                    timeout=settings.llm_invoke_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"LLM response generation timed out after {settings.llm_invoke_timeout}s"
                )
                response = "I apologize, but I'm having trouble responding right now. Could you please rephrase your message?"

            return {
                "messages": [AIMessage(content=response)],
                "next_agent": None,
                "should_continue": False,
            }

        # Generate question using LLM
        question = await _generate_clarifying_question(missing_info, state)

        # Add question to messages
        question_msg = AIMessage(content=question)

        logger.info(f"Vaidya asking: {question}")

        # Add to pending questions for tracking
        pending = state.get("pending_questions", [])
        pending.append(
            {
                "source": "Vaidya",
                "topic": missing_info["topic"],
                "text": question,
            }
        )

        return {
            "messages": [question_msg],
            "pending_questions": pending,
            "next_agent": None,  # Wait for user response
            "should_continue": False,  # End this turn, wait for user
        }

    except Exception as e:
        logger.error(f"Error in Vaidya questioner: {e}", exc_info=True)

        # LLM fallback instead of static string
        try:
            llm = get_interview_model()
            user_msg = _get_latest_user_message(state) or "your question"
            fallback_response = await llm.ainvoke(
                [
                    HumanMessage(
                        content=(
                            f"You are Vaidya, an AI health assistant. "
                            f'The patient said: "{user_msg}". '
                            "Ask ONE short, empathetic follow-up question to understand their health concern better. "
                            "Do not start with filler phrases. 1-2 sentences max."
                        )
                    )
                ]
            )
            fallback_text = (
                fallback_response.content
                if isinstance(fallback_response.content, str)
                else str(fallback_response.content)
            )
            fallback_msg = AIMessage(content=fallback_text)
        except Exception:
            fallback_msg = AIMessage(
                content="Could you tell me more about what you're experiencing so I can help?"
            )

        return {
            "messages": [fallback_msg],
            "should_continue": False,
        }


def _identify_missing_info(state: SymptomCheckState) -> Optional[Dict[str, str]]:
    """
    Identify what critical information is missing.

    Uses `intent` field (preserved by supervisor) instead of `next_agent`
    (which is overwritten to 'Vaidya_Questioner' by safety overrides before
    this questioner node runs).

    Args:
        state: Current state

    Returns:
        Dictionary with 'topic' and 'description' of missing info, or None
    """
    # Use intent to determine what the supervisor originally wanted to do
    # (next_agent may have been redirected to 'Vaidya_Questioner' by safety overrides)
    intent = state.get("intent")
    next_agent = state.get("next_agent")

    # Age needed for preventive care
    if state.get("active_workflows") and "Preventive_Chronic_Agent" in state.get(
        "active_workflows", []
    ):
        if not state.get("age"):
            return {
                "topic": "age",
                "description": "Patient age for preventive care recommendations",
            }

    # Check intent for MEDICATION_SAFETY
    wants_drug_check = (
        intent == "MEDICATION_SAFETY" or next_agent == "Drug_Interaction_Agent"
    )
    if wants_drug_check:
        meds = state.get("med_list_from_user", []) or state.get(
            "current_medications", []
        )
        if not meds or len(meds) < 2:
            return {
                "topic": "medications",
                "description": "List of current medications (at least 2) for interaction checking",
            }

    return None


async def _generate_clarifying_question(
    missing_info: Dict[str, str],
    state: SymptomCheckState,
) -> str:
    """
    Generate a natural clarifying question for missing information.

    Args:
        missing_info: Dictionary with topic and description
        state: Current state

    Returns:
        Generated question string
    """
    # Phi-4-mini-instruct (3.8B) — ultra-fast conversational interview Q&A
    llm = get_interview_model()

    # Recent conversation excerpt for context
    messages = state.get("messages", [])
    recent_messages = messages[-4:] if len(messages) > 4 else messages
    recent_exchanges = "\n".join(
        [
            f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {str(m.content)[:120]}"
            for m in recent_messages
        ]
    )

    prompt = VAIDYA_QUESTIONER_PROMPT.format(
        chief_complaint=state.get("chief_complaint", "not yet identified"),
        topic=missing_info["topic"],
        missing_info=missing_info["description"],
        patient_age=str(state.get("age", "unknown")),
        known_conditions=", ".join(state.get("chronic_conditions", []))
        or "none reported",
        current_medications=", ".join(state.get("current_medications", []))
        or "none reported",
        severity=str(state.get("severity", "not specified")),
        triage_classification=state.get("classification", "not yet triaged"),
        recent_exchanges=recent_exchanges if recent_exchanges else "[First message]",
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    question = (
        response.content if isinstance(response.content, str) else str(response.content)
    )

    return question.strip()


async def _generate_conversational_response(state: SymptomCheckState) -> str:
    """
    Generate a conversational response when no specific missing info to collect.
    Used for greetings, vague messages, inappropriate content, etc.
    Fully LLM-driven - no hardcoded responses.

    Args:
        state: Current state

    Returns:
        Generated conversational response
    """
    logger.info("🤖 Starting LLM call for conversational response")
    # Phi-4-mini-instruct (3.8B) — ultra-fast back-and-forth dialogue
    llm = get_interview_model()
    logger.info(
        f"✅ LLM model loaded: {llm.model_name if hasattr(llm, 'model_name') else 'unknown'}"
    )

    messages = state.get("messages", [])
    recent_messages = messages[-4:] if len(messages) > 4 else messages
    context_summary = "\n".join(
        [
            f"{'User' if isinstance(m, HumanMessage) else 'Vaidya'}: {m.content[:150]}"
            for m in recent_messages
        ]
    )

    user_message = "No message"
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break

    from app.agents.prompts import VAIDYA_CONVERSATIONAL_PROMPT

    prompt = VAIDYA_CONVERSATIONAL_PROMPT.format(
        patient_age=str(state.get("age", "unknown")),
        chief_complaint=state.get("chief_complaint", "not yet identified"),
        triage_classification=state.get("classification", "not yet triaged"),
        emergency_mode=state.get("emergency_mode", False),
        known_conditions=", ".join(state.get("chronic_conditions", []))
        or "none reported",
        current_medications=", ".join(state.get("current_medications", []))
        or "none reported",
        context_summary=context_summary if context_summary else "[First message]",
        user_message=user_message,
    )

    logger.info("📤 Sending request to LLM...")
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    logger.info("✅ Received LLM response")

    response_text = (
        response.content if isinstance(response.content, str) else str(response.content)
    )

    return response_text.strip()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def _get_latest_user_message(state: SymptomCheckState) -> Optional[str]:
    """Extract the latest user message from state."""
    messages = state.get("messages", [])

    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            # Handle both string and list content types
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # Extract text from list of content blocks
                text_parts = []
                for item in content:
                    if isinstance(item, str):
                        text_parts.append(item)
                    elif isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                return " ".join(text_parts) if text_parts else None

    return None


def _build_context(state: SymptomCheckState) -> Dict[str, Any]:
    """Build context dictionary for decision making."""
    return {
        "message_count": state.get("message_count", len(state.get("messages", []))),
        "chief_complaint": state.get("chief_complaint") or "None",
        "triage_classification": state.get("classification") or "None",
        "golden_4_complete": state.get("golden_4_complete", False),
        "history_analyzed": state.get("history_analyzed", False),
        "preventive_care_analyzed": state.get("preventive_care_analyzed", False),
        "interaction_check_done": state.get("interaction_check_done", False),
        "provider_search_done": state.get("provider_search_done", False),
        "conversation_summary": state.get("conversation_summary"),
        "last_error": state.get("last_error"),
        "tool_failures": state.get("tool_failures", []),
        "emergency_mode": state.get("emergency_mode", False),
    }


def _get_fallback_agent(state: SymptomCheckState) -> str:
    """
    Determine a safe fallback agent based on current state.

    Args:
        state: Current state

    Returns:
        Name of fallback agent
    """
    # If nothing done yet, start with symptom analysis
    if not state.get("golden_4_complete", False):
        return "Symptom_Analyst"

    # If symptom done but not history, do history
    if not state.get("history_analyzed", False):
        return "History_Agent"

    # Otherwise, wrap up with final responder
    return "Final_Responder"


def should_continue_workflow(state: SymptomCheckState) -> str:
    """
    Determine if workflow should continue or end.

    Args:
        state: Current state

    Returns:
        "continue" or "end"
    """
    if not state.get("should_continue", True):
        return "end"

    # If next_agent is set, continue
    if state.get("next_agent"):
        return "continue"

    # Default to end (wait for user)
    return "end"


def route_to_next_agent(state: SymptomCheckState) -> str:
    """
    Route to the next agent based on Vaidya's decision.

    Args:
        state: Current state

    Returns:
        Name of next agent/node to execute
    """
    next_agent = state.get("next_agent")

    if not next_agent:
        return "end"

    # Map next_agent names to actual node names
    agent_mapping = {
        "Symptom_Analyst": "symptom_analyst",
        "History_Agent": "history",
        "Preventive_Chronic_Agent": "preventive_chronic",
        "Drug_Interaction_Agent": "drug_interaction",
        "Provider_Locator_Agent": "provider_locator",
        "ER_Emergency_Agent": "er_emergency",
        "Vaidya_Questioner": "vaidya_questioner",
        "Final_Responder": "final_responder",
    }

    node_name = agent_mapping.get(next_agent, "final_responder")

    logger.info(f"Routing to: {node_name}")

    return node_name


# ==============================================================================
# CONTENT SAFETY & GREETING HANDLING
# ==============================================================================


def _is_inappropriate_content(message: str) -> bool:
    """
    Check if message contains truly inappropriate content (not medical emergencies).

    IMPORTANT: Suicidal ideation, self-harm, and overdose mentions are MEDICAL EMERGENCIES
    and must NOT be caught here — they must reach the symptom analyst's red_flag_check
    which routes to the emergency node with proper guidance.

    Args:
        message: User message to check

    Returns:
        True if content is genuinely inappropriate (non-clinical)
    """
    msg_lower = message.lower()

    # Only block genuinely non-clinical inappropriate content
    # DO NOT add medical/mental-health crisis patterns here
    inappropriate_patterns = [
        # Illegal activities unrelated to healthcare
        "illegal drugs",
        "buy drugs",
        "fake prescription",
        "forge prescription",
        # Harassment/abuse
        "hate speech",
        "racist",
        "discriminate",
        # Harmful advice requests unrelated to personal health
        "how to harm others",
        "how to hurt someone",
    ]

    for pattern in inappropriate_patterns:
        if pattern in msg_lower:
            return True

    return False


def _handle_greeting(
    message: str, state: SymptomCheckState
) -> Optional[Dict[str, Any]]:
    """
    Handle simple greetings directly without full intent analysis.

    Args:
        message: User message
        state: Current state

    Returns:
        Routing decision for greetings, or None if not a greeting
    """
    msg_lower = message.lower().strip()

    # Common greeting patterns
    greetings = [
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "greetings",
        "howdy",
        "hi there",
        "hello there",
    ]

    # Check if message is a simple greeting (not part of longer sentence)
    is_greeting = False
    if msg_lower in greetings:
        is_greeting = True
    elif any(
        msg_lower.startswith(g + " ") or msg_lower.startswith(g + "!")
        for g in greetings
    ):
        # It's a greeting followed by something else, not a simple greeting
        is_greeting = False
    elif msg_lower.replace("!", "").replace("?", "").strip() in greetings:
        is_greeting = True

    if is_greeting:
        logger.info(f"Handling simple greeting: {message}")
        return {
            "intent": "GREETING",
            "next_agent": "Vaidya_Questioner",
            "emit_status": "STATUS:NONE",
            "reason": "User sent a simple greeting",
            "needs_followup": True,
        }

    return None
