"""Medical History Analysis Agent.

This agent analyzes patient's medical history from EHR/FHIR data
and correlates it with current symptoms to provide context-aware triage.
"""

from typing import Dict, List, Optional
from app.tools.fhir_client import (
    get_patient_demographics,
    get_patient_conditions,
    get_patient_observations,
    get_patient_medications,
    get_patient_allergies,
)
from app.config.llm_config import get_history_model
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# --- Risk Assessment Logic ---


def calculate_cardiovascular_risk(
    conditions: List[Dict], observations: List[Dict], demographics: Dict
) -> str:
    """
    Calculate cardiovascular risk level based on conditions and labs.

    Returns: LOW, MODERATE, or HIGH
    """
    risk_factors = 0

    # Age risk
    age = demographics.get("age", 0)
    if age > 65:
        risk_factors += 2
    elif age > 50:
        risk_factors += 1

    # Chronic conditions
    condition_names = [c["name"].lower() for c in conditions]
    if any("hypertension" in name for name in condition_names):
        risk_factors += 2
    if any("diabetes" in name for name in condition_names):
        risk_factors += 2
    if any(
        "hyperlipidemia" in name or "cholesterol" in name for name in condition_names
    ):
        risk_factors += 1

    # Lab values
    for obs in observations:
        if obs["name"] == "Systolic Blood Pressure" and obs["value"] > 140:
            risk_factors += 1
        if obs["name"] == "LDL Cholesterol" and obs["value"] > 130:
            risk_factors += 1
        if obs["name"] == "Hemoglobin A1c" and obs["value"] > 7.0:
            risk_factors += 1

    # Determine risk level
    if risk_factors >= 5:
        return "HIGH"
    elif risk_factors >= 3:
        return "MODERATE"
    else:
        return "LOW"


def assess_risk_for_symptom(
    symptom: str,
    conditions: List[Dict],
    observations: List[Dict],
    demographics: Dict,
) -> str:
    """
    Assess overall risk level based on symptom type and patient history.

    Returns: LOW, MODERATE, or HIGH
    """
    symptom_lower = symptom.lower() if symptom else ""

    # Chest pain, cardiac symptoms
    if any(
        kw in symptom_lower
        for kw in ["chest pain", "chest pressure", "cardiac", "heart", "angina"]
    ):
        return calculate_cardiovascular_risk(conditions, observations, demographics)

    # Respiratory symptoms with asthma/COPD
    if any(
        kw in symptom_lower
        for kw in [
            "shortness of breath",
            "breathing",
            "wheezing",
            "cough",
            "respiratory",
        ]
    ):
        condition_names = [c["name"].lower() for c in conditions]
        if any("asthma" in name or "copd" in name for name in condition_names):
            return "MODERATE"

    # Neurological symptoms with diabetes
    if any(
        kw in symptom_lower
        for kw in ["numbness", "tingling", "neuropathy", "foot pain", "leg pain"]
    ):
        condition_names = [c["name"].lower() for c in conditions]
        if any("diabetes" in name for name in condition_names):
            return "MODERATE"

    # Default
    return "LOW"


# --- History Correlation Analysis ---


async def analyze_medical_history(
    patient_id: str,
    chief_complaint: Optional[str],
    current_symptoms: Dict,
) -> Dict:
    """
    Main function to fetch and analyze patient's medical history.

    Args:
        patient_id: Patient identifier
        chief_complaint: Current chief complaint
        current_symptoms: Dict with location, duration, severity, etc.

    Returns:
        Dictionary with history analysis results (includes status_events)
    """
    logger.info(f"Analyzing medical history for patient: {patient_id}")

    # Fetch all patient data
    demographics = get_patient_demographics(patient_id)
    if not demographics:
        logger.warning(f"Patient {patient_id} not found in system")
        return {
            "patient_found": False,
            "history_summary": "No patient record found.",
            "chronic_conditions": [],
            "recent_labs": [],
            "current_medications": [],
            "allergies": [],
            "risk_level": "UNKNOWN",
        }

    conditions = get_patient_conditions(patient_id, last_n_years=10)
    observations = get_patient_observations(patient_id, last_n_years=2)
    medications = get_patient_medications(patient_id)
    allergies = get_patient_allergies(patient_id)

    # Calculate risk level
    risk_level = assess_risk_for_symptom(
        chief_complaint or "", conditions, observations, demographics
    )

    # Prepare data for LLM analysis
    history_data = {
        "patient_found": True,
        "demographics": demographics,
        "chronic_conditions": [c["name"] for c in conditions],
        "recent_labs": [
            {
                "name": obs["name"],
                "value": obs["value"],
                "unit": obs["unit"],
                "date": obs["date"],
                "is_abnormal": obs["is_abnormal"],
            }
            for obs in observations[:10]  # Last 10 observations
        ],
        "current_medications": [m["name"] for m in medications],
        "allergies": [a["substance"] for a in allergies],
        "risk_level": risk_level,
    }

    # Generate narrative summary using LLM
    history_summary = await generate_history_summary(
        demographics,
        conditions,
        observations,
        medications,
        allergies,
        chief_complaint,
        current_symptoms,
        risk_level,
    )

    history_data["history_summary"] = history_summary

    return history_data


