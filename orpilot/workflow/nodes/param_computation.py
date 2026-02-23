"""Parameter computation node — derive model-ready parameters from raw user data."""

from __future__ import annotations

import csv
import itertools
import math
import re
import traceback
from pathlib import Path
from typing import Any

from orpilot.llm.base import BaseLLM
from orpilot.models.data import CsvColumnSpec, CsvFileSpec, UserData, _cast_value
from orpilot.paths import DATA_DIR
from orpilot.prompts import param_computation as prompts
from orpilot.workflow.state import WorkflowState


def param_computation_node(state: WorkflowState, llm: BaseLLM) -> WorkflowState:
    """Compute derived parameters from raw user data when needed.

    Sits between data_collection and ir_builder.  The LLM inspects the raw
    table schemas and the problem description to decide whether any
    transformation is required (e.g. pairwise distances from coordinates).
    If so, it generates a Python script that writes the computed CSV(s) to
    data_dir, which are then merged into user_data so ir_builder sees them.
    """
    user_data: UserData | None = state.get("user_data")
    problem = state.get("problem")
    data_dir = state.get("data_dir", str(DATA_DIR))

    if user_data is None:
        return {**state, "current_node": "param_computation"}

    table_schemas = _describe_tables(user_data)
    problem_json = problem.model_dump_json(indent=2) if problem else "{}"

    prompt = prompts.SYSTEM_PROMPT.format(
        problem_json=problem_json,
        table_schemas=table_schemas,
    )

    messages: list[dict] = [{"role": "system", "content": prompt}]
    output_files: list[dict] = []
    for attempt in range(3):
        response = llm.chat(messages)

        if "[NO_COMPUTATION_NEEDED]" in response:
            return {**state, "current_node": "param_computation"}

        code = _strip_fences(response)
        output_files, error = _run_computation(code, user_data.as_dict(), data_dir)

        if not error and output_files:
            break

        # Script failed — ask the LLM to fix it
        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": (
                f"The script failed with this error:\n\n{error}\n\n"
                "Fix the Python script and output only the corrected code."
            ),
        })
    else:
        # All retries exhausted — surface the failure so ir_builder can report it
        return {
            **state,
            "error_context": (
                "Parameter computation failed after 3 attempts and no derived CSVs "
                "were produced. The IR may have parameters with no data source. "
                f"Last error:\n{error}"
            ),
            "current_node": "param_computation",
        }

    updated_user_data = _merge_computed_files(user_data, output_files, data_dir)

    updates: dict[str, Any] = {
        "user_data": updated_user_data,
        "current_node": "param_computation",
    }

    # Add computed file paths to problem.csv_file_paths so ir_builder can reference them
    if problem:
        new_paths = {
            Path(f["filename"]).stem: str((Path(data_dir) / f["filename"]).resolve())
            for f in output_files
        }
        merged_paths = {**(problem.csv_file_paths or {}), **new_paths}
        updates["problem"] = problem.model_copy(update={"csv_file_paths": merged_paths})

    return {**state, **updates}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _describe_tables(user_data: UserData) -> str:
    """Return a human-readable summary of available raw tables and their columns."""
    lines: list[str] = []

    # Prefer the richer spec information when available
    if user_data.csv_specs:
        for spec in user_data.csv_specs:
            stem = Path(spec.filename).stem
            cols = ", ".join(f"{c.name} ({c.dtype})" for c in spec.columns)
            lines.append(f"- {stem}: [{cols}]")
    else:
        for name, rows in user_data.raw_tables.items():
            if rows:
                cols = ", ".join(rows[0].keys())
                lines.append(f"- {name}: [{cols}]")

    return "\n".join(lines) if lines else "(none)"


def _strip_fences(text: str) -> str:
    match = re.search(r"```(?:python)?\s*\n?(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _run_computation(
    code: str, data: dict[str, Any], data_dir: str
) -> tuple[list[dict], str | None]:
    """Execute LLM-generated computation code in a restricted namespace.

    Returns (output_files, error_message).  error_message is None on success.
    """
    namespace: dict[str, Any] = {
        "data": data,
        "data_dir": data_dir,
        "output_files": [],
        # Pre-import safe standard-library modules
        "csv": csv,
        "math": math,
        "itertools": itertools,
    }
    try:
        exec(code, namespace)  # noqa: S102
        return namespace.get("output_files", []), None
    except Exception:
        return [], traceback.format_exc()


def _merge_computed_files(
    user_data: UserData,
    output_files: list[dict],
    data_dir: str,
) -> UserData:
    """Load newly written CSVs and add them to user_data."""
    new_raw_tables = dict(user_data.raw_tables)
    new_csv_specs = list(user_data.csv_specs)

    for file_info in output_files:
        filename = file_info.get("filename", "")
        if not filename:
            continue

        stem = Path(filename).stem
        filepath = Path(data_dir) / filename
        if not filepath.is_file():
            continue

        col_defs: list[dict] = file_info.get("columns", [])
        columns = [
            CsvColumnSpec(
                name=c["name"],
                dtype=c.get("dtype", "str"),
                description=c.get("description", ""),
            )
            for c in col_defs
        ]
        col_dtypes = {c.name: c.dtype for c in columns}

        rows: list[dict[str, Any]] = []
        with open(filepath, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                typed_row: dict[str, Any] = {}
                for key, value in row.items():
                    try:
                        typed_row[key] = _cast_value(value, col_dtypes.get(key, "str"))
                    except Exception:
                        typed_row[key] = value
                rows.append(typed_row)

        new_raw_tables[stem] = rows
        new_csv_specs.append(
            CsvFileSpec(
                filename=filename,
                description=file_info.get("description", ""),
                columns=columns,
            )
        )

    return user_data.model_copy(update={
        "raw_tables": new_raw_tables,
        "csv_specs": new_csv_specs,
    })
