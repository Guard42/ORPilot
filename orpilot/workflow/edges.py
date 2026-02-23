"""Conditional edge logic for routing between workflow nodes."""

from __future__ import annotations

from orpilot.models.solution import SolveStatus
from orpilot.workflow.state import WorkflowState


def after_interview(state: WorkflowState) -> str:
    """Route after interview node."""
    if state.get("problem") is not None:
        return "data_collection"
    # Still interviewing — need more user input
    return "wait_for_input"


def after_data_collection(state: WorkflowState) -> str:
    """Route after data collection node."""
    if state.get("user_data") is not None:
        return "param_computation"
    return "wait_for_input"


def after_ir_compiler(state: WorkflowState) -> str:
    """Route after IR compilation."""
    if not state.get("error_context"):
        return "solver_runner"

    # Compilation failed — check retry budget
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    if retry_count < max_retries:
        return "ir_builder"

    return "reporter"


def after_solver_runner(state: WorkflowState) -> str:
    """Route after solver execution."""
    solution = state.get("solution")
    if solution is None:
        return "ir_builder"

    if solution.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE):
        return "reporter"

    # Failed — check retry budget
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    if retry_count < max_retries:
        # Recompiling the same IR is pointless — go back to the LLM to fix the IR
        return "ir_builder"

    # Exhausted retries — report the failure
    return "reporter"
