"""Triage classification enums and models."""

from enum import Enum


class TriageClassification(str, Enum):
    """Triage urgency levels."""

    HOME = "HOME"  # Self-care at home
    GP_SOON = "GP_SOON"  # See primary care within 1-2 weeks
    GP_24H = "GP_24H"  # See doctor within 24 hours
    ER_NOW = "ER_NOW"  # Seek emergency care immediately


class Probability(str, Enum):
    """Probability levels for differential diagnosis."""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class SessionStatus(str, Enum):
    """Session status."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
