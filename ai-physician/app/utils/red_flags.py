"""Red flag detection for emergency symptoms."""

import re
from typing import List, Tuple


# Emergency symptom patterns by category
RED_FLAG_PATTERNS = {
    "cardiac_emergency": [
        r"chest pain",
        r"crushing.*chest",
        r"pressure.*chest",
        r"chest.*tight",
        r"pain.*radiating.*(arm|jaw|shoulder|back)",
        r"pain.*(arm|jaw).*chest",
    ],
    "respiratory_emergency": [
        r"can'?t breathe",
        r"can'?t catch.*breath",
        r"difficulty breathing",
        r"shortness of breath.*rest",
        r"gasping for air",
        r"choking",
        r"lips.*blue",
        r"turning blue",
    ],
    "neurological_emergency": [
        r"worst headache.*life",
        r"thunderclap headache",
        r"sudden.*severe.*headache",
        r"loss of consciousness",
        r"passed out",
        r"blacked out",
        r"face.*droop",
        r"facial.*droop",
        r"arm.*weak",
        r"leg.*weak",
        r"slurred speech",
        r"can'?t speak properly",
        r"confused",
        r"disoriented",
        r"seizure",
    ],
    "psychiatric_emergency": [
        r"want to (die|kill myself)",
        r"suicidal",
        r"plan to.*harm",
        r"going to end it",
        r"thoughts of (suicide|killing myself)",
        r"better off dead",
    ],
    "trauma_emergency": [
        r"heavy bleeding",
        r"profuse bleeding",
        r"bleeding.*won'?t stop",
        r"severe.*injury",
        r"can'?t move.*(limb|arm|leg)",
        r"broken bone.*protruding",
        r"compound fracture",
    ],
    "abdominal_emergency": [
        r"severe.*abdominal pain",
        r"abdomen.*rigid",
        r"stomach.*rigid",
        r"severe.*stomach pain",
        r"vomiting blood",
        r"blood in.*vomit",
        r"blood in.*stool",
        r"black.*tarry.*stool",
    ],
    "allergic_emergency": [
        r"severe allergic reaction",
        r"anaphylaxis",
        r"face.*swelling",
        r"tongue.*swelling",
        r"throat.*closing",
        r"hives.*difficulty breathing",
    ],
}


def detect_red_flags(text: str) -> Tuple[bool, List[str]]:
    """
    Detect emergency red flags in user input.

    Args:
        text: User message text

    Returns:
        Tuple of (has_red_flags, list_of_detected_categories)
    """
    text_lower = text.lower()
    detected_flags = []

    for category, patterns in RED_FLAG_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                detected_flags.append(category)
                break  # Only add category once

    return len(detected_flags) > 0, detected_flags


def get_red_flag_description(category: str) -> str:
    """Get human-readable description of red flag category."""
    descriptions = {
        "cardiac_emergency": "Possible heart-related emergency (chest pain, pressure)",
        "respiratory_emergency": "Severe breathing difficulty",
        "neurological_emergency": "Possible stroke or severe neurological event",
        "psychiatric_emergency": "Mental health crisis requiring immediate attention",
        "trauma_emergency": "Severe injury or uncontrolled bleeding",
        "abdominal_emergency": "Severe abdominal emergency",
        "allergic_emergency": "Severe allergic reaction",
    }
    return descriptions.get(category, category)
