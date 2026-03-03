"""Vaidya Multi-Agent Orchestrated Workflow.

This module defines the final LangGraph workflow with:
1. ReAct Supervisor as the central decision maker.
2. Modular sub-agents (Symptom, History, Drugs, etc.).
3. Shared state management via VaidyaState.
"""

import logging
from functools import lru_cache
from langgraph.graph import StateGraph, END

from app.agents.common.state import VaidyaState
from app.agents.supervisor.supervisor import supervisor_node
from app.agents.common.nodes import (
    final_responder_node,
    summarization_node,
    save_assessment_node,
    vaidya_questioner_node
)
from app.agents.sub_agents.symptom_analyst.nodes import (
    analyze_input_node,
    red_flag_check_node,
    emergency_node,
    gather_info_node,
    assessment_node,
    triage_node
)
from app.agents.sub_agents.history.nodes import history_node
from app.agents.sub_agents.preventive_chronic.nodes import preventive_chronic_node
from app.agents.sub_agents.drug.nodes import drug_interaction_node
from app.agents.sub_agents.provider.nodes import provider_locator_node
from app.agents.sub_agents.er_emergency.nodes import er_emergency_node

logger = logging.getLogger(__name__)

def route_to_next_agent(state: VaidyaState) -> str:
    """Router based on supervisor's decision."""
    next_agent = state.get("next_agent")
    if not next_agent:
        return "end"
        
    # Map supervisor decision to graph node names
    mapping = {
        "Symptom_Analyst": "symptom_workflow",
        "History_Agent": "history",
        "Preventive_Chronic_Agent": "preventive_chronic",
        "Drug_Interaction_Agent": "drug_interaction",
        "Provider_Locator_Agent": "provider_locator",
        "Vaidya_Questioner": "vaidya_questioner",
        "Final_Responder": "final_responder"
    }
    return mapping.get(next_agent, "final_responder")

def route_after_analysis(state: VaidyaState) -> str:
    if state.get("red_flags_detected"):
        return "emergency"
    if state.get("golden_4_complete"):
        return "assessment"
    return "vaidya_questioner"

def route_after_triage(state: VaidyaState) -> str:
    if state.get("emergency_mode"):
        return "er_emergency"
    return "save_assessment"

def build_vaidya_graph():
    """Build the unified multi-agent graph."""
    workflow = StateGraph(VaidyaState)

    # Core Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("summarization", summarization_node)
    
    # Specialist Nodes (Symptom Analyst workflow)
    workflow.add_node("symptom_analysis", analyze_input_node)
    workflow.add_node("red_flag_check", red_flag_check_node)
    workflow.add_node("emergency", emergency_node)
    workflow.add_node("gather_info", gather_info_node)
    workflow.add_node("assessment", assessment_node)
    workflow.add_node("triage", triage_node)
    
    # Other Specialist Nodes
    workflow.add_node("history", history_node)
    workflow.add_node("preventive_chronic", preventive_chronic_node)
    workflow.add_node("drug_interaction", drug_interaction_node)
    workflow.add_node("provider_locator", provider_locator_node)
    workflow.add_node("er_emergency", er_emergency_node)
    
    # Final Nodes
    workflow.add_node("vaidya_questioner", vaidya_questioner_node)
    workflow.add_node("final_responder", final_responder_node)
    workflow.add_node("save_assessment", save_assessment_node)

    # Entry Logic
    workflow.set_entry_point("supervisor")
    
    # Supervisor Routing
    workflow.add_conditional_edges(
        "supervisor",
        route_to_next_agent,
        {
            "symptom_workflow": "symptom_analysis",
            "history": "history",
            "preventive_chronic": "preventive_chronic",
            "drug_interaction": "drug_interaction",
            "provider_locator": "provider_locator",
            "vaidya_questioner": "vaidya_questioner",
            "final_responder": "final_responder",
            "end": END
        }
    )

    # Symptom Analyst execution path
    workflow.add_edge("symptom_analysis", "gather_info")
    workflow.add_edge("gather_info", "red_flag_check")
    
    workflow.add_conditional_edges(
        "red_flag_check",
        route_after_analysis,
        {
            "emergency": "emergency",
            "assessment": "assessment",
            "vaidya_questioner": "vaidya_questioner"
        }
    )
    
    # Emergency routing
    workflow.add_edge("emergency", "er_emergency")
    
    # Triage routing
    workflow.add_edge("assessment", "triage")
    workflow.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "er_emergency": "er_emergency",
            "save_assessment": "save_assessment"
        }
    )

    # Other Specialist Loops
    workflow.add_edge("history", "summarization")
    workflow.add_edge("preventive_chronic", "summarization")
    workflow.add_edge("drug_interaction", "summarization")
    workflow.add_edge("provider_locator", "summarization")
    
    workflow.add_edge("er_emergency", "final_responder")
    workflow.add_edge("summarization", "supervisor")
    
    # Questioner and Final Responder
    workflow.add_edge("vaidya_questioner", END)
    workflow.add_edge("save_assessment", "final_responder")
    workflow.add_edge("final_responder", END)

    return workflow.compile()

@lru_cache(maxsize=1)
def get_vaidya_graph():
    return build_vaidya_graph()
