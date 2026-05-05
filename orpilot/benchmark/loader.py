"""Load BenchmarkCase objects from the filesystem."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from orpilot.benchmark.case import BenchmarkCase


def _load_csv(path: Path) -> list[dict[str, Any]]:
    """Read a CSV file and return rows as dicts, coercing numeric strings."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            typed: dict[str, Any] = {}
            for k, v in row.items():
                try:
                    typed[k] = int(v)
                    continue
                except (ValueError, TypeError):
                    pass
                try:
                    typed[k] = float(v)
                    continue
                except (ValueError, TypeError):
                    pass
                typed[k] = v
            rows.append(typed)
    return rows


def load_benchmark_case(case_dir: Path) -> BenchmarkCase:
    """Load a BenchmarkCase from a directory.

    Required files:
        problem.txt   — NLP4LP-style problem description
        expected.json — {"objective", "status", "tolerance", "source", "tags"}

    Optional files:
        data/*.csv    — pre-extracted tables (enables Mode B / C)
        ir.json       — reference IR (enables Mode C)
    """
    case_dir = Path(case_dir)

    problem_path = case_dir / "problem.txt"
    if not problem_path.exists():
        raise FileNotFoundError(f"Missing problem.txt in {case_dir}")

    expected_path = case_dir / "expected.json"
    if not expected_path.exists():
        raise FileNotFoundError(f"Missing expected.json in {case_dir}")

    problem_text = problem_path.read_text(encoding="utf-8").strip()
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    # Load pre-extracted tables if data/ exists
    tables: dict[str, list[dict[str, Any]]] | None = None
    data_dir = case_dir / "data"
    if data_dir.is_dir():
        csv_files = sorted(data_dir.glob("*.csv"))
        if csv_files:
            tables = {p.stem: _load_csv(p) for p in csv_files}

    # Load reference IR if present
    ir_model: dict | None = None
    ir_path = case_dir / "ir.json"
    if ir_path.exists():
        ir_model = json.loads(ir_path.read_text(encoding="utf-8"))

    return BenchmarkCase(
        name=case_dir.name,
        problem_text=problem_text,
        tables=tables,
        ir_model=ir_model,
        expected_objective=expected.get("objective"),
        expected_status=expected.get("status", "optimal"),
        objective_tolerance=expected.get("tolerance", 1e-4),
        source=expected.get("source", ""),
        tags=expected.get("tags", []),
    )


def load_all_cases(root: Path) -> list[BenchmarkCase]:
    """Recursively find all directories containing expected.json and load them."""
    root = Path(root)
    cases = []
    for expected_path in sorted(root.rglob("expected.json")):
        case_dir = expected_path.parent
        try:
            cases.append(load_benchmark_case(case_dir))
        except Exception as exc:
            import warnings
            warnings.warn(f"Skipping {case_dir}: {exc}", stacklevel=2)
    return cases
