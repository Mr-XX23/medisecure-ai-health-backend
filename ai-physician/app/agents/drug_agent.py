"""Drug Interaction Agent.

This agent analyzes medication lists and checks for potential drug-drug interactions,
providing clear explanations and safety guidance.
"""

from typing import List, Dict
from app.tools.drug_interactions import (
    check_drug_interactions,
    normalize_drug_names,
    format_interaction_for_display,
)
from app.config.llm_config import get_drug_model
from app.agents.prompts import (
    DRUG_INTERACTION_PROMPT,
    DRUG_INSUFFICIENT_MEDS_PROMPT,
    DRUG_NO_INTERACTIONS_PROMPT,
)
from langchain_core.messages import SystemMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)


async def analyze_drug_interactions(
    medications: List[str],
    user_medications: List[str] | None = None,
    patient_age: str = "unknown",
    patient_conditions: List[str] | None = None,
    patient_allergies: List[str] | None = None,
    chief_complaint: str = "",
) -> Dict:
    """
    Analyze medications for potential drug-drug interactions.

    Args:
        medications: List of current medications from medical history
        user_medications: Additional medications mentioned by user (optional)
        patient_age: Patient age string for context-aware responses
        patient_conditions: Known chronic conditions
        patient_allergies: Known drug allergies
        chief_complaint: Current symptom / reason for visit

    Returns:
        Dict with:
            - interactions: List of interaction dictionaries
            - summary: AI-generated plain language explanation
            - has_major_interactions: Boolean flag
            - has_moderate_interactions: Boolean flag
    """
    logger.info("Starting drug interaction analysis")

    conditions_str = ", ".join(patient_conditions or []) or "none reported"
    allergies_str = ", ".join(patient_allergies or []) or "none reported"

    # Combine medication lists
    all_meds = list(set(medications + (user_medications or [])))
    llm = get_drug_model()

    if len(all_meds) < 2:
        logger.info("Less than 2 medications, skipping interaction check")
        try:
            insufficient_prompt = DRUG_INSUFFICIENT_MEDS_PROMPT.format(
                patient_age=patient_age,
                known_conditions=conditions_str,
                patient_allergies=allergies_str,
                medications_listed=", ".join(all_meds) if all_meds else "none",
                chief_complaint=chief_complaint or "not specified",
            )
            resp = await llm.ainvoke([HumanMessage(content=insufficient_prompt)])
            summary = str(resp.content) if resp.content else ""
        except Exception as e:
            logger.error(f"DRUG_INSUFFICIENT_MEDS_PROMPT LLM failed: {e}")
            summary = (
                "Please share your complete medication list (prescription, OTC, and supplements) "
                "so I can check for any interactions."
            )
        return {
            "interactions": [],
            "summary": summary,
            "has_major_interactions": False,
            "has_moderate_interactions": False,
        }

    # Check for interactions
    logger.info(f"Checking interactions for {len(all_meds)} medications: {all_meds}")
    interactions = check_drug_interactions(all_meds)

    if not interactions:
        logger.info("No interactions found")
        try:
            no_interaction_prompt = DRUG_NO_INTERACTIONS_PROMPT.format(
                patient_age=patient_age,
                known_conditions=conditions_str,
                patient_allergies=allergies_str,
                medications_list=", ".join(all_meds),
                chief_complaint=chief_complaint or "not specified",
            )
            resp = await llm.ainvoke([HumanMessage(content=no_interaction_prompt)])
            summary = str(resp.content) if resp.content else ""
        except Exception as e:
            logger.error(f"DRUG_NO_INTERACTIONS_PROMPT LLM failed: {e}")
            summary = (
                f"No known interactions were identified between your {len(all_meds)} medications. "
                "Keep your pharmacist updated if any new medication is added."
            )
        return {
            "interactions": [],
            "summary": summary,
            "has_major_interactions": False,
            "has_moderate_interactions": False,
        }

    # Categorize interactions
    has_major = any(i["severity"] == "MAJOR" for i in interactions)
    has_moderate = any(i["severity"] == "MODERATE" for i in interactions)

    logger.info(
        f"Found {len(interactions)} interactions (Major: {has_major}, Moderate: {has_moderate})"
    )

    # Generate AI explanation
    try:
        summary = await _generate_interaction_explanation(
            all_meds,
            interactions,
            patient_age=patient_age,
            patient_conditions=conditions_str,
            patient_allergies=allergies_str,
        )
    except Exception as e:
        logger.error(f"Error generating AI explanation: {e}", exc_info=True)
        # Fallback to simple formatted output
        summary = format_interaction_for_display(interactions)
        summary += "\n\n⚠️ **Important**: Do not stop or change any medications without consulting your doctor or pharmacist."

    return {
        "interactions": interactions,
        "summary": summary,
        "has_major_interactions": has_major,
        "has_moderate_interactions": has_moderate,
    }


async def _generate_interaction_explanation(
    medications: List[str],
    interactions: List[Dict],
    patient_age: str = "unknown",
    patient_conditions: str = "none reported",
    patient_allergies: str = "none reported",
) -> str:
    """
    Generate a clear, patient-friendly explanation of drug interactions using LLM.

    Args:
        medications: List of medication names
        interactions: List of interaction dictionaries
        patient_age: Patient age for personalised guidance
        patient_conditions: Known conditions (string)
        patient_allergies: Known allergies (string)

    Returns:
        Plain language explanation as string
    """
    # Llama-4-Scout-17B - Drug Interaction: strong clinical explanation + structured formatting
    llm = get_drug_model()

    # Format medications list
    meds_text = "\n".join([f"- {med.title()}" for med in medications])

    # Format interaction data
    interactions_text = []
    for i, interaction in enumerate(interactions, 1):
        interactions_text.append(
            f"{i}. {interaction['drug_a'].title()} + {interaction['drug_b'].title()}\n"
            f"   Severity: {interaction['severity']}\n"
            f"   Description: {interaction['description']}\n"
            f"   Clinical Effects: {interaction['clinical_effects']}\n"
            f"   Management: {interaction['management']}\n"
        )

    interaction_data = (
        "\n".join(interactions_text)
        if interactions_text
        else "No interactions detected."
    )

    # Create prompt
    prompt = DRUG_INTERACTION_PROMPT.format(
        medications_list=meds_text,
        interaction_data=interaction_data,
        patient_age=patient_age,
        patient_conditions=patient_conditions,
        patient_allergies=patient_allergies,
    )

    # Get LLM response — system prompt is embedded in DRUG_INTERACTION_PROMPT itself
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    return str(response.content) if response.content else ""


def should_check_interactions(
    medications: List[str],
    user_input: str = "",
) -> bool:
    """
    Determine if drug interaction check should be performed.

    Args:
        medications: List of medications from history
        user_input: Recent user input text

    Returns:
        Boolean indicating if check should be performed
    """
    # Check if user explicitly asked about interactions
    interaction_keywords = [
        "interaction",
        "interact",
        "medications",
        "medicines",
        "drugs",
        "mix",
        "take together",
        "safe to take",
        "combine",
    ]

    user_lower = user_input.lower() if user_input else ""
    asks_about_interactions = any(
        keyword in user_lower for keyword in interaction_keywords
    )

    # Always check if user asks, or if we have multiple medications
    return asks_about_interactions or len(medications) >= 2
