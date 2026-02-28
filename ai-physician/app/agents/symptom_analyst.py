"""Vaidya-Orchestrated Multi-Agent Workflow.

This module defines the LangGraph workflow with Vaidya as the central supervisor
that intelligently routes to specialist agents.
"""

from langgraph.graph import StateGraph, END
from app.agents.state import SymptomCheckState
from app.agents.nodes import (
    greeting_node,
    analyze_input_node,
    red_flag_check_node,
    emergency_node,
    gather_info_node,
    history_node,
    assessment_node,
    triage_node,
    preventive_chronic_node,
    drug_interaction_node,
    recommendation_node,
    save_assessment_node,
    final_responder_node,
    summarization_node,
)
from app.agents.vaidya_supervisor import (
    vaidya_supervisor_node,
    vaidya_questioner_node,
    route_to_next_agent,
)
from app.agents.provider_agent import provider_locator_node
from app.agents.er_emergency_agent import er_emergency_node
import logging

logger = logging.getLogger(__name__)


def check_red_flags(state: SymptomCheckState) -> str:
    """Route based on red flag detection."""
    if state.get("red_flags_detected"):
        return "emergency"
    return "gather_info"


def check_golden_4_complete(state: SymptomCheckState) -> str:
    """Route based on Golden 4 completion status."""
    if state.get("golden_4_complete", False):
        return "complete"
    return "wait_for_user"


def route_after_symptom_analyst(state: SymptomCheckState) -> str:
    """Route after symptom analyst completes."""
    # If emergency, go straight to final responder
    if state.get("classification") == "ER_NOW":
        return "final_responder"

    # If Golden 4 not complete, wait for more user input
    if not state.get("golden_4_complete", False):
        return "end"

    # Otherwise return to Vaidya for next decision
    return "vaidya"


def build_vaidya_graph():
    """
    Build and compile the Vaidya-orchestrated multi-agent workflow.

    Flow:
    1. Entry → greeting → summarization (checks if needed) → vaidya_supervisor
    2. Vaidya analyzes intent and routes to:
       - symptom_analyst (for symptom checks)
       - history (for medical history)
       - preventive_chronic (for preventive care)
       - drug_interaction (for medication safety)
       - provider_locator (for finding doctors/hospitals)
       - vaidya_questioner (for clarifying questions)
       - final_responder (to synthesize and conclude)
    3. After each specialist agent, loop back to Vaidya for next decision
    4. Summarization auto-triggers at 20+ messages to keep context manageable
    5. Vaidya decides when workflow is complete
    """
    logger.info("Building Vaidya-orchestrated LangGraph workflow")

    workflow = StateGraph(SymptomCheckState)

    # Add all nodes
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("summarization", summarization_node)  # Context management
    workflow.add_node("vaidya", vaidya_supervisor_node)
    workflow.add_node("vaidya_questioner", vaidya_questioner_node)

    # Symptom analyst sub-workflow
    workflow.add_node("analyze_input", analyze_input_node)
    workflow.add_node("red_flag_check", red_flag_check_node)
    workflow.add_node("emergency", emergency_node)
    workflow.add_node("gather_info", gather_info_node)
    workflow.add_node("assess", assessment_node)
    workflow.add_node("triage", triage_node)

    # Specialist agents
    workflow.add_node("history", history_node)
    workflow.add_node("preventive_chronic", preventive_chronic_node)
    workflow.add_node("drug_interaction", drug_interaction_node)
    workflow.add_node("provider_locator", provider_locator_node)
    workflow.add_node("er_emergency", er_emergency_node)  # ER hospital search

    # Final nodes
    workflow.add_node("final_responder", final_responder_node)
    workflow.add_node("save_assessment", save_assessment_node)

    # Set entry point
    workflow.set_entry_point("greeting")

    # Greeting → Summarization (to check context)
    workflow.add_edge("greeting", "summarization")

    # Summarization → Vaidya (always, even if no summary needed)
    workflow.add_edge("summarization", "vaidya")

    # Vaidya routes to specialist agents via conditional
    workflow.add_conditional_edges(
        "vaidya",
        route_to_next_agent,
        {
            "symptom_analyst": "analyze_input",
            "history": "history",
            "preventive_chronic": "preventive_chronic",
            "drug_interaction": "drug_interaction",
            "provider_locator": "provider_locator",
            "er_emergency": "er_emergency",
            "vaidya_questioner": "vaidya_questioner",
            "final_responder": "final_responder",
            "end": END,
        },
    )

    # === Symptom Analyst Sub-workflow ===
    # analyze_input → red_flag_check
    workflow.add_edge("analyze_input", "red_flag_check")

    # red_flag_check → emergency OR gather_info
    workflow.add_conditional_edges(
        "red_flag_check",
        check_red_flags,
        {"emergency": "emergency", "gather_info": "gather_info"},
    )

    # emergency → er_emergency → final_responder (ER hospital search + synthesis)
    workflow.add_edge("emergency", "er_emergency")
    workflow.add_edge("er_emergency", "final_responder")

    # gather_info checks if Golden 4 is complete
    workflow.add_conditional_edges(
        "gather_info",
        check_golden_4_complete,
        {
            "complete": "assess",  # Golden 4 complete → assessment
            "wait_for_user": END,  # Not complete → wait for more input
        },
    )

    # After gathering complete: assess → triage → back to summarization → Vaidya
    workflow.add_edge("assess", "triage")
    workflow.add_edge("triage", "summarization")

    # === Specialist Agents return to Summarization (which checks context, then → Vaidya) ===
    workflow.add_edge("history", "summarization")
    workflow.add_edge("preventive_chronic", "summarization")
    workflow.add_edge("drug_interaction", "summarization")
    workflow.add_edge("provider_locator", "summarization")

    # === Vaidya Questioner waits for user response ===
    workflow.add_edge("vaidya_questioner", END)

    # === Final Responder saves and ends ===
    workflow.add_edge("final_responder", "save_assessment")
    workflow.add_edge("save_assessment", END)

    # Compile the graph
    graph = workflow.compile()
    logger.info("Vaidya-orchestrated workflow compiled successfully")

    return graph


# Global graph instance
_vaidya_graph = None


def get_vaidya_graph():
    """
    Get or create the Vaidya-orchestrated multi-agent graph instance.

    Vaidya acts as the root supervisor agent that intelligently routes to specialist agents:
    - Symptom Analyst (symptom checking)
    - History Agent (medical history)
    - Preventive & Chronic Care Agent (preventive care)
    - Drug Interaction Agent (medication safety)
    - Provider Locator Agent (finding healthcare providers)
    """
    global _vaidya_graph
    if _vaidya_graph is None:
        _vaidya_graph = build_vaidya_graph()
    return _vaidya_graph
