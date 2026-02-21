"""Vaidya API endpoints.

This API provides access to Vaidya, the root supervisor agent that intelligently
handles all healthcare interactions by routing to specialized sub-agents:
- Symptom Analyst: For symptom checking and triage
- History Agent: For accessing medical history
- Preventive & Chronic Care Agent: For preventive care recommendations
- Drug Interaction Agent: For medication safety checks
- Provider Locator Agent: For finding healthcare providers

Vaidya orchestrates the entire conversation and determines the best agent for each request.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from app.api.dependencies import get_current_user
from app.models.messages import (
    StartSessionResponse,
    MessageRequest,
    SessionDetailsResponse,
    AssessmentHistoryResponse,
    AssessmentSummary,
    SessionSummary,
    UserSessionsResponse,
)
from app.models.triage import SessionStatus
from app.services.session_service import get_session_service
from app.services.assessment_service import get_assessment_service
from app.agents.symptom_analyst import get_vaidya_graph
from app.agents.state import SymptomCheckState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from typing import Dict
from datetime import datetime
import json
import logging
import asyncio


def _status_event_to_message(status_event: str) -> str:
    """Convert internal status event code to user-friendly message."""
    status_map = {
        "STATUS:SYMPTOM_ANALYSIS": "Analyzing your symptoms...",
        "STATUS:CHECKING_HISTORY": "Checking your medical history...",
        "STATUS:SEARCHING_PROVIDERS": "Looking for nearby healthcare providers...",
        "STATUS:CHECKING_MEDICATIONS": "Checking medication interactions...",
        "STATUS:PREVENTIVE_CARE": "Analyzing preventive care recommendations...",
        "STATUS:TRIAGE_ASSESSMENT": "Assessing urgency level...",
        "STATUS:GENERATING_RESPONSE": "Preparing your personalized response...",
    }
    return status_map.get(status_event, "Processing your request...")


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vaidya", tags=["Vaidya"])


@router.post("/start", response_model=StartSessionResponse)
async def start_session(current_user: Dict[str, str] = Depends(get_current_user)):
    """
    Start a new Vaidya session.

    Requires JWT authentication.
    Returns session ID and initial greeting message.

    Vaidya is the root supervisor agent that will intelligently route to
    specialized sub-agents as needed based on your requests.
    """
    session_service = get_session_service()

    # Create new session
    session = await session_service.create_session(
        user_id=current_user["userId"], user_email=current_user["email"]
    )

    # Get the Vaidya-orchestrated multi-agent graph
    graph = get_vaidya_graph()

    # Initialize state
    initial_state: SymptomCheckState = {
        "messages": [],
        "conversation_summary": None,
        "message_count": 0,
        "user_id": current_user["userId"],
        "user_email": current_user["email"],
        "session_id": session.session_id,
        "chief_complaint": None,
        "location": None,
        "duration": None,
        "severity": None,
        "triggers": None,
        "relievers": None,
        "associated_symptoms": [],
        "current_stage": "greeting",
        "questions_asked": 0,
        "golden_4_complete": False,
        "red_flags_detected": [],
        "classification": None,
        "differential_diagnosis": [],
        "recommendations": [],
        "urgency_score": None,
        "patient_id": None,
        "history_summary": None,
        "chronic_conditions": [],
        "recent_labs": [],
        "current_medications": [],
        "allergies": [],
        "risk_level": None,
        "history_analyzed": False,
        "preventive_recommendations": [],
        "chronic_care_plans": [],
        "preventive_care_analyzed": False,
        "age": None,
        "sex": None,
        "med_list_from_user": [],
        "interaction_results": [],
        "interaction_check_done": False,
        "user_location": None,
        "provider_query": None,
        "nearby_providers": [],
        "provider_search_done": False,
        "intent": None,
        "next_agent": None,
        "active_workflows": [],
        "pending_questions": [],
        "status_events": [],
        "last_error": None,
        "tool_failures": [],
        "should_continue": True,
        "error": None,
        "last_question_type": None,
        "collected_fields": [],
    }

    # Run greeting node
    try:
        result = await graph.ainvoke(initial_state)

        # Extract greeting message
        greeting_msg = None
        if result.get("messages"):
            last_msg = result["messages"][-1]
            if isinstance(last_msg, AIMessage):
                content = last_msg.content
                greeting_msg = content if isinstance(content, str) else str(content)

        # Save greeting message to session
        if greeting_msg:
            await session_service.add_message(
                session_id=session.session_id, role="assistant", content=greeting_msg
            )

        return StartSessionResponse(
            session_id=session.session_id,
            message=greeting_msg
            or "Hello! I'm Vaidya, your AI health assistant. I can help with symptom checking, finding healthcare providers, reviewing medications, and more. How can I assist you today?",
            status="active",
        )

    except Exception as e:
        logger.error(f"Error starting session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start session: {str(e)}",
        )


@router.post("/message")
async def send_message(
    request: MessageRequest, current_user: Dict[str, str] = Depends(get_current_user)
):
    """
    Send a message in an existing Vaidya session.

    Streams the response using Server-Sent Events (SSE).

    Vaidya (root supervisor) analyzes your message and intelligently routes to
    the appropriate specialist agent (symptom analyst, history, drug checker,
    provider locator, etc.)
    """
    session_service = get_session_service()
    graph = get_vaidya_graph()

    # Verify session exists and belongs to user
    session = await session_service.get_session(request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    if session.user_id != current_user["userId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session",
        )

    # Save user message
    await session_service.add_message(
        session_id=request.session_id, role="user", content=request.message
    )

    # Build state from session
    messages = [
        (
            HumanMessage(content=msg.content)
            if msg.role == "user"
            else AIMessage(content=msg.content)
        )
        for msg in session.messages
    ]
    messages.append(HumanMessage(content=request.message))

    # Load agent state from session to preserve progress
    agent_state = session.agent_state

    # Apply conversation summary context window to limit LLM token pressure.
    # When the session has a stored summary (set by summarization_node) and the
    # raw message history is long, trim to last 10 messages and prepend the
    # clinical summary as a SystemMessage instead of sending the full history.
    stored_summary = getattr(agent_state, "conversation_summary", None)
    if stored_summary and len(messages) > 12:
        summary_sys_msg = SystemMessage(
            content=f"[Clinical Summary of Prior Conversation]\n\n{stored_summary}"
        )
        tail = messages[-10:]  # last 5 exchanges
        messages = [summary_sys_msg] + tail
        logger.info(
            f"Applied context window for session {request.session_id}: "
            f"summary + {len(tail)} recent messages (was {len(session.messages) + 1})"
        )

    state: SymptomCheckState = {
        "messages": messages,
        "conversation_summary": getattr(
            agent_state, "conversation_summary", None
        ),  # persist summary across turns
        "message_count": len(messages),
        "user_id": session.user_id,
        "user_email": session.user_email,
        "session_id": session.session_id,
        # Symptoms from session (CRITICAL: Load all fields)
        "chief_complaint": session.symptoms_collected.chief_complaint,
        "location": session.symptoms_collected.location,
        "duration": session.symptoms_collected.duration,
        "severity": session.symptoms_collected.severity,
        "triggers": session.symptoms_collected.triggers,
        "relievers": session.symptoms_collected.relievers,
        "associated_symptoms": session.symptoms_collected.associated_symptoms or [],
        # Agent progress state (loaded from session to preserve context)
        "current_stage": agent_state.current_stage,
        "questions_asked": agent_state.questions_asked,
        "golden_4_complete": agent_state.golden_4_complete,
        "red_flags_detected": [],
        "classification": None,
        "differential_diagnosis": [],
        "recommendations": [],
        "urgency_score": None,
        # Question context tracking (prevents repeated questions)
        "last_question_type": agent_state.last_question_type,
        "collected_fields": agent_state.collected_fields,
        # Multi-agent state (loaded from session)
        "intent": agent_state.intent,
        "next_agent": agent_state.next_agent,
        "active_workflows": agent_state.active_workflows,
        # Medical history state
        "patient_id": agent_state.patient_id,
        "history_summary": None,
        "chronic_conditions": [],
        "recent_labs": [],
        "current_medications": [],
        "allergies": [],
        "risk_level": None,
        "history_analyzed": agent_state.history_analyzed,
        # Preventive care state
        "preventive_recommendations": [],
        "chronic_care_plans": [],
        "preventive_care_analyzed": agent_state.preventive_care_analyzed,
        "age": agent_state.age,
        "sex": agent_state.sex,
        # Drug interaction state
        "med_list_from_user": agent_state.med_list_from_user,
        "interaction_results": [],
        "interaction_check_done": agent_state.interaction_check_done,
        # Provider locator state
        "user_location": None,
        "provider_query": agent_state.provider_query,
        "nearby_providers": [],
        "provider_search_done": agent_state.provider_search_done,
        # Control
        "pending_questions": [],
        "status_events": [],
        "last_error": None,
        "tool_failures": [],
        "should_continue": True,
        "error": None,
    }

    # Log loaded state for verification
    logger.info(
        f"Loaded state from session {request.session_id}: "
        f"chief_complaint={state['chief_complaint']}, "
        f"location={state['location']}, "
        f"duration={state['duration']}, "
        f"severity={state['severity']}, "
        f"questions_asked={state['questions_asked']}, "
        f"golden_4_complete={state['golden_4_complete']}, "
        f"last_question_type={state['last_question_type']}, "
        f"collected_fields={state['collected_fields']}"
    )

    async def event_generator():
        """Generate SSE events from agent output."""
        try:
            full_response = ""
            final_state = None
            current_message_content = ""
            token_count = 0
            current_node = None
            node_buffer = ""
            initial_message_count = len(state.get("messages", []))
            # Track new AI messages independently — plain dict.update() on final_state
            # overwrites the 'messages' key on each on_chain_end, losing earlier messages.
            accumulated_ai_messages: list = []

            # Define internal nodes that should NEVER stream output to frontend
            # These nodes only update state and make routing decisions
            SILENT_NODES = {
                "vaidya",  # Vaidya supervisor routing decisions
                "analyze_input",  # Symptom data extraction
                "red_flag_check",  # Emergency flag detection
                "assess",  # Internal assessment logic
                "triage",  # Triage classification
                "save_assessment",  # Database operations
                "check_completion",  # Conditional checks
                "route_after_supervisor",  # Routing logic
                "should_continue",  # Conditional edge function
            }

            logger.info(f"Starting SSE stream for session: {request.session_id}")

            # Stream from agent using astream_events for token-level streaming
            async for event in graph.astream_events(state, version="v2"):
                kind = event.get("event")

                # Track which node is currently executing
                if kind == "on_chain_start":
                    name = event.get("name", "")
                    current_node = name
                    node_buffer = ""
                    is_silent = current_node in SILENT_NODES
                    logger.info(f"Entering node: {name} (silent={is_silent})")

                # Handle LLM token streaming
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        token = chunk.content
                        if token:
                            # Add to node buffer to check if it's JSON
                            node_buffer += token

                            # **PRIMARY FILTER: Skip streaming from internal/silent nodes**
                            should_filter = False

                            # Filter by node name - internal nodes never stream
                            if current_node in SILENT_NODES:
                                should_filter = True
                                # Only log once per node, not for every token
                                if len(node_buffer) < 50:
                                    logger.debug(
                                        f"🔇 Filtering output from silent node: {current_node}"
                                    )
                            else:
                                # For non-silent nodes, also check if content is JSON
                                stripped = node_buffer.strip()
                                # Check if content looks like JSON (structured data)
                                if len(stripped) > 0 and stripped[0] in ("{", "["):
                                    # Check if we have enough content to determine if it's JSON
                                    if len(stripped) > 10:
                                        try:
                                            # Try to parse as JSON to confirm
                                            json.loads(stripped)
                                            should_filter = True
                                            logger.debug(
                                                f"Filtering JSON output from node: {current_node}"
                                            )
                                        except (json.JSONDecodeError, ValueError):
                                            # Not valid JSON yet - wait for more tokens
                                            # After accumulating significant content, decide
                                            if len(stripped) > 500:
                                                # Use bracket counting to detect ongoing JSON
                                                # accumulation instead of blindly unfiltering at
                                                # 100 chars (was streaming partial JSON to frontend).
                                                open_count = stripped.count(
                                                    "{"
                                                ) + stripped.count("[")
                                                close_count = stripped.count(
                                                    "}"
                                                ) + stripped.count("]")
                                                if open_count > close_count:
                                                    # Still accumulating an open JSON structure
                                                    should_filter = True
                                                else:
                                                    # Balanced/malformed — assume not pure JSON
                                                    should_filter = False
                            # Stream tokens from conversational nodes only (non-JSON output)
                            if not should_filter:
                                token_count += 1
                                current_message_content += token
                                full_response = current_message_content
                                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                await asyncio.sleep(0.001)

                # Track final state from the main graph chain end
                elif kind == "on_chain_end":
                    # Get the output from the event
                    name = event.get("name", "")
                    outputs = event.get("data", {}).get("output")

                    # Capture final state, merging non-messages fields properly.
                    # plain dict.update() would overwrite the 'messages' key on every
                    # node chain_end, destroying messages from earlier nodes.  Track new
                    # AI messages in accumulated_ai_messages; merge all other fields normally.
                    if outputs and isinstance(outputs, dict):
                        # Collect any new AI messages from this node
                        for msg in outputs.get("messages", []):
                            if isinstance(msg, AIMessage):
                                accumulated_ai_messages.append(msg)

                        # Merge non-messages state fields
                        if final_state is None:
                            final_state = {
                                k: v for k, v in outputs.items() if k != "messages"
                            }
                        else:
                            for k, v in outputs.items():
                                if k != "messages":
                                    final_state[k] = v

                        # **EMIT STATUS EVENTS** - Check for status events in the node output
                        if outputs.get("status_events"):
                            for status_event in outputs["status_events"]:
                                # Convert status event to user-friendly message
                                status_message = _status_event_to_message(status_event)
                                logger.info(
                                    f"Emitting status event: {status_event} -> {status_message}"
                                )
                                yield f"data: {json.dumps({'type': 'status', 'content': status_message})}\n\n"
                                await asyncio.sleep(0.01)

                        # Log merged state after each node (for debugging)
                        logger.info(
                            f"Merged state after {name}: "
                            f"chief_complaint={final_state.get('chief_complaint')}, "
                            f"location={final_state.get('location')}, "
                            f"duration={final_state.get('duration')}, "
                            f"severity={final_state.get('severity')}, "
                            f"golden_4_complete={final_state.get('golden_4_complete')}, "
                            f"last_question_type={final_state.get('last_question_type')}"
                        )

                    # Reset for next node
                    current_node = None
                    node_buffer = ""

            logger.info(
                f"Streamed {token_count} tokens for session: {request.session_id}"
            )

            # If no tokens were streamed, check for NEW AI messages accumulated from nodes
            # (This handles nodes that return complete messages without streaming)
            if token_count == 0 and accumulated_ai_messages:
                logger.info(
                    f"No tokens streamed — streaming last accumulated AI message "
                    f"({len(accumulated_ai_messages)} total new messages)"
                )
                # Stream the last (most recent) AI message
                for msg in reversed(accumulated_ai_messages):
                    content = msg.content
                    response_text = (
                        content if isinstance(content, str) else str(content)
                    )
                    if not response_text or not response_text.strip():
                        continue
                    logger.info(
                        f"Streaming complete message from state: {response_text[:100]}..."
                    )
                    for char in response_text:
                        full_response += char
                        yield f"data: {json.dumps({'type': 'token', 'content': char})}\n\n"
                        await asyncio.sleep(0.005)
                    break  # Only stream the most recent AI message
            elif token_count == 0:
                logger.warning(
                    f"No tokens streamed and no AI messages found. "
                    f"final_state exists: {final_state is not None}"
                )

            # Save assistant message to session
            if full_response:
                await session_service.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=full_response,
                )

            # Update session with collected symptoms and triage result from final state
            if final_state:
                session = await session_service.get_session(request.session_id)
                if session:
                    from app.models.session import (
                        SymptomsData,
                        TriageData,
                        AgentStateData,
                    )

                    # Only update non-None symptom fields to preserve existing data
                    if final_state.get("chief_complaint") is not None:
                        session.symptoms_collected.chief_complaint = final_state.get(
                            "chief_complaint"
                        )
                    if final_state.get("location") is not None:
                        session.symptoms_collected.location = final_state.get(
                            "location"
                        )
                    if final_state.get("duration") is not None:
                        session.symptoms_collected.duration = final_state.get(
                            "duration"
                        )
                    if final_state.get("severity") is not None:
                        session.symptoms_collected.severity = final_state.get(
                            "severity"
                        )
                    if final_state.get("triggers") is not None:
                        session.symptoms_collected.triggers = final_state.get(
                            "triggers"
                        )
                    if final_state.get("relievers") is not None:
                        session.symptoms_collected.relievers = final_state.get(
                            "relievers"
                        )
                    if final_state.get("associated_symptoms"):
                        session.symptoms_collected.associated_symptoms = (
                            final_state.get("associated_symptoms", [])
                        )

                    # Update agent progress state to preserve context
                    if final_state.get("current_stage") is not None:
                        session.agent_state.current_stage = str(
                            final_state.get("current_stage")
                        )
                    if final_state.get("questions_asked") is not None:
                        session.agent_state.questions_asked = int(
                            final_state.get("questions_asked", 0)
                        )
                    if final_state.get("golden_4_complete") is not None:
                        session.agent_state.golden_4_complete = bool(
                            final_state.get("golden_4_complete")
                        )
                    if final_state.get("intent") is not None:
                        session.agent_state.intent = final_state.get("intent")
                    if final_state.get("next_agent") is not None:
                        session.agent_state.next_agent = final_state.get("next_agent")
                    if final_state.get("active_workflows"):
                        session.agent_state.active_workflows = final_state.get(
                            "active_workflows", []
                        )

                    # Update medical history state
                    if final_state.get("patient_id") is not None:
                        session.agent_state.patient_id = final_state.get("patient_id")
                    if final_state.get("history_analyzed") is not None:
                        session.agent_state.history_analyzed = bool(
                            final_state.get("history_analyzed")
                        )

                    # Update preventive care state
                    if final_state.get("preventive_care_analyzed") is not None:
                        session.agent_state.preventive_care_analyzed = bool(
                            final_state.get("preventive_care_analyzed")
                        )
                    if final_state.get("age") is not None:
                        session.agent_state.age = final_state.get("age")
                    if final_state.get("sex") is not None:
                        session.agent_state.sex = final_state.get("sex")

                    # Update drug interaction state
                    if final_state.get("interaction_check_done") is not None:
                        session.agent_state.interaction_check_done = bool(
                            final_state.get("interaction_check_done")
                        )
                    if final_state.get("med_list_from_user"):
                        session.agent_state.med_list_from_user = final_state.get(
                            "med_list_from_user", []
                        )

                    # Update provider search state
                    if final_state.get("provider_search_done") is not None:
                        session.agent_state.provider_search_done = bool(
                            final_state.get("provider_search_done")
                        )
                    if final_state.get("provider_query") is not None:
                        session.agent_state.provider_query = final_state.get(
                            "provider_query"
                        )

                    # Update question context tracking
                    if final_state.get("last_question_type") is not None:
                        session.agent_state.last_question_type = final_state.get(
                            "last_question_type"
                        )
                    if final_state.get("collected_fields"):
                        session.agent_state.collected_fields = final_state.get(
                            "collected_fields", []
                        )

                    # Persist conversation summary so context window is applied next turn
                    if final_state.get("conversation_summary") is not None:
                        session.agent_state.conversation_summary = final_state.get(
                            "conversation_summary"
                        )

                    # Log what's being saved for verification
                    logger.info(
                        f"Saving to database for session {request.session_id}: "
                        f"chief_complaint={session.symptoms_collected.chief_complaint}, "
                        f"location={session.symptoms_collected.location}, "
                        f"duration={session.symptoms_collected.duration}, "
                        f"severity={session.symptoms_collected.severity}, "
                        f"questions_asked={session.agent_state.questions_asked}, "
                        f"golden_4_complete={session.agent_state.golden_4_complete}, "
                        f"last_question_type={session.agent_state.last_question_type}, "
                        f"collected_fields={session.agent_state.collected_fields}"
                    )

                    # Update triage result if available
                    if final_state.get("classification"):
                        session.triage_result = TriageData(
                            classification=final_state.get("classification"),
                            confidence=None,
                            red_flags=final_state.get("red_flags_detected", []),
                            differential_diagnosis=final_state.get(
                                "differential_diagnosis", []
                            ),
                            recommendations=final_state.get("recommendations", []),
                            urgency_score=final_state.get("urgency_score"),
                        )

                    # Mark session as completed if workflow finished
                    if final_state.get("current_stage") == "complete":
                        session.status = SessionStatus.COMPLETED
                        session.completed_at = datetime.utcnow()

                    await session_service.update_session(session)

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'session_id': request.session_id})}\n\n"

        except Exception as e:
            logger.error(f"Error in event stream: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx/proxies
        },
    )


@router.get("/session/{session_id}", response_model=SessionDetailsResponse)
async def get_session_details(
    session_id: str, current_user: Dict[str, str] = Depends(get_current_user)
):
    """
    Get details of a specific Vaidya session.

    Returns session metadata, messages, symptoms collected, and triage result.
    """
    session_service = get_session_service()

    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    if session.user_id != current_user["userId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session",
        )

    # Convert session models to response models
    from app.models.messages import MessageModel, SymptomsCollected, TriageResult

    messages = [
        MessageModel(role=msg.role, content=msg.content, timestamp=msg.timestamp)
        for msg in session.messages
    ]

    symptoms_collected = SymptomsCollected(
        chief_complaint=session.symptoms_collected.chief_complaint,
        location=session.symptoms_collected.location,
        duration=session.symptoms_collected.duration,
        severity=session.symptoms_collected.severity,
        triggers=session.symptoms_collected.triggers,
        associated_symptoms=session.symptoms_collected.associated_symptoms,
    )

    triage_result = None
    if session.triage_result:
        triage_result = TriageResult(
            classification=session.triage_result.classification,
            red_flags=session.triage_result.red_flags,
            differential_diagnosis=session.triage_result.differential_diagnosis,
            recommendations=session.triage_result.recommendations,
        )

    return SessionDetailsResponse(
        session_id=session.session_id,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        messages=messages,
        symptoms_collected=symptoms_collected,
        triage_result=triage_result,
    )


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str, current_user: Dict[str, str] = Depends(get_current_user)
):
    """
    Permanently delete a Vaidya session and all its messages.

    Only the owner of the session can delete it.
    Returns 204 No Content on success.
    """
    session_service = get_session_service()

    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    if session.user_id != current_user["userId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session",
        )

    deleted = await session_service.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session",
        )

    logger.info(f"Session {session_id} deleted by user {current_user['userId']}")
    # 204 — no response body


@router.get("/sessions", response_model=UserSessionsResponse)
async def get_user_sessions(
    limit: int = 20,
    offset: int = 0,
    current_user: Dict[str, str] = Depends(get_current_user),
):
    """
    Get list of all chat sessions for the current user.

    Returns paginated session summaries including a preview of the first user message.
    Ordered by most recent first.
    """
    session_service = get_session_service()

    sessions = await session_service.get_user_sessions(
        user_id=current_user["userId"], limit=limit, offset=offset
    )

    summaries = []
    for s in sessions:
        # Extract first user message as preview
        preview = None
        for msg in s.messages:
            if msg.role == "user":
                preview = msg.content[:80] + ("..." if len(msg.content) > 80 else "")
                break

        summaries.append(
            SessionSummary(
                session_id=s.session_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                status=s.status,
                message_count=s.message_count,
                preview=preview,
            )
        )

    return UserSessionsResponse(
        total=len(summaries),
        limit=limit,
        offset=offset,
        sessions=summaries,
    )


@router.get("/history", response_model=AssessmentHistoryResponse)
async def get_assessment_history(
    limit: int = 10,
    offset: int = 0,
    current_user: Dict[str, str] = Depends(get_current_user),
):
    """
    Get user's assessment history from Vaidya sessions.

    Returns paginated list of past assessments with key information.
    """
    assessment_service = get_assessment_service()

    assessments, total = await assessment_service.get_user_assessments(
        user_id=current_user["userId"], limit=limit, offset=offset
    )

    # Convert to summary format
    summaries = [
        AssessmentSummary(
            assessment_id=a.assessment_id,
            created_at=a.created_at,
            chief_complaint=a.chief_complaint,
            classification=a.classification,
            urgency_score=a.urgency_score,
            emergency_advised=a.emergency_advised,
        )
        for a in assessments
    ]

    return AssessmentHistoryResponse(
        total=total, limit=limit, offset=offset, assessments=summaries
    )
