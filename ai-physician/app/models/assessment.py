"""MongoDB schema for triage assessments."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.models.triage import TriageClassification, Probability
import uuid


class DifferentialDiagnosis(BaseModel):
    """A single differential diagnosis entry."""

    condition: str
    probability: Probability
    reasoning: str


class TriageAssessment(BaseModel):
    """Completed triage assessment document."""

    assessment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Clinical summary
    chief_complaint: str
    clinical_summary: str
    symptoms: dict = Field(default_factory=dict)

    # Triage decision
    classification: TriageClassification
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    urgency_score: int = Field(..., ge=1, le=10)
    red_flags_detected: List[str] = Field(default_factory=list)

    # Diagnostic reasoning
    differential_diagnosis: List[DifferentialDiagnosis] = Field(default_factory=list)

    # Recommendations
    recommendations: List[str] = Field(default_factory=list)
    when_to_seek_care: str
    self_care_advice: List[str] = Field(default_factory=list)

    # Safety
    disclaimers_shown: bool = True
    emergency_advised: bool = False

    # Metadata
    conversation_length: int
    processing_time_seconds: float
    model_used: str = "multi-model"

    class Config:
        json_schema_extra = {
            "example": {
                "assessment_id": "123e4567-e89b-12d3-a456-426614174000",
                "session_id": "abc123",
                "user_id": "user456",
                "chief_complaint": "severe headache",
                "classification": "GP_24H",
                "confidence_score": 0.85,
                "urgency_score": 7,
            }
        }
