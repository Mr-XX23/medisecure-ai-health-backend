"""Tools package for AI Physician agents."""

from app.tools.fhir_client import (
    get_patient_demographics,
    get_patient_conditions,
    get_patient_observations,
    get_patient_medications,
    get_patient_allergies,
)

__all__ = [
    "get_patient_demographics",
    "get_patient_conditions",
    "get_patient_observations",
    "get_patient_medications",
    "get_patient_allergies",
]
