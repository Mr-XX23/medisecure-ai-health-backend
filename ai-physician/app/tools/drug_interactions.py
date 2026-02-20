"""Drug Interaction Checker Tool.

This module provides functions to normalize drug names and check for drug-drug interactions.
Currently uses mock data for MVP. Can be connected to DrugBank API or similar service in production.
"""

from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


# Brand name to generic name mapping (common medications)
DRUG_NAME_MAPPING = {
    # Pain/Anti-inflammatory
    "tylenol": "acetaminophen",
    "advil": "ibuprofen",
    "motrin": "ibuprofen",
    "aleve": "naproxen",
    "aspirin": "aspirin",
    # Cardiovascular
    "prinivil": "lisinopril",
    "zestril": "lisinopril",
    "norvasc": "amlodipine",
    "lopressor": "metoprolol",
    "toprol": "metoprolol",
    "coumadin": "warfarin",
    "plavix": "clopidogrel",
    # Cholesterol
    "lipitor": "atorvastatin",
    "crestor": "rosuvastatin",
    "zocor": "simvastatin",
    # Diabetes
    "glucophage": "metformin",
    # Mental Health
    "prozac": "fluoxetine",
    "zoloft": "sertraline",
    "xanax": "alprazolam",
    "ativan": "lorazepam",
    # Antibiotics
    "z-pack": "azithromycin",
    "cipro": "ciprofloxacin",
    # Respiratory
    "proair": "albuterol",
    "ventolin": "albuterol",
}


# Mock drug-drug interaction database
# In production, this would come from DrugBank API or similar
MOCK_INTERACTIONS = {
    ("warfarin", "ibuprofen"): {
        "severity": "MAJOR",
        "description": "NSAIDs like ibuprofen can increase bleeding risk when combined with warfarin",
        "mechanism": "NSAIDs inhibit platelet function and may displace warfarin from protein binding",
        "management": "Monitor INR more frequently. Watch for signs of bleeding (bruising, blood in urine/stool). Consider alternative pain relief like acetaminophen.",
        "clinical_effects": "Increased risk of serious bleeding including gastrointestinal hemorrhage",
    },
    ("warfarin", "aspirin"): {
        "severity": "MAJOR",
        "description": "Aspirin combined with warfarin significantly increases bleeding risk",
        "mechanism": "Aspirin irreversibly inhibits platelet aggregation and may increase warfarin effect",
        "management": "Avoid combination unless specifically prescribed by cardiologist. Requires close INR monitoring and bleeding surveillance.",
        "clinical_effects": "Substantially increased risk of major bleeding events",
    },
    ("lisinopril", "ibuprofen"): {
        "severity": "MODERATE",
        "description": "NSAIDs can reduce the blood pressure-lowering effect of ACE inhibitors like lisinopril",
        "mechanism": "NSAIDs inhibit prostaglandin synthesis, reducing ACE inhibitor effectiveness",
        "management": "Monitor blood pressure regularly. Use lowest effective NSAID dose for shortest duration. Consider acetaminophen as alternative.",
        "clinical_effects": "Decreased antihypertensive effect, possible increase in blood pressure",
    },
    ("metformin", "alcohol"): {
        "severity": "MODERATE",
        "description": "Alcohol consumption with metformin can increase risk of lactic acidosis",
        "mechanism": "Both metformin and alcohol can cause lactic acidosis, effects may be additive",
        "management": "Avoid excessive alcohol consumption. Limit to moderate intake (1-2 drinks maximum). Avoid binge drinking.",
        "clinical_effects": "Increased risk of lactic acidosis (rare but serious), altered glucose control",
    },
    ("atorvastatin", "azithromycin"): {
        "severity": "MODERATE",
        "description": "Azithromycin may increase atorvastatin levels, raising risk of muscle problems",
        "mechanism": "Azithromycin may inhibit metabolism of statins",
        "management": "Watch for muscle pain, weakness, or dark urine. Report symptoms immediately. Short-term use generally acceptable.",
        "clinical_effects": "Increased risk of myopathy and rhabdomyolysis",
    },
    ("fluoxetine", "ibuprofen"): {
        "severity": "MODERATE",
        "description": "SSRIs like fluoxetine combined with NSAIDs increase gastrointestinal bleeding risk",
        "mechanism": "Both drugs affect platelet function and gastric protection",
        "management": "Consider alternative pain relief. If NSAIDs needed, take with food and consider adding stomach protection (PPI).",
        "clinical_effects": "Increased risk of upper GI bleeding",
    },
    ("alprazolam", "alcohol"): {
        "severity": "MAJOR",
        "description": "Combining benzodiazepines like alprazolam with alcohol is dangerous and potentially deadly",
        "mechanism": "Both are CNS depressants with additive effects",
        "management": "Avoid alcohol completely while taking alprazolam. Risk of severe sedation, respiratory depression, and overdose.",
        "clinical_effects": "Severe sedation, confusion, respiratory depression, coma, death",
    },
    ("sertraline", "fluoxetine"): {
        "severity": "MAJOR",
        "description": "Combining two SSRIs increases risk of serotonin syndrome",
        "mechanism": "Excessive serotonin accumulation in the brain",
        "management": "Do not take together. Requires washout period when switching between SSRIs. Consult prescriber.",
        "clinical_effects": "Serotonin syndrome: agitation, confusion, rapid heart rate, high blood pressure, dilated pupils, muscle rigidity",
    },
    ("lisinopril", "albuterol"): {
        "severity": "MINOR",
        "description": "Albuterol may slightly increase heart rate and blood pressure",
        "mechanism": "Beta-2 agonist effects on cardiovascular system",
        "management": "Usually not clinically significant. Monitor blood pressure if using albuterol frequently.",
        "clinical_effects": "Mild temporary increase in heart rate and blood pressure",
    },
    ("metformin", "atorvastatin"): {
        "severity": "MINOR",
        "description": "Generally safe combination, commonly prescribed together",
        "mechanism": "No significant interaction mechanism",
        "management": "No special precautions needed. Both are commonly used in patients with diabetes and high cholesterol.",
        "clinical_effects": "No significant clinical interaction",
    },
}


