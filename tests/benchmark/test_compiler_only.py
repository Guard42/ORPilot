"""Compiler-only benchmark tests (Mode C) — no LLM required."""

from __future__ import annotations

import pytest

from orpilot.benchmark.case import BenchmarkCase
from orpilot.benchmark.runner import BenchmarkRunner


@pytest.mark.benchmark
@pytest.mark.parametrize("solver", ["pulp"])
def test_compiler_only_all_cases(compiler_cases: list[BenchmarkCase], solver: str):
    """All cases with ir.json + data/ pass the compiler-only mode."""
    if not compiler_cases:
        pytest.skip("No compiler-ready cases found in benchmarks/")

    runner = BenchmarkRunner(timeout=60)
    failures = []

    for case in compiler_cases:
        result = runner.run_compiler_only(
            case=case,
            ir_model=case.ir_model,  # type: ignore[arg-type]
            tables=case.tables,  # type: ignore[arg-type]
            solver=solver,
        )
        if not result.passed:
            failures.append(
                f"{case.name}: status={result.status}, "
                f"obj={result.objective_value} (expected {case.expected_objective}), "
                f"error={result.error}"
            )

    if failures:
        pytest.fail("Compiler-only benchmark failures:\n" + "\n".join(failures))


@pytest.mark.benchmark
@pytest.mark.parametrize("solver", ["pulp"])
def test_transportation_compiler(solver: str):
    """Transportation problem — compiler-only smoke test."""
    from orpilot.benchmark.loader import load_benchmark_case
    from pathlib import Path

    case_dir = Path(__file__).parent.parent.parent / "benchmarks" / "nlp4lp" / "001_transportation"
    if not case_dir.exists():
        pytest.skip(f"Case directory not found: {case_dir}")

    case = load_benchmark_case(case_dir)
    assert case.ir_model is not None, "ir.json missing"
    assert case.tables is not None, "data/ missing"

    runner = BenchmarkRunner(timeout=60)
    result = runner.run_compiler_only(case, case.ir_model, case.tables, solver)

    assert result.error is None, f"Execution error: {result.error}"
    assert result.status == "optimal", f"Expected optimal, got {result.status}"
    assert result.passed, (
        f"Objective mismatch: got {result.objective_value}, expected {case.expected_objective}"
    )


@pytest.mark.benchmark
@pytest.mark.parametrize("solver", ["pulp"])
def test_knapsack_compiler(solver: str):
    """Knapsack problem — compiler-only smoke test."""
    from orpilot.benchmark.loader import load_benchmark_case
    from pathlib import Path

    case_dir = Path(__file__).parent.parent.parent / "benchmarks" / "nlp4lp" / "002_knapsack"
    if not case_dir.exists():
        pytest.skip(f"Case directory not found: {case_dir}")

    case = load_benchmark_case(case_dir)
    assert case.ir_model is not None, "ir.json missing"
    assert case.tables is not None, "data/ missing"

    runner = BenchmarkRunner(timeout=60)
    result = runner.run_compiler_only(case, case.ir_model, case.tables, solver)

    assert result.error is None, f"Execution error: {result.error}"
    assert result.status == "optimal", f"Expected optimal, got {result.status}"
    assert result.passed, (
        f"Objective mismatch: got {result.objective_value}, expected {case.expected_objective}"
    )
