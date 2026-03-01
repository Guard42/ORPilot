"""Shared fixtures and helpers for integration tests."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from orpilot.codegen.ir_compiler import IRCompiler
from orpilot.codegen.executor import CodeExecutor

EXAMPLES_DIR = Path(__file__).parents[2] / "examples"

PULP_AVAILABLE = importlib.util.find_spec("pulp") is not None
PYOMO_AVAILABLE = importlib.util.find_spec("pyomo") is not None
ORTOOLS_AVAILABLE = importlib.util.find_spec("ortools") is not None


def load_example_data(example_dir: Path) -> dict:
    """Read all CSV files from example_dir/data/ into a dict keyed by file stem.

    Values are kept as strings — the generated solver code performs its own
    type conversion (e.g. float(_row['supply'])).
    """
    data: dict = {}
    data_dir = example_dir / "data"
    for csv_path in sorted(data_dir.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        data[csv_path.stem] = rows
    return data


def compile_and_solve(problem_name: str, solver_framework: str) -> dict:
    """Load IR, compile, load data, execute and return executor result dict."""
    example_dir = EXAMPLES_DIR / problem_name
    ir = json.loads((example_dir / "ir.json").read_text(encoding="utf-8"))
    code = IRCompiler().compile(ir, solver_framework)
    data = load_example_data(example_dir)
    return CodeExecutor(timeout=60).execute(code, data)


# ---------------------------------------------------------------------------
# Fixtures — one per (problem × backend) combination
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def transportation_pulp():
    pytest.importorskip("pulp")
    return compile_and_solve("transportation", "pulp")


@pytest.fixture(scope="module")
def transportation_pyomo():
    pytest.importorskip("pyomo.environ")
    return compile_and_solve("transportation", "pyomo")


@pytest.fixture(scope="module")
def transportation_ortools():
    pytest.importorskip("ortools.linear_solver.pywraplp")
    return compile_and_solve("transportation", "ortools")


@pytest.fixture(scope="module")
def knapsack_pulp():
    pytest.importorskip("pulp")
    return compile_and_solve("knapsack", "pulp")


@pytest.fixture(scope="module")
def knapsack_pyomo():
    pytest.importorskip("pyomo.environ")
    return compile_and_solve("knapsack", "pyomo")


@pytest.fixture(scope="module")
def knapsack_ortools():
    pytest.importorskip("ortools.linear_solver.pywraplp")
    return compile_and_solve("knapsack", "ortools")


@pytest.fixture(scope="module")
def job_assignment_pulp():
    pytest.importorskip("pulp")
    return compile_and_solve("job_assignment", "pulp")


@pytest.fixture(scope="module")
def job_assignment_pyomo():
    pytest.importorskip("pyomo.environ")
    return compile_and_solve("job_assignment", "pyomo")


@pytest.fixture(scope="module")
def job_assignment_ortools():
    pytest.importorskip("ortools.linear_solver.pywraplp")
    return compile_and_solve("job_assignment", "ortools")