def normalize_drug_names(med_list: List[str]) -> List[str]:
    """
    Normalize drug names from brand names to generic names.

    Args:
        med_list: List of medication names (brand or generic)

    Returns:
        List of normalized generic names
    """
    normalized = []

    for med in med_list:
        # Clean the input
        med_clean = med.lower().strip()

        # Remove common suffixes/notes in parentheses
        if "(" in med_clean:
            med_clean = med_clean.split("(")[0].strip()

        # Check if it's a brand name we know
        if med_clean in DRUG_NAME_MAPPING:
            normalized_name = DRUG_NAME_MAPPING[med_clean]
            logger.info(f"Normalized '{med}' → '{normalized_name}'")
            normalized.append(normalized_name)
        else:
            # Keep as-is if we don't have a mapping
            normalized.append(med_clean)

    return normalized


def check_drug_interactions(medications: List[str]) -> List[Dict]:
    """
    Check for drug-drug interactions in the medication list.

    Args:
        medications: List of medication names (should be normalized first)

    Returns:
        List of interaction dictionaries with fields:
        - drug_a: First drug name
        - drug_b: Second drug name
        - severity: MAJOR, MODERATE, or MINOR
        - description: Brief description
        - mechanism: How the interaction occurs
        - management: What to do about it
        - clinical_effects: What symptoms/effects may occur
    """
    logger.info(f"Checking interactions for {len(medications)} medications")

    if len(medications) < 2:
        logger.info("Less than 2 medications, no interactions possible")
        return []

    # Normalize all medication names
    normalized_meds = normalize_drug_names(medications)

    interactions = []

    # Check each pair of medications
    for i, med_a in enumerate(normalized_meds):
        for med_b in normalized_meds[i + 1 :]:
            # Check both orderings (A+B and B+A)
            interaction_key = (med_a, med_b)
            reverse_key = (med_b, med_a)

            if interaction_key in MOCK_INTERACTIONS:
                interaction = MOCK_INTERACTIONS[interaction_key].copy()
                interaction["drug_a"] = med_a
                interaction["drug_b"] = med_b
                interactions.append(interaction)
                logger.info(
                    f"Found interaction: {med_a} + {med_b} ({interaction['severity']})"
                )
            elif reverse_key in MOCK_INTERACTIONS:
                interaction = MOCK_INTERACTIONS[reverse_key].copy()
                interaction["drug_a"] = med_b
                interaction["drug_b"] = med_a
                interactions.append(interaction)
                logger.info(
                    f"Found interaction: {med_b} + {med_a} ({interaction['severity']})"
                )

    # Sort by severity (MAJOR first, then MODERATE, then MINOR)
    severity_order = {"MAJOR": 0, "MODERATE": 1, "MINOR": 2}
    interactions.sort(key=lambda x: severity_order.get(x["severity"], 3))

    logger.info(f"Found {len(interactions)} total interactions")
    return interactions