async def generate_history_summary(
    demographics: Dict,
    conditions: List[Dict],
    observations: List[Dict],
    medications: List[Dict],
    allergies: List[Dict],
    chief_complaint: Optional[str],
    current_symptoms: Dict,
    risk_level: str,
) -> str:
    """
    Generate a narrative history summary using LLM.

    This creates a clinically relevant summary that explains how
    the patient's history relates to their current symptoms.
    """
    from app.agents.prompts import HISTORY_ANALYSIS_PROMPT

    # Llama-4-Scout-17B - History Analysis: structured FHIR -> narrative clinical context
    llm = get_history_model()

    # Build prompt context
    age = demographics.get("age", "unknown")
    gender = demographics.get("gender", "unknown")

    conditions_text = (
        "\n".join(
            [
                f"  - {c['name']} (since {c['onset_date']}, {c['status']})"
                for c in conditions
            ]
        )
        or "  None documented"
    )

    # Group observations by type
    recent_labs_text = (
        "\n".join(
            [
                f"  - {obs['name']}: {obs['value']} {obs['unit']} ({obs['date']}) {'[ABNORMAL]' if obs['is_abnormal'] else ''}"
                for obs in observations[:8]
            ]
        )
        or "  None recent"
    )

    medications_text = (
        "\n".join([f"  - {m['name']} (for {m['indication']})" for m in medications])
        or "  None"
    )

    allergies_text = (
        "\n".join(
            [
                f"  - {a['substance']} ({a['severity']} - {a['reaction']})"
                for a in allergies
            ]
        )
        or "  None"
    )

    # Current symptom summary
    symptom_details = f"""
Chief Complaint: {chief_complaint or 'Not specified'}
Location: {current_symptoms.get('location', 'Not specified')}
Duration: {current_symptoms.get('duration', 'Not specified')}
Severity: {current_symptoms.get('severity', 'Not specified')}/10
"""

    prompt_content = HISTORY_ANALYSIS_PROMPT.format(
        age=age,
        gender=gender,
        conditions=conditions_text,
        recent_labs=recent_labs_text,
        medications=medications_text,
        allergies=allergies_text,
        symptom_details=symptom_details,
        risk_level=risk_level,
    )

    system_msg = SystemMessage(
        content="You are a medical history analysis specialist. Generate clear, clinically relevant summaries."
    )
    human_msg = HumanMessage(content=prompt_content)

    response = await llm.ainvoke([system_msg, human_msg])

    # Ensure we return a string
    content = response.content
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # If it's a list, join the parts
        return " ".join(str(part) for part in content)
    else:
        return str(content)


def format_history_for_triage(history_data: Dict) -> str:
    """
    Format history data for inclusion in triage decision.

    Returns a concise text summary for the triage agent.
    """
    if not history_data.get("patient_found"):
        return "No medical history available."

    parts = [
        f"Risk Level: {history_data['risk_level']}",
    ]

    if history_data.get("chronic_conditions"):
        parts.append(
            f"Chronic Conditions: {', '.join(history_data['chronic_conditions'][:3])}"
        )

    if history_data.get("current_medications"):
        parts.append(f"Medications: {len(history_data['current_medications'])} active")

    if history_data.get("allergies"):
        parts.append(f"Allergies: {', '.join(history_data['allergies'])}")

    abnormal_labs = [
        lab for lab in history_data.get("recent_labs", []) if lab.get("is_abnormal")
    ]
    if abnormal_labs:
        parts.append(f"Recent abnormal labs: {len(abnormal_labs)}")

    return " | ".join(parts)
