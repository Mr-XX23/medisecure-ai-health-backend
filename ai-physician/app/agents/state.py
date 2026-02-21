"""LangGraph state definition for Symptom Analyst agent."""

from typing import TypedDict, Annotated, Sequence, Optional, List
from langchain_core.messages import BaseMessage
from operator import add


class SymptomCheckState(TypedDict):
    """State for the Symptom Analyst agent workflow."""

    # Conversation
    messages: Annotated[Sequence[BaseMessage], add]
    conversation_summary: Optional[str]  # Clinical summary for long conversations
    message_count: int

    # User context
    user_id: str
    user_email: str
    session_id: str

    # Clinical data (Golden 4 + extras)
    chief_complaint: Optional[str]
    location: Optional[str]
    duration: Optional[str]
    severity: Optional[int]  # 1-10 scale
    triggers: Optional[str]
    relievers: Optional[str]
    associated_symptoms: List[str]

    # Agent control flow
    current_stage: str  # "greeting", "gathering", "assessing", "triaging", "complete"
    questions_asked: int
    golden_4_complete: bool
    red_flags_detected: List[str]

    # Question context tracking (prevents ambiguous numeric answers)
    last_question_type: Optional[
        str
    ]  # ASK_CHIEF_COMPLAINT, ASK_LOCATION, ASK_DURATION, ASK_SEVERITY, etc.
    collected_fields: List[str]  # Track which Golden 4 fields are filled

    # Triage output
    classification: Optional[str]  # HOME, GP_SOON, GP_24H, ER_NOW
    differential_diagnosis: List[str]
    recommendations: List[str]
    urgency_score: Optional[int]  # 1-10

    # Medical History (from History Agent)
    patient_id: Optional[str]
    history_summary: Optional[str]
    chronic_conditions: List[str]
    recent_labs: List[dict]  # [{name, value, date, is_abnormal}, ...]
    current_medications: List[str]
    allergies: List[str]
    risk_level: Optional[str]  # LOW, MODERATE, HIGH
    history_analyzed: bool

    # Preventive Care & Chronic Management (from Preventive Care Agent)
    preventive_recommendations: List[
        dict
    ]  # [{category, name, reason, status, urgency_note}, ...]
    chronic_care_plans: List[
        dict
    ]  # [{condition, risk_level, targets, monitoring, lifestyle, doctor_followup_topics}, ...]
    preventive_care_analyzed: bool

    # Patient Demographics (for preventive care)
    age: Optional[int]
    sex: Optional[str]  # "male", "female", "other"

    # Drug Interaction Check (from Drug Agent)
    med_list_from_user: List[str]  # Medications mentioned by user in chat
    interaction_results: List[
        dict
    ]  # [{drug_a, drug_b, severity, description, management}, ...]
    interaction_check_done: bool

    # Provider Locator (from Provider Agent)
    user_location: Optional[dict]  # {lat: float, lng: float}
    provider_query: Optional[
        str
    ]  # Specialty or type (e.g., "cardiologist", "hospital")
    nearby_providers: List[
        dict
    ]  # [{place_id, name, address, lat, lng, rating, reviews, score, types, distance_km}, ...]
    provider_search_done: bool

    # Vaidya Supervisor Control (routing and orchestration)
    intent: Optional[
        str
    ]  # SYMPTOM_CHECK, FOLLOWUP_QUESTION, PROVIDER_SEARCH, MEDICATION_SAFETY, GENERAL_HEALTH, OTHER
    next_agent: Optional[
        str
    ]  # Next agent to execute (Symptom_Analyst, History_Agent, etc.)
    active_workflows: List[str]  # Currently active workflow names
    pending_questions: List[
        dict
    ]  # [{"source": "Vaidya", "topic": "age", "text": "..."}]
    status_events: List[
        str
    ]  # Status updates for streaming (e.g., "STATUS:CHECKING_HISTORY")
    last_error: Optional[str]  # Last error message
    tool_failures: List[str]  # List of tools that failed

    # Control flags
    should_continue: bool
    error: Optional[str]
