"""TextIngestor — parse a plain-text OR problem into structured data via LLM."""

from __future__ import annotations

import json
import re
from typing import Any

from orpilot.llm.base import BaseLLM
from orpilot.models.problem import (
    Constraint,
    ObjectiveType,
    ProblemDefinition,
    ProblemType,
)
from orpilot.prompts.ingestor import SYSTEM_PROMPT


def _strip_fences(text: str) -> str:
    pattern = r"```(?:json)?\s*\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_problem_type(raw: str) -> ProblemType:
    mapping = {
        "transportation": ProblemType.TRANSPORTATION,
        "assignment": ProblemType.ASSIGNMENT,
        "scheduling": ProblemType.SCHEDULING,
        "network_flow": ProblemType.NETWORK_FLOW,
        "linear_programming": ProblemType.LINEAR_PROGRAMMING,
        "integer_programming": ProblemType.INTEGER_PROGRAMMING,
        "mixed_integer": ProblemType.MIXED_INTEGER,
    }
    return mapping.get(raw.lower().strip(), ProblemType.OTHER)


def _parse_objective_type(raw: str) -> ObjectiveType:
    if raw.lower().strip() == "maximize":
        return ObjectiveType.MAXIMIZE
    return ObjectiveType.MINIMIZE


class TextIngestor:
    """Parse a plain-text benchmark problem description using one LLM call."""

    def ingest(
        self, text: str, llm: BaseLLM
    ) -> tuple[ProblemDefinition, dict[str, list[dict[str, Any]]]]:
        """Parse *text* and return ``(problem_def, tables_dict)``.

        ``tables_dict`` maps each table stem to a list of row dicts.
        Raises ``ValueError`` if the LLM response cannot be parsed.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        response = llm.chat(messages)
        raw = _strip_fences(response)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"TextIngestor: LLM returned invalid JSON: {exc}\n---\n{raw}") from exc

        p = data.get("problem", {})
        constraints = [
            Constraint(description=c) if isinstance(c, str) else Constraint(**c)
            for c in p.get("constraints", [])
        ]
        problem_def = ProblemDefinition(
            title=p.get("title", ""),
            description=p.get("description", text),
            problem_type=_parse_problem_type(p.get("problem_type", "other")),
            objective=_parse_objective_type(p.get("objective", "minimize")),
            objective_description=p.get("objective_description", ""),
            constraints=constraints,
            decision_variables=p.get("decision_variables", []),
        )
        tables: dict[str, list[dict[str, Any]]] = data.get("tables", {})
        return problem_def, tables
