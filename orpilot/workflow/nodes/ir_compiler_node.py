"""IR compiler node — deterministic IR → solver code."""

from __future__ import annotations

import traceback

from orpilot.codegen.ir_compiler import IRCompiler
from orpilot.llm.base import BaseLLM
from orpilot.workflow.state import WorkflowState


def ir_compiler_node(state: WorkflowState, llm: BaseLLM) -> WorkflowState:
    """Compile the IR dict to solver code.

    On success, clears error_context and sets generated_code.
    On failure, sets error_context with the exception detail and increments
    retry_count so the conditional edge can route back to ir_builder.
    """
    ir_model = state.get("ir_model")
    solver = state.get("solver_name", "pulp")

    try:
        code = IRCompiler().compile(ir_model, solver)
    except Exception:
        error_msg = (
            "IR compilation to solver code failed:\n"
            + traceback.format_exc()
        )
        retry_count = state.get("retry_count", 0) + 1
        return {
            **state,
            "error_context": error_msg,
            "retry_count": retry_count,
            "current_node": "ir_compiler",
        }

    return {
        **state,
        "generated_code": code,
        "error_context": "",
        "current_node": "ir_compiler",
    }
