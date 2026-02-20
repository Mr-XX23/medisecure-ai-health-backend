"""FHIR client for fetching patient medical history.

This module provides functions to retrieve Electronic Health Record (EHR) data
in FHIR format. Currently uses mock data for development.

In production, this would connect to:
- HAPI FHIR server
- Epic FHIR API
- Cerner/Oracle Health FHIR API
- Or custom EHR integration
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


# Mock patient database (simulating Synthea-generated data)
MOCK_PATIENTS = {
    "patient_001": {
        "id": "patient_001",
        "name": "John Smith",
        "date_of_birth": "1978-05-15",
        "address": "123 Main St, Anytown, USA",
        "phone": "555-123-4567",
        "zip_code": "12345",
        "city": "Anytown",
        "gender": "male",
        "age": 47,
    },
    "patient_002": {
        "id": "patient_002",
        "name": "Jane Doe",
        "date_of_birth": "1985-09-22",
        "address": "456 Oak Ave, Somewhere, USA",
        "phone": "555-987-6543",
        "zip_code": "67890",
        "city": "Somewhere",
        "gender": "female",
        "age": 40,
    },
}

# Mock conditions (diagnoses)
MOCK_CONDITIONS = {
    "patient_001": [
        {
            "code": "I10",
            "name": "Essential (primary) hypertension",
            "onset_date": "2018-03-15",
            "status": "active",
            "severity": "moderate",
        },
        {
            "code": "E11.9",
            "name": "Type 2 diabetes mellitus",
            "onset_date": "2020-07-22",
            "status": "active",
            "severity": "controlled",
        },
        {
            "code": "E78.5",
            "name": "Hyperlipidemia",
            "onset_date": "2019-11-10",
            "status": "active",
            "severity": "mild",
        },
    ],
    "patient_002": [
        {
            "code": "J45.909",
            "name": "Unspecified asthma, uncomplicated",
            "onset_date": "2010-04-12",
            "status": "active",
            "severity": "mild intermittent",
        },
    ],
}

# Mock observations (labs, vitals)
MOCK_OBSERVATIONS = {
    "patient_001": [
        {
            "code": "8480-6",
            "name": "Systolic Blood Pressure",
            "value": 145,
            "unit": "mmHg",
            "date": "2025-12-10",
            "is_abnormal": True,
            "reference_range": "90-120",
        },
        {
            "code": "8462-4",
            "name": "Diastolic Blood Pressure",
            "value": 92,
            "unit": "mmHg",
            "date": "2025-12-10",
            "is_abnormal": True,
            "reference_range": "60-80",
        },
        {
            "code": "4548-4",
            "name": "Hemoglobin A1c",
            "value": 7.2,
            "unit": "%",
            "date": "2025-11-15",
            "is_abnormal": True,
            "reference_range": "<5.7",
        },
        {
            "code": "2089-1",
            "name": "LDL Cholesterol",
            "value": 135,
            "unit": "mg/dL",
            "date": "2025-11-15",
            "is_abnormal": True,
            "reference_range": "<100",
        },
        {
            "code": "8480-6",
            "name": "Systolic Blood Pressure",
            "value": 152,
            "unit": "mmHg",
            "date": "2025-09-05",
            "is_abnormal": True,
            "reference_range": "90-120",
        },
    ],
    "patient_002": [
        {
            "code": "8480-6",
            "name": "Systolic Blood Pressure",
            "value": 118,
            "unit": "mmHg",
            "date": "2025-12-01",
            "is_abnormal": False,
            "reference_range": "90-120",
        },
        {
            "code": "8462-4",
            "name": "Diastolic Blood Pressure",
            "value": 76,
            "unit": "mmHg",
            "date": "2025-12-01",
            "is_abnormal": False,
            "reference_range": "60-80",
        },
    ],
}

# Mock medications
MOCK_MEDICATIONS = {
    "patient_001": [
        {
            "name": "Lisinopril 10 mg",
            "generic_name": "Lisinopril",
            "class": "ACE Inhibitor",
            "indication": "Hypertension",
            "start_date": "2018-03-15",
            "status": "active",
        },
        {
            "name": "Metformin 1000 mg",
            "generic_name": "Metformin",
            "class": "Biguanide",
            "indication": "Type 2 Diabetes",
            "start_date": "2020-07-22",
            "status": "active",
        },
        {
            "name": "Atorvastatin 20 mg",
            "generic_name": "Atorvastatin",
            "class": "Statin",
            "indication": "Hyperlipidemia",
            "start_date": "2019-11-10",
            "status": "active",
        },
        {
            "name": "Aspirin 81 mg",
            "generic_name": "Aspirin",
            "class": "Antiplatelet",
            "indication": "Cardiovascular protection",
            "start_date": "2020-01-15",
            "status": "active",
        },
    ],
    "patient_002": [
        {
            "name": "Albuterol inhaler",
            "generic_name": "Albuterol",
            "class": "Short-acting beta agonist",
            "indication": "Asthma rescue",
            "start_date": "2010-04-12",
            "status": "active",
        },
    ],
}

# Mock allergies
MOCK_ALLERGIES = {
    "patient_001": [
        {
            "substance": "Penicillin",
            "reaction": "Hives, difficulty breathing",
            "severity": "severe",
            "onset": "1995-06-20",
        },
    ],
    "patient_002": [
        {
            "substance": "Latex",
            "reaction": "Skin rash",
            "severity": "mild",
            "onset": "2005-03-10",
        },
    ],
}


def get_patient_demographics(patient_id: str) -> Optional[Dict]:
    """
    Fetch basic patient demographics.

    Args:
        patient_id: Unique patient identifier

    Returns:
        Dictionary with patient demographics or None if not found
    """
    logger.info(f"Fetching demographics for patient: {patient_id}")
    return MOCK_PATIENTS.get(patient_id)


def get_patient_conditions(
    patient_id: str, last_n_years: int = 10, active_only: bool = True
) -> List[Dict]:
    """
    Fetch patient's chronic conditions and diagnoses.

    Args:
        patient_id: Unique patient identifier
        last_n_years: Limit to conditions from last N years
        active_only: Only return active conditions

    Returns:
        List of condition dictionaries
    """
    logger.info(
        f"Fetching conditions for patient: {patient_id} (last {last_n_years} years)"
    )

    conditions = MOCK_CONDITIONS.get(patient_id, [])

    if active_only:
        conditions = [c for c in conditions if c.get("status") == "active"]

    # Filter by date if needed (simplified - in real implementation would check onset_date)
    cutoff_date = datetime.now() - timedelta(days=last_n_years * 365)

    return conditions


def get_patient_observations(
    patient_id: str,
    observation_codes: Optional[List[str]] = None,
    last_n_years: int = 10,
) -> List[Dict]:
    """
    Fetch patient's lab results and vital signs.

    Args:
        patient_id: Unique patient identifier
        observation_codes: LOINC codes to filter (e.g., ['8480-6'] for systolic BP)
        last_n_years: Limit to observations from last N years

    Returns:
        List of observation dictionaries

    Common LOINC codes:
        8480-6: Systolic BP
        8462-4: Diastolic BP
        4548-4: Hemoglobin A1c
        2089-1: LDL Cholesterol
        2093-3: Total Cholesterol
    """
    logger.info(
        f"Fetching observations for patient: {patient_id} (codes: {observation_codes})"
    )

    observations = MOCK_OBSERVATIONS.get(patient_id, [])

    # Filter by codes if specified
    if observation_codes:
        observations = [obs for obs in observations if obs["code"] in observation_codes]

    # Filter by date
    cutoff_date = datetime.now() - timedelta(days=last_n_years * 365)
    # In production, would parse obs["date"] and filter

    # Sort by date (most recent first)
    observations.sort(key=lambda x: x["date"], reverse=True)

    return observations


def get_patient_medications(patient_id: str, active_only: bool = True) -> List[Dict]:
    """
    Fetch patient's current and past medications.

    Args:
        patient_id: Unique patient identifier
        active_only: Only return active medications

    Returns:
        List of medication dictionaries
    """
    logger.info(f"Fetching medications for patient: {patient_id}")

    medications = MOCK_MEDICATIONS.get(patient_id, [])

    if active_only:
        medications = [m for m in medications if m.get("status") == "active"]

    return medications


def get_patient_allergies(patient_id: str) -> List[Dict]:
    """
    Fetch patient's documented allergies and adverse reactions.

    Args:
        patient_id: Unique patient identifier

    Returns:
        List of allergy dictionaries
    """
    logger.info(f"Fetching allergies for patient: {patient_id}")
    return MOCK_ALLERGIES.get(patient_id, [])


def get_complete_patient_history(patient_id: str) -> Dict:
    """
    Fetch complete patient history in one call.

    This is a convenience function that calls all other functions
    and returns a comprehensive history bundle.

    Args:
        patient_id: Unique patient identifier

    Returns:
        Dictionary containing all patient data
    """
    logger.info(f"Fetching complete history for patient: {patient_id}")

    return {
        "demographics": get_patient_demographics(patient_id),
        "conditions": get_patient_conditions(patient_id),
        "observations": get_patient_observations(patient_id, last_n_years=2),
        "medications": get_patient_medications(patient_id),
        "allergies": get_patient_allergies(patient_id),
    }


# Helper function for filtering observations by type
def get_cardiovascular_labs(patient_id: str) -> List[Dict]:
    """Get cardiovascular-related labs (BP, cholesterol, etc.)"""
    codes = ["8480-6", "8462-4", "2089-1", "2093-3"]  # BP and cholesterol codes
    return get_patient_observations(patient_id, observation_codes=codes)


def get_diabetes_labs(patient_id: str) -> List[Dict]:
    """Get diabetes-related labs (HbA1c, glucose, etc.)"""
    codes = ["4548-4", "2339-0"]  # HbA1c and glucose codes
    return get_patient_observations(patient_id, observation_codes=codes)
