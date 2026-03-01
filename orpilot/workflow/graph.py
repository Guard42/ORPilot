"""Main LangGraph graph definition for the ORPilot workflow."""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from orpilot.llm.base import BaseLLM
from orpilot.llm.config import LLMConfig, get_llm
from orpilot.workflow.state import WorkflowState
from orpilot.workflow.nodes.interview import interview_node
from orpilot.workflow.nodes.data_collection import data_collection_node
from orpilot.workflow.nodes.param_computation import param_computation_node
from orpilot.workflow.nodes.direct_code_gen import direct_code_gen_node
from orpilot.workflow.nodes.ir_builder import ir_builder_on_demand_node
from orpilot.workflow.nodes.solver_runner import solver_runner_node
from orpilot.workflow.nodes.reporter import reporter_node
from orpilot.workflow import edges


def build_graph(
    llm: BaseLLM | None = None,
    llm_config: LLMConfig | None = None,
) -> StateGraph:
    """Build the ORPilot workflow graph.

    Default path: interview → data_collection → param_computation →
                  direct_code_gen → solver_runner → reporter

    Optional on-demand IR (when generate_ir=True in state):
                  solver_runner → ir_builder_on_demand → reporter

    Args:
        llm: Pre-configured LLM instance. If None, created from llm_config.
        llm_config: LLM configuration. Used only if llm is None.

    Returns:
        A compiled LangGraph StateGraph ready for execution.
    """
    if llm is None:
        llm = get_llm(llm_config)

    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("interview", lambda state: interview_node(state, llm))
    graph.add_node("data_collection", lambda state: data_collection_node(state, llm))
    graph.add_node("param_computation", lambda state: param_computation_node(state, llm))
    graph.add_node("direct_code_gen", lambda state: direct_code_gen_node(state, llm))
    graph.add_node("solver_runner", lambda state: solver_runner_node(state))
    graph.add_node("ir_builder_on_demand", lambda state: ir_builder_on_demand_node(state, llm))
    graph.add_node("reporter", lambda state: reporter_node(state, llm))

    # A no-op node that signals "waiting for user input"
    graph.add_node("wait_for_input", lambda state: {**state, "needs_user_input": True})

    # Set entry point
    graph.set_entry_point("interview")

    # Edges
    graph.add_conditional_edges("interview", edges.after_interview)
    graph.add_conditional_edges("data_collection", edges.after_data_collection)

    # param_computation → direct_code_gen (always)
    graph.add_edge("param_computation", "direct_code_gen")

    # direct_code_gen → solver_runner (or reporter on hard failure)
    graph.add_conditional_edges("direct_code_gen", edges.after_direct_code_gen)

    # solver_runner → reporter | ir_builder_on_demand | direct_code_gen (retry)
    graph.add_conditional_edges("solver_runner", edges.after_solver_runner)

    # ir_builder_on_demand → reporter (always, IR is optional — never blocks)
    graph.add_edge("ir_builder_on_demand", "reporter")

    # Terminal nodes
    graph.add_edge("reporter", END)
    graph.add_edge("wait_for_input", END)

    return graph.compile()
