"""Common nodes for Vaidya supervisor and specialist workflow."""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage
from app.agents.common.state import VaidyaState
from app.agents.common.utils import parse_json_safely
from app.agents.supervisor.prompts import VAIDYA_CONVERSATIONAL_PROMPT, FINAL_RESPONDER_PROMPT, SUMMARIZATION_PROMPT, VAIDYA_QUESTIONER_PROMPT
from app.config.llm_config import get_final_model, get_supervisor_model, get_interview_model

logger = logging.getLogger(__name__)

async def final_responder_node(state: VaidyaState) -> Dict[str, Any]:
    """Synthesizes all specialist agent findings into a comprehensive response."""
    logger.info(f"🎬 Final Responder: Synthesizing response for session {state.get('session_id')}")
    
    llm = get_final_model()
    
    # Simple synthesis logic for now - in production this would be more complex
    prompt = FINAL_RESPONDER_PROMPT.format(
        chief_complaint=state.get("chief_complaint") or "Not specified",
        triage_classification=state.get("classification") or "Not assessed",
        differential_diagnosis=", ".join(state.get("differential_diagnosis", [])) or "Not determined",
        red_flags=", ".join(state.get("red_flags_detected", [])) or "None detected",
        history_summary=state.get("history_summary") or "N/A",
        preventive_recommendations=str(state.get("preventive_recommendations", [])),
        chronic_care_plans=str(state.get("chronic_care_plans", [])),
        interaction_results=str(state.get("interaction_results", [])),
        nearby_providers=str(state.get("nearby_providers", [])),
        conversation_summary=state.get("conversation_summary") or "N/A"
    )
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return {"messages": [response], "should_continue": False}

async def summarization_node(state: VaidyaState) -> Dict[str, Any]:
    """Summarizes conversation when it gets too long."""
    messages = state.get("messages", [])
    summarized_count = state.get("summarized_message_count", 0)
    
    # Check if we have 10 or more new messages since the last summarization
    new_messages = messages[summarized_count:]
    if len(new_messages) < 10:
        return {"should_continue": True}

    logger.info(f"📝 Summarizing {len(new_messages)} new messages for session {state.get('session_id')}")
    llm = get_supervisor_model()
    
    # Format the new messages for the LLM
    new_history_text = "\n".join([f"{type(m).__name__}: {m.content}" for m in new_messages])
    
    # Provide context of existing summary if it exists
    existing_summary = state.get("conversation_summary") or "No previous summary."
    
    prompt = f"""
    Existing Conversation Summary:
    {existing_summary}

    New messages to summarize:
    {new_history_text}

    Create a concise clinical summary of these NEW messages. 
    Focus on:
    - New symptoms or complaints
    - Changes in status
    - Key patient answers
    
    Return ONLY the summary of the new messages. Do not repeat the existing summary.
    """
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    new_summary = str(response.content).strip()
    
    # Append the new summary to the cumulative summary
    if state.get("conversation_summary"):
        combined_summary = f"{state.get('conversation_summary')}\n\nSubsequent events:\n{new_summary}"
    else:
        combined_summary = new_summary
        
    return {
        "conversation_summary": combined_summary,
        "summarized_message_count": summarized_count + len(new_messages),
        "should_continue": True
    }

async def save_assessment_node(state: VaidyaState) -> Dict[str, Any]:
    """Save completed assessment to persistence layer."""
    logger.info(f"Saving assessment for session: {state.get('session_id')}")
    # Implementation would involve calling the assessment service
    return {"should_continue": False}

async def vaidya_questioner_node(state: VaidyaState) -> Dict[str, Any]:
    """Handles off-topic questions, clarifications, and the initial greeting."""
    logger.info(f"🤔 Vaidya Questioner: Processing input for session {state.get('session_id')}")
    
    llm = get_interview_model()
    
    # Format recent exchanges
    messages = state.get("messages", [])
    recent = "\n".join([f"{'Patient' if isinstance(m, HumanMessage) else 'Vaidya'}: {m.content}" for m in messages[-4:]]) if messages else "None"
    
    prompt = VAIDYA_QUESTIONER_PROMPT.format(
        intent=state.get("intent") or "OTHER",
        routing_thought=state.get("thought") or "N/A",
        chief_complaint=state.get("chief_complaint") or "None",
        topic="Initial Assessment / Clarification / Greeting / Other",
        missing_info="Initial symptoms or clarification",
        patient_age=state.get("age") or "Unknown",
        known_conditions=", ".join(state.get("chronic_conditions", [])) or "None",
        current_medications=", ".join(state.get("current_medications", [])) or "None",
        severity=state.get("severity") or "null",
        location=state.get("location") or "null",
        duration=state.get("duration") or "null",
        triggers=state.get("triggers") or "null",
        relievers=state.get("relievers") or "null",
        triage_classification=state.get("classification") or "None",
        emergency_mode=state.get("emergency_mode", False),
        recent_exchanges=recent
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = str(response.content)

    print("VAIDYA QUESTIONER RESPONSE ", content)

    # Parse the structured JSON response
    parsed = parse_json_safely(content)

    if not parsed:
        # Fallback: return raw message if JSON parsing fails
        logger.error(f"Vaidya Questioner failed to produce valid JSON. Raw output: {content[:200]}")
        return {"messages": [response], "should_continue": False}

    # Extract clean text questions to show the patient
    questions = parsed.get("questions", [])
    text_response = "\n\n".join([q.get("text", "") for q in questions if q.get("text")])

    # Get the type of the last question asked (for context tracking)
    last_type = questions[-1].get("question_type") if questions else None

    logger.info(
        f"Vaidya Questioner: asked {parsed.get('questions_asked_delta', 0)} question(s), "
        f"last_type={last_type}, text_preview={text_response[:80]!r}"
    )

    # Return updated state
    return {
        "messages": [AIMessage(content=text_response)],
        "questions_asked": state.get("questions_asked", 0) + int(parsed.get("questions_asked_delta", 0)),
        "last_question_type": last_type,
        "thought": parsed.get("thought"),
        "plan": parsed.get("plan"),
        "should_continue": False,
    }
