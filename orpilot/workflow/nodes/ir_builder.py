"""IR builder node — translate ProblemDefinition JSON into a strict JSON IR via LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path

from orpilot.llm.base import BaseLLM
from orpilot.models.ir import IRModel
from orpilot.prompts import ir_builder as ir_builder_prompts
from orpilot.workflow.state import WorkflowState


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    pattern = r"```(?:json)?\s*\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def ir_builder_node(state: WorkflowState, llm: BaseLLM) -> WorkflowState:
    """Call the LLM to translate the ProblemDefinition into a JSON IR.

    Retries up to 2 times on parse/validation failure.
    On UNSUPPORTED_MODEL error: short-circuits to reporter with a user message.
    """
    problem = state["problem"]
    user_data = state.get("user_data")

    # Build csv_schemas: table_stem → [col1, col2, ...] so the LLM knows
    # exact column names and can fill "column" fields without guessing.
    csv_schemas: dict[str, list[str]] = {}
    if user_data and user_data.csv_specs:
        for spec in user_data.csv_specs:
            stem = Path(spec.filename).stem
            csv_schemas[stem] = [c.name for c in spec.columns]

    user_payload: dict = {"problem": json.loads(problem.model_dump_json())}
    if csv_schemas:
        user_payload["csv_schemas"] = csv_schemas

    error_context = state.get("error_context")
    existing_ir = state.get("ir_model")
    generated_code = state.get("generated_code", "")

    if error_context and existing_ir:
        # Retry after downstream failure: show the LLM the IR it produced, the Python
        # code that was compiled from it, and the error — so it can trace the bug back
        # to the IR rather than guessing from the error message alone.
        code_block = f"```python\n{generated_code}\n```\n\n" if generated_code else ""
        messages = [
            {"role": "system", "content": ir_builder_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
            {"role": "assistant", "content": json.dumps(existing_ir)},
            {
                "role": "user",
                "content": (
                    f"The IR you produced was compiled to this Python solver code:\n\n"
                    f"{code_block}"
                    f"Running that code produced this error:\n\n"
                    f"{error_context}\n\n"
                    "Identify the root cause in your IR and return a corrected JSON IR. "
                    "Output JSON only."
                ),
            },
        ]
    elif error_context:
        # param_computation failed — inform the LLM so it knows computed CSVs may be missing
        messages = [
            {"role": "system", "content": ir_builder_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    json.dumps(user_payload) + "\n\n"
                    f"Warning: parameter computation failed and some derived CSVs "
                    f"may not be available:\n{error_context}\n\n"
                    "If a required CSV is missing from csv_file_paths, set source to null "
                    "and the model will need to be corrected once the data issue is resolved."
                ),
            },
        ]
    else:
        messages = [
            {"role": "system", "content": ir_builder_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
        ]

    for attempt in range(3):  # initial attempt + up to 2 retries
        response = llm.chat(messages)
        try:
            ir_dict = json.loads(_strip_fences(response))
            if ir_dict.get("error") == "UNSUPPORTED_MODEL":
                return {
                    **state,
                    "report": (
                        "This problem cannot be represented as a linear or mixed-integer "
                        "program. Please reformulate your problem and try again."
                    ),
                    "current_node": "reporter",
                }
            IRModel.model_validate(ir_dict)
            return {**state, "ir_model": ir_dict, "error_context": "", "current_node": "ir_builder"}
        except Exception as exc:
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Validation failed: {exc}. Return corrected JSON only.",
            })

    return {
        **state,
        "report": (
            "The model could not be built after 3 attempts. "
            "Please refine your problem description or data and try again."
        ),
        "current_node": "reporter",
    }


def ir_builder_on_demand_node(state: WorkflowState, llm: BaseLLM) -> WorkflowState:
    """Generate IR on-demand from the problem description + working Python code.

    Called after a successful solve to produce a solver-agnostic IR blueprint that
    can be compiled to a different solver without another LLM call.
    The generated Python code is included so the LLM uses it as a structural
    reference rather than re-interpreting the problem description from scratch.
    On failure the node simply skips IR (the solve was already successful).
    """
    problem = state["problem"]
    user_data = state.get("user_data")
    generated_code = state.get("generated_code", "")

    csv_schemas: dict[str, list[str]] = {}
    if user_data and user_data.csv_specs:
        for spec in user_data.csv_specs:
            stem = Path(spec.filename).stem
            csv_schemas[stem] = [c.name for c in spec.columns]

    user_payload: dict = {"problem": json.loads(problem.model_dump_json())}
    if csv_schemas:
        user_payload["csv_schemas"] = csv_schemas

    code_block = f"```python\n{generated_code}\n```" if generated_code else ""
    messages = [
        {"role": "system", "content": ir_builder_prompts.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                json.dumps(user_payload) + "\n\n"
                "The following Python solver code already solves this problem correctly. "
                "Use it as a structural reference (sets, variables, parameters, constraints, "
                "objective direction) to generate the IR. The IR must be solver-agnostic — "
                "extract the abstract model structure, do not transliterate solver-specific "
                "syntax (e.g. PuLP's lpSum or LpVariable).\n\n"
                f"{code_block}\n\n"
                "Return JSON IR only."
            ),
        },
    ]

    for attempt in range(3):
        response = llm.chat(messages)
        try:
            ir_dict = json.loads(_strip_fences(response))
            if ir_dict.get("error") == "UNSUPPORTED_MODEL":
                # Solve already succeeded — IR is optional, just skip
                return {**state, "current_node": "ir_builder_on_demand"}
            IRModel.model_validate(ir_dict)
            return {**state, "ir_model": ir_dict, "current_node": "ir_builder_on_demand"}
        except Exception as exc:
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Validation failed: {exc}. Return corrected JSON only.",
            })

    # IR generation failed — not a blocker, solve already succeeded
    return {**state, "current_node": "ir_builder_on_demand"}
