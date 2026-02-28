"""API request and response models."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.triage import TriageClassification, SessionStatus


class MessageRequest(BaseModel):
    """Request to send a message in a symptom check session."""

    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., max_length=2000, description="User message")
    user_location: Optional[dict] = Field(
        None,
        description="User GPS location {lat: float, lng: float} — required for ER hospital search",
    )


class StartSessionResponse(BaseModel):
    """Response when starting a new session."""

    session_id: str
    message: str
    status: str


class MessageModel(BaseModel):
    """Individual message in conversation."""

    role: str = Field(..., description="user or assistant")
    content: str
    timestamp: datetime


class SymptomsCollected(BaseModel):
    """Symptoms collected during session."""

    chief_complaint: Optional[str] = None
    location: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[int] = Field(None, ge=1, le=10)
    triggers: Optional[str] = None
    associated_symptoms: List[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    """Triage assessment result."""

    classification: Optional[TriageClassification] = None
    red_flags: List[str] = Field(default_factory=list)
    differential_diagnosis: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class AssessmentSummary(BaseModel):
    """Summary of a completed assessment."""

    assessment_id: str
    created_at: datetime
    chief_complaint: str
    classification: TriageClassification
    urgency_score: Optional[int] = None
    emergency_advised: bool = False


class AssessmentHistoryResponse(BaseModel):
    """Response containing user's assessment history."""

    total: int
    limit: int
    offset: int
    assessments: List[AssessmentSummary]


class SessionDetailsResponse(BaseModel):
    """Full session details response."""

    session_id: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    message_count: int
    messages: List[MessageModel]
    symptoms_collected: SymptomsCollected
    triage_result: Optional[TriageResult] = None


class SessionSummary(BaseModel):
    """Lightweight summary of a chat session for the history list."""

    session_id: str
    created_at: datetime
    updated_at: datetime
    status: SessionStatus
    message_count: int
    preview: Optional[str] = None  # First user message truncated to 80 chars


class UserSessionsResponse(BaseModel):
    """Response containing paginated list of user sessions."""

    total: int
    limit: int
    offset: int
    sessions: List[SessionSummary]
