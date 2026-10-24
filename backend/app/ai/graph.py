"""LangGraph StateGraph: a real branching workflow, not a straight line.

Conditional edges:
  * validate_extraction failure -> retry intake_extraction (max 2 retries),
    then route to the error end-state;
  * final_validation failure    -> retry capa_generation (max 2 retries),
    then route to the error end-state.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.ai import nodes
from app.ai.state import RCAState

MAX_RETRIES = 2  # "retry the previous node (max 2), then route to an error end-state"


def route_after_extraction(state: RCAState) -> str:
    if not state.get("validation_error"):
        return "continue"
    if state.get("retries", {}).get("intake_extraction", 0) <= MAX_RETRIES:
        return "retry_intake"
    return "error"


def route_after_final(state: RCAState) -> str:
    if not state.get("final_validation_error"):
        return "end"
    if state.get("retries", {}).get("capa_generation", 0) <= MAX_RETRIES:
        return "retry_capa"
    return "error"


def build_graph():
    graph = StateGraph(RCAState)

    graph.add_node("intake_extraction", nodes.intake_extraction)
    graph.add_node("validate_extraction", nodes.validate_extraction)
    graph.add_node("five_whys", nodes.five_whys)
    graph.add_node("fishbone", nodes.fishbone)
    graph.add_node("root_cause_synthesis", nodes.root_cause_synthesis)
    graph.add_node("evidence_gap_check", nodes.evidence_gap_check)
    graph.add_node("capa_generation", nodes.capa_generation)
    graph.add_node("final_validation", nodes.final_validation)
    graph.add_node("error_end", nodes.error_end)

    graph.add_edge(START, "intake_extraction")
    graph.add_edge("intake_extraction", "validate_extraction")
    graph.add_conditional_edges(
        "validate_extraction",
        route_after_extraction,
        {
            "continue": "five_whys",
            "retry_intake": "intake_extraction",
            "error": "error_end",
        },
    )

    graph.add_edge("five_whys", "fishbone")
    graph.add_edge("fishbone", "root_cause_synthesis")
    graph.add_edge("root_cause_synthesis", "evidence_gap_check")
    graph.add_edge("evidence_gap_check", "capa_generation")
    graph.add_edge("capa_generation", "final_validation")
    graph.add_conditional_edges(
        "final_validation",
        route_after_final,
        {
            "end": END,
            "retry_capa": "capa_generation",
            "error": "error_end",
        },
    )
    graph.add_edge("error_end", END)

    return graph.compile()


# Compiled graph used by the SSE endpoint.
graph = build_graph()
