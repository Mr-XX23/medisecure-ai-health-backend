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
from app.agents.prompts import DRUG_INTERACTION_PROMPT
from langchain_core.messages import SystemMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)


async def analyze_drug_interactions(
    medications: List[str],
    user_medications: List[str] | None = None,
) -> Dict:
    """
    Analyze medications for potential drug-drug interactions.

    Args:
        medications: List of current medications from medical history
        user_medications: Additional medications mentioned by user (optional)

    Returns:
        Dict with:
            - interactions: List of interaction dictionaries
            - summary: AI-generated plain language explanation
            - has_major_interactions: Boolean flag
            - has_moderate_interactions: Boolean flag
    """
    logger.info("Starting drug interaction analysis")

    # Combine medication lists
    all_meds = list(set(medications + (user_medications or [])))

    if len(all_meds) < 2:
        logger.info("Less than 2 medications, skipping interaction check")
        return {
            "interactions": [],
            "summary": "You have fewer than 2 medications listed, so no drug interactions can occur. "
            "If you're taking other medications, please let me know so I can check for interactions.",
            "has_major_interactions": False,
            "has_moderate_interactions": False,
        }

    # Check for interactions
    logger.info(f"Checking interactions for {len(all_meds)} medications: {all_meds}")
    interactions = check_drug_interactions(all_meds)

    if not interactions:
        logger.info("No interactions found")
        return {
            "interactions": [],
            "summary": f"✅ Good news! I didn't find any known interactions between your {len(all_meds)} medications. "
            "However, it's still a good idea to have your pharmacist review all your medications periodically.",
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
        summary = await _generate_interaction_explanation(all_meds, interactions)
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
) -> str:
    """
    Generate a clear, patient-friendly explanation of drug interactions using LLM.

    Args:
        medications: List of medication names
        interactions: List of interaction dictionaries

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
    )

    # Get LLM response
    system_msg = SystemMessage(
        content="You are a medication safety assistant. Explain drug interactions clearly and safely."
    )
    human_msg = HumanMessage(content=prompt)

    response = await llm.ainvoke([system_msg, human_msg])

    return str(response.content) if response.content else ""


def extract_medications_from_text(text: str) -> List[str]:
    """
    Extract medication names from free text using simple pattern matching.

    This is a basic implementation. In production, could use NER (Named Entity Recognition)
    or a medical NLP model.

    Args:
        text: User input text

    Returns:
        List of potential medication names
    """
    # TODO: Implement better NER for medication extraction
    # For now, return empty list - medications will come from history
    return []


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


def prioritize_interactions(interactions: List[Dict]) -> List[Dict]:
    """
    Prioritize interactions by severity and clinical significance.

    Args:
        interactions: List of all detected interactions

    Returns:
        Sorted list with most important interactions first
    """
    # Severity order
    severity_priority = {"MAJOR": 0, "MODERATE": 1, "MINOR": 2}

    # Sort by severity
    sorted_interactions = sorted(
        interactions, key=lambda x: severity_priority.get(x["severity"], 3)
    )

    return sorted_interactions
