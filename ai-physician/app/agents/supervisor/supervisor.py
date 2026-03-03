"""Vaidya Supervisor Agent - Central orchestrator for the AI Primary Care Physician.

This agent implements a ReAct-style pattern (Thought, Plan, Decision) to:
1. Greet the user and manage initial intake.
2. Analyze user intent and medical context.
3. Route to specialized sub-agents.
4. Maintain a high-level coordination role throughout the conversation.
"""

import json
import logging
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agents.common.state import VaidyaState
from app.agents.common.utils import parse_json_safely
from app.agents.supervisor.prompts import (
    VAIDYA_SYSTEM_PROMPT
)
from app.config.llm_config import get_supervisor_model

logger = logging.getLogger(__name__)

async def supervisor_node(state: VaidyaState) -> Dict[str, Any]:
    """
    The primary Supervisor node. Acts as the entry point and decision maker.
    """
    logger.info("Vaidya Supervisor: Orchestrating turn")
    
    llm = get_supervisor_model()

    # Get conversation history since last summary (excluding the current user message)
    summarized_count = state.get("summarized_message_count", 0)
    messages = state.get("messages", [])
    
    # We take all messages from summarized_count up to (but not including) the latest one
    recent_messages = messages[summarized_count:-1] if len(messages) > summarized_count else []
    
    # Format recent history for prompt
    recent_history_text = "\n".join([
        f"{'Patient' if isinstance(m, HumanMessage) else 'Vaidya'}: {m.content}" 
        for m in recent_messages
    ]) if recent_messages else "No recent messages."

    # Build context for the supervisor
    context = _get_context_summary(state)
    context["recent_history"] = recent_history_text
    
    # Handle empty message case (e.g. on /start without a message)
    user_msg = _get_latest_user_message(state)

    if not user_msg:
        # If no message, we just want a greeting/prompt
        return {
            "thought": "No user message provided. Routing to Questioner for initial greeting.",
            "plan": "Ask the user how I can help today.",
            "next_agent": "Vaidya_Questioner",
            "intent": "GREETING",
            "should_continue": True
        }

    # Now we inject the current user message into context for formatting the system prompt
    context["user_message"] = user_msg
    
    system_msg_content = VAIDYA_SYSTEM_PROMPT.format(**context)
    system_msg = SystemMessage(content=system_msg_content)
    
    logger.info(f"Supervisor context length: {len(system_msg_content)} chars")

    # The user has merged intent analysis into the system prompt.
    response = await llm.ainvoke([
        system_msg, 
        HumanMessage(content="Analyze the user message above and return the routing JSON.")
    ])
    content = str(response.content)

    print("SUPERVISOR RESPONSE",content)

    decision = parse_json_safely(content)
    
    if not decision:
        logger.error(f"Supervisor failed to produce valid JSON decision. Raw output: {content}")
        return {"next_agent": "Final_Responder", "should_continue": True}

    logger.info(f"Supervisor Thought: {decision.get('thought')}")
    logger.info(f"Supervisor Plan: {decision.get('plan')}")
    logger.info(f"Supervisor Decision: next_agent={decision.get('next_agent')}")

    result = {
        "thought": decision.get("thought"),
        "plan": decision.get("plan"),
        "next_agent": decision.get("next_agent"),
        "should_continue": True
    }
    
    if decision.get("intent") is not None:
        result["intent"] = decision.get("intent")
        
    if decision.get("emit_status"):
        result["status_events"] = [decision.get("emit_status")]
        
    if decision.get("emergency_detected"):
        result["emergency_mode"] = True
        
    if decision.get("emergency_type"):
        result["emergency_type"] = decision.get("emergency_type")

    return result

def _get_latest_user_message(state: VaidyaState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""

def _get_context_summary(state: VaidyaState) -> Dict[str, Any]:
    return {
        "message_count": len(state.get("messages", [])),
        "chief_complaint": state.get("chief_complaint") or "not yet identified",
        "triage_classification": state.get("classification") or "not yet determined",
        "golden_4_complete": state.get("golden_4_complete", False),
        "history_analyzed": state.get("history_analyzed", False),
        "preventive_care_analyzed": state.get("preventive_care_analyzed", False),
        "interaction_check_done": state.get("interaction_check_done", False),
        "provider_search_done": state.get("provider_search_done", False),
        "emergency_mode": state.get("emergency_mode", False),
        "questions_asked": state.get("questions_asked", 0),
        "last_question_type": state.get("last_question_type"),
        "conversation_summary": state.get("conversation_summary") or "No summary yet."
    }