async def check_drug_interactions_via_api(drugbank_ids: List[str]) -> List[Dict]:
    """
    Check drug interactions via external API (DrugBank or similar).

    This is a placeholder for future API integration.
    Currently redirects to mock data function.

    Args:
        drugbank_ids: List of DrugBank IDs or drug names

    Returns:
        List of interaction dictionaries
    """
    # TODO: Implement DrugBank API integration
    # import httpx
    # from app.config.settings import settings
    #
    # ids = ",".join(drugbank_ids)
    # url = f"https://api.drugbank.com/v1/ddi?drugbank_id={ids}"
    # headers = {"Authorization": f"Bearer {settings.DRUGBANK_API_KEY}"}
    #
    # async with httpx.AsyncClient() as client:
    #     resp = await client.get(url, headers=headers)
    #     resp.raise_for_status()
    #     return resp.json()

    # For now, use mock data
    return check_drug_interactions(drugbank_ids)


def format_interaction_for_display(interactions: List[Dict]) -> str:
    """
    Format drug interactions for user-friendly display.

    Args:
        interactions: List of interaction dictionaries

    Returns:
        Formatted string for display
    """
    if not interactions:
        return "✅ No known drug interactions detected in the provided medications."

    # Group by severity
    major = [i for i in interactions if i["severity"] == "MAJOR"]
    moderate = [i for i in interactions if i["severity"] == "MODERATE"]
    minor = [i for i in interactions if i["severity"] == "MINOR"]

    output = ["**💊 Drug Interaction Analysis**\n"]

    if major:
        output.append(f"**⚠️ MAJOR Interactions ({len(major)}):**")
        for interaction in major:
            output.append(
                f"- **{interaction['drug_a'].title()} + {interaction['drug_b'].title()}**\n"
                f"  {interaction['description']}\n"
                f"  ⚠️ Action: {interaction['management']}"
            )
        output.append("")

    if moderate:
        output.append(f"**⚡ MODERATE Interactions ({len(moderate)}):**")
        for interaction in moderate:
            output.append(
                f"- **{interaction['drug_a'].title()} + {interaction['drug_b'].title()}**\n"
                f"  {interaction['description']}\n"
                f"  ℹ️ Action: {interaction['management']}"
            )
        output.append("")

    if minor:
        output.append(f"**ℹ️ Minor Interactions ({len(minor)}):**")
        minor_pairs = [f"{i['drug_a'].title()} + {i['drug_b'].title()}" for i in minor]
        output.append(f"  {', '.join(minor_pairs)}")
        output.append("  (Generally not clinically significant)")
        output.append("")

    return "\n".join(output)
