"""Preventive Care & Chronic Disease Management Agent."""

from typing import Dict, List, Optional
from app.config.llm_config import get_preventive_model
from app.agents.prompts import PREVENTIVE_CHRONIC_PROMPT
from langchain_core.messages import SystemMessage, HumanMessage
import json
import logging

logger = logging.getLogger(__name__)


async def analyze_preventive_care(
    age: Optional[int],
    sex: Optional[str],
    chronic_conditions: List[str],
    recent_labs: List[dict],
    current_medications: List[str],
    history_summary: Optional[str] = None,
    risk_level: Optional[str] = None,
) -> Dict:
    """
    Generate preventive care recommendations and chronic disease care plans.

    Args:
        age: Patient age
        sex: Patient sex (male/female/other)
        chronic_conditions: List of chronic conditions
        recent_labs: Recent lab results and vitals
        current_medications: Current medications
        history_summary: Medical history summary from history agent
        risk_level: Current risk level (LOW/MODERATE/HIGH)

    Returns:
        Dict with:
            - preventive_recommendations: List of preventive care items
            - chronic_care_plans: List of chronic disease care plans
            - summary: Brief summary text
    """
    logger.info("Starting preventive care and chronic disease analysis")

    # Default values if missing
    age_str = str(age) if age is not None else "Unknown"
    sex_str = sex or "Unknown"
    risk_level = risk_level or "UNKNOWN"
    history_summary = history_summary or "No medical history available"

    # Format chronic conditions
    if chronic_conditions:
        conditions_text = "\n".join(
            [f"- {condition}" for condition in chronic_conditions]
        )
    else:
        conditions_text = "No chronic conditions documented"

    # Format recent labs
    if recent_labs:
        labs_text = "\n".join(
            [
                f"- {lab.get('name', 'Unknown test')}: {lab.get('value', 'N/A')} "
                f"({lab.get('date', 'Unknown date')}) {'[ABNORMAL]' if lab.get('is_abnormal') else ''}"
                for lab in recent_labs
            ]
        )
    else:
        labs_text = "No recent labs available"

    # Format medications
    if current_medications:
        meds_text = "\n".join([f"- {med}" for med in current_medications])
    else:
        meds_text = "No current medications documented"

    # Create prompt
    prompt = PREVENTIVE_CHRONIC_PROMPT.format(
        age=age_str,
        sex=sex_str,
        chronic_conditions=conditions_text,
        recent_labs=labs_text,
        current_medications=meds_text,
        history_summary=history_summary,
        risk_level=risk_level,
    )

    response_text = ""  # Initialize for error handling

    try:
        # Llama-4-Scout-17B - Preventive/Chronic: guideline reasoning, care plans
        llm = get_preventive_model()

        # System message for JSON output
        system_msg = SystemMessage(
            content="You are a medical assistant. Respond ONLY with valid JSON, no additional text."
        )
        human_msg = HumanMessage(content=prompt)

        # Get response
        response = await llm.ainvoke([system_msg, human_msg])
        response_text = str(response.content) if response.content else ""

        # Try to parse JSON
        # Remove markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        result = json.loads(response_text)

        # Validate structure
        if "preventive_recommendations" not in result:
            result["preventive_recommendations"] = []
        if "chronic_care_plans" not in result:
            result["chronic_care_plans"] = []
        if "summary" not in result:
            result["summary"] = "Preventive care recommendations generated."

        logger.info(
            f"Generated {len(result['preventive_recommendations'])} preventive recommendations "
            f"and {len(result['chronic_care_plans'])} chronic care plans"
        )

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        if response_text:
            logger.error(f"Response text: {response_text[:500]}")
        return {
            "preventive_recommendations": [],
            "chronic_care_plans": [],
            "summary": "Unable to generate preventive care recommendations at this time.",
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Error in preventive care analysis: {e}", exc_info=True)
        return {
            "preventive_recommendations": [],
            "chronic_care_plans": [],
            "summary": "Error generating preventive care recommendations.",
            "error": str(e),
        }


def format_preventive_recommendations(recommendations: List[dict]) -> str:
    """
    Format preventive recommendations for display.

    Args:
        recommendations: List of preventive recommendation dicts

    Returns:
        Formatted string for display
    """
    if not recommendations:
        return "No specific preventive care recommendations at this time."

    # Group by status
    due_now = [r for r in recommendations if r.get("status") == "DUE_NOW"]
    due_soon = [r for r in recommendations if r.get("status") == "DUE_SOON"]

    output = ["**📋 Preventive Care Recommendations:**\n"]

    if due_now:
        output.append("**Due Now:**")
        for rec in due_now:
            output.append(
                f"- **{rec.get('name')}** ({rec.get('category', 'screening')})\n"
                f"  {rec.get('reason', '')} - {rec.get('urgency_note', 'Schedule soon')}"
            )
        output.append("")

    if due_soon:
        output.append("**Due Soon:**")
        for rec in due_soon:
            output.append(
                f"- **{rec.get('name')}** ({rec.get('category', 'screening')})\n"
                f"  {rec.get('reason', '')} - {rec.get('urgency_note', '')}"
            )
        output.append("")

    return "\n".join(output)


def format_chronic_care_plans(care_plans: List[dict]) -> str:
    """
    Format chronic care plans for display.

    Args:
        care_plans: List of chronic care plan dicts

    Returns:
        Formatted string for display
    """
    if not care_plans:
        return ""

    output = ["**🏥 Chronic Disease Management Plans:**\n"]

    for plan in care_plans:
        condition = plan.get("condition", "Unknown condition")
        risk = plan.get("risk_level", "UNKNOWN")

        output.append(f"**{condition}** (Risk: {risk})")

        if plan.get("targets"):
            output.append("  **Goals:**")
            for target in plan["targets"]:
                output.append(f"  - {target}")

        if plan.get("monitoring"):
            output.append("  **Monitoring:**")
            for item in plan["monitoring"]:
                output.append(f"  - {item}")

        if plan.get("lifestyle"):
            output.append("  **Lifestyle:**")
            for item in plan["lifestyle"]:
                output.append(f"  - {item}")

        if plan.get("doctor_followup_topics"):
            output.append("  **Discuss with your doctor:**")
            for topic in plan["doctor_followup_topics"]:
                output.append(f"  - {topic}")

        output.append("")  # Blank line between conditions

    return "\n".join(output)
