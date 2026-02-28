"""MongoDB schema for symptom sessions."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.triage import SessionStatus, TriageClassification
import uuid


class Message(BaseModel):
    """Individual message in a session."""

    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)


class SymptomsData(BaseModel):
    """Clinical symptom data (Golden 4 + extras)."""

    chief_complaint: Optional[str] = None
    location: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=1, le=10)
    triggers: Optional[str] = None
    relievers: Optional[str] = None
    associated_symptoms: List[str] = Field(default_factory=list)


class TriageData(BaseModel):
    """Triage assessment data."""

    classification: Optional[TriageClassification] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    red_flags: List[str] = Field(default_factory=list)
    differential_diagnosis: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    urgency_score: Optional[int] = Field(default=None, ge=1, le=10)


class AgentStateData(BaseModel):
    """Agent workflow state tracking - preserves progress between messages."""

    current_stage: str = "greeting"
    questions_asked: int = 0
    golden_4_complete: bool = False

    # Question context tracking (prevents repeated questions)
    last_question_type: Optional[str] = None  # ASK_CHIEF_COMPLAINT, ASK_LOCATION, etc.
    collected_fields: List[str] = Field(
        default_factory=list
    )  # Track which Golden 4 fields are filled

    # Multi-agent tracking
    intent: Optional[str] = None
    next_agent: Optional[str] = None
    active_workflows: List[str] = Field(default_factory=list)

    # Medical history integration
    patient_id: Optional[str] = None
    history_analyzed: bool = False

    # Preventive care
    preventive_care_analyzed: bool = False
    age: Optional[int] = None
    sex: Optional[str] = None

    # Drug interactions
    interaction_check_done: bool = False
    med_list_from_user: List[str] = Field(default_factory=list)

    # Provider search
    provider_search_done: bool = False
    provider_query: Optional[str] = None

    # Context management
    conversation_summary: Optional[str] = None  # Clinical summary for long sessions

    # Emergency Response Mode (persisted so sticky mode survives reconnects)
    emergency_mode: bool = False
    emergency_type: Optional[str] = None
    er_search_triggered: bool = False
    er_hospitals: List[dict] = Field(default_factory=list)
    er_emergency_numbers: Optional[dict] = None


class SymptomSession(BaseModel):
    """Symptom check session document."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: str
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Conversation tracking
    message_count: int = 0
    messages: List[Message] = Field(default_factory=list)

    # Clinical context
    symptoms_collected: SymptomsData = Field(default_factory=lambda: SymptomsData())

    # Triage outcome
    triage_result: Optional[TriageData] = None

    # Agent workflow state (preserves progress between messages)
    agent_state: AgentStateData = Field(default_factory=lambda: AgentStateData())

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "user123",
                "user_email": "user@example.com",
                "status": "active",
                "message_count": 3,
                "symptoms_collected": {"chief_complaint": "headache", "severity": 7},
            }
        }
