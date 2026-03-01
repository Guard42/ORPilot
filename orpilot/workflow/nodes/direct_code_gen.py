"""Direct code generation node — LLM writes solver code directly (no IR)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from orpilot.llm.base import BaseLLM
from orpilot.prompts.direct_code_gen import build_system_prompt
from orpilot.workflow.state import WorkflowState


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    pattern = r"```(?:python)?\s*\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def direct_code_gen_node(state: WorkflowState, llm: BaseLLM) -> WorkflowState:
    """Call the LLM to write solver code directly from the problem description.

    On fresh call: sends problem + csv_schemas.
    On retry (error_context set): sends previous code + error and asks for a fix.
    Retries up to 2 times on parse failure before giving up.
    """
    problem = state["problem"]
    user_data = state.get("user_data")
    solver = state.get("solver_name", "pulp")

    # Build csv_schemas: table_stem → {columns: {col: dtype}, sample: first_row}
    # so the LLM knows exact column names, types, and representative values.
    csv_schemas: dict[str, dict] = {}
    if user_data and user_data.csv_specs:
        raw_tables = user_data.raw_tables or {}
        for spec in user_data.csv_specs:
            stem = Path(spec.filename).stem
            rows = raw_tables.get(stem, [])
            csv_schemas[stem] = {
                "columns": {c.name: c.dtype for c in spec.columns},
                "sample": rows[0] if rows else {},
            }

    # Strip csv_file_paths — the model must use `data`, not open files directly.
    problem_dict = json.loads(problem.model_dump_json())
    problem_dict.pop("csv_file_paths", None)

    user_payload: dict = {"problem": problem_dict}
    if csv_schemas:
        user_payload["csv_schemas"] = csv_schemas

    system_prompt = build_system_prompt(solver)
    error_context = state.get("error_context")
    existing_code = state.get("generated_code", "")

    if error_context and existing_code:
        # Retry after solver/execution failure: show the LLM the code it wrote and the error.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
            {"role": "assistant", "content": existing_code},
            {
                "role": "user",
                "content": (
                    f"The code failed with the following error:\n\n"
                    f"{error_context}\n\n"
                    "Fix the code. Return corrected Python only — no markdown fences."
                ),
            },
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ]

    for attempt in range(3):  # initial attempt + up to 2 parse retries
        response = llm.chat(messages)
        code = _strip_fences(response)
        # Basic sanity check: must define a solve function
        if "def solve(" in code:
            return {
                **state,
                "generated_code": code,
                "error_context": "",
                "current_node": "direct_code_gen",
            }
        # Response doesn't look like valid Python code — ask for a correction
        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": (
                "Your response did not contain a valid `solve` function. "
                "Return Python code only — no markdown fences, no explanation."
            ),
        })

    return {
        **state,
        "report": (
            "Could not generate solver code after 3 attempts. "
            "Please refine your problem description or data and try again."
        ),
        "current_node": "reporter",
    }
