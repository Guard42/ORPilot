"""Reporter node — translate solution into a natural language report."""

from __future__ import annotations

import json

from orpilot.llm.base import BaseLLM
from orpilot.prompts import report as report_prompts
from orpilot.workflow.state import WorkflowState


def _build_csv_files_text(solution) -> str:
    """Describe each output CSV file's structure with a sample of its rows."""
    if not solution or not solution.variable_groups:
        return "(none)"

    sections: list[str] = []
    for group in solution.variable_groups:
        filename = f"solution_{group.group_name}.csv"
        labels = list(group.dimension_labels or [])
        columns = labels + ["value"]
        header = ", ".join(columns)

        # Collect up to 5 non-zero rows as illustrative examples
        sample_rows: list[str] = []
        _SEP = "\x1f"
        for var_name, value in sorted((group.variables or {}).items()):
            if value is not None and round(float(value), 6) != 0:
                if _SEP in var_name:
                    parts = var_name.split(_SEP, 1)
                    dims = parts[1].split(_SEP) if len(parts) > 1 else []
                else:
                    parts = var_name.split("_", len(labels))  # legacy fallback
                    dims = parts[len(parts) - len(labels):] if labels else []
                row = ", ".join(dims + [str(round(float(value), 4))])
                sample_rows.append(f"    {row}")
            if len(sample_rows) >= 5:
                break

        section = f"File: {filename}\n  Columns: {header}"
        if sample_rows:
            section += "\n  Sample rows (non-zero):\n" + "\n".join(sample_rows)
        sections.append(section)

    return "\n\n".join(sections)


def reporter_node(state: WorkflowState, llm: BaseLLM) -> WorkflowState:
    """Generate a natural-language report from the solution."""
    problem = state.get("problem")
    solution = state.get("solution")

    variables_text = json.dumps(solution.variables, indent=2) if solution else "{}"
    csv_files_text = _build_csv_files_text(solution)

    prompt = report_prompts.SYSTEM_PROMPT.format(
        problem_description=problem.description if problem else "Unknown",
        status=solution.status.value if solution else "unknown",
        objective_value=solution.objective_value if solution else "N/A",
        variables_text=variables_text,
        solver_output=solution.solver_output if solution else "",
        csv_files_text=csv_files_text,
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Generate the report."},
    ]

    report = llm.chat(messages)

    return {
        **state,
        "report": report,
        "current_node": "reporter",
        "needs_user_input": False,
    }
