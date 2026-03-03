"""Vaidya AI Health Assistant - Shared State Definition."""

from typing import TypedDict, Annotated, Sequence, Optional, List, Any, Dict
from langchain_core.messages import BaseMessage
from operator import add


class VaidyaState(TypedDict):
    """
    Central state object for the Vaidya AI Health Assistant.
    Follows a ReAct-style pattern to allow the supervisor to reason and act.
    """

    # ── Conversation ──────────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], add]  # Accumulated via operator.add
    conversation_summary: Optional[str]              # Clinical summary (compression)
    summarized_message_count: int                    # Number of messages already included in summary
    message_count: int

    # ── User Context ──────────────────────────────────────────
    user_id: str
    user_email: str
    session_id: str
    user_location: Optional[dict]       # {lat: float, lng: float}

    # ── Clinical Fields (Golden 4) ─────────────────────────────
    chief_complaint: Optional[str]      # "chest pain", "headache", etc.
    location: Optional[str]             # Body location
    duration: Optional[str]             # "3 days", "since yesterday"
    severity: Optional[str]      # 1-10 scale or descriptor
    triggers: Optional[str]
    relievers: Optional[str]
    associated_symptoms: List[str]

    # ── Specialist Agent Outputs ──────────────────────────────
    # Triage
    classification: Optional[str]       # HOME|GP_SOON|GP_24H|ER_NOW
    differential_diagnosis: List[str]
    recommendations: List[str]
    urgency_score: Optional[str]        # 1-10 string or descriptor

    # History
    patient_id: Optional[str]
    history_summary: Optional[str]
    chronic_conditions: List[str]
    recent_labs: List[dict]             # [{name, value, date, is_abnormal}]
    current_medications: List[str]
    allergies: List[str]
    risk_level: Optional[str]           # LOW|MODERATE|HIGH
    history_analyzed: bool

    # Preventive / Chronic
    preventive_recommendations: List[dict]  # [{category, name, reason, status, urgency_note}]
    chronic_care_plans: List[dict]          # [{condition, risk_level, targets, monitoring, ...}]
    preventive_care_analyzed: bool
    age: Optional[int]
    sex: Optional[str]                  # male|female|other

    # Drug Interactions
    med_list_from_user: List[str]
    interaction_results: List[dict]     # [{drug_a, drug_b, severity, description, management}]
    interaction_check_done: bool

    # Provider Search
    provider_query: Optional[str]
    nearby_providers: List[dict]        # [{place_id, name, address, rating, distance_km, ...}]
    provider_search_done: bool

    # ── Emergency Response Mode ────────────────────────────────
    emergency_mode: bool                # Sticky once ER_NOW triggered
    emergency_type: Optional[str]       # cardiac_emergency, respiratory_emergency, etc.
    er_search_triggered: bool           # Prevents duplicate hospital lookup
    er_hospitals: Optional[List[dict]]  # Top 3 verified ERs with details
    er_emergency_numbers: Optional[dict] # {ambulance, police, fire}
    location_timeout: bool

    # ── Orchestration & Reasoning ──────────────────────────────
    current_stage: str                  # greeting|gathering|assessing|triaging|complete
    intent: Optional[str]               # SYMPTOM_CHECK|PROVIDER_SEARCH|MEDICATION_SAFETY|...
    next_agent: Optional[str]           # Next node to execute
    active_workflows: List[str]
    pending_questions: List[dict]
    status_events: List[str]            # SSE status event codes
    last_question_type: Optional[str]   # Prevents ambiguous follow-up answers
    collected_fields: List[str]
    questions_asked: int
    golden_4_complete: bool
    red_flags_detected: List[str]

    # ── Planning & ReAct ───────────────────────────────────────
    # Adding fields for Manus/Genspark style reasoning
    plan: Optional[str]                 # Current step-by-step plan
    thought: Optional[str]              # Internal reasoning before action
    tool_calls: List[dict]              # Tracking tool executions
    
    # ── Error Handling ─────────────────────────────────────────
    last_error: Optional[str]
    tool_failures: List[str]
    should_continue: bool
    error: Optional[str]

def create_initial_state(user_id: str, email: str, session_id: str) -> VaidyaState:
    """Create the initial empty state for a new Vaidya session."""
    return {
        "messages": [],
        "conversation_summary": None,
        "summarized_message_count": 0,
        "message_count": 0,
        "user_id": user_id,
        "user_email": email,
        "session_id": session_id,
        "user_location": None,
        "chief_complaint": None,
        "location": None,
        "duration": None,
        "severity": None,
        "triggers": None,
        "relievers": None,
        "associated_symptoms": [],
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
        "provider_query": None,
        "nearby_providers": [],
        "provider_search_done": False,
        "emergency_mode": False,
        "emergency_type": None,
        "er_search_triggered": False,
        "er_hospitals": [],
        "er_emergency_numbers": None,
        "location_timeout": False,
        "current_stage": "greeting",
        "intent": None,
        "next_agent": None,
        "active_workflows": [],
        "pending_questions": [],
        "status_events": [],
        "last_question_type": None,
        "collected_fields": [],
        "questions_asked": 0,
        "golden_4_complete": False,
        "red_flags_detected": [],
        "plan": None,
        "thought": None,
        "tool_calls": [],
        "last_error": None,
        "tool_failures": [],
        "should_continue": True,
        "error": None,
    }
