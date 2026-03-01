"""Full-pipeline benchmark tests — require a live LLM API key."""

from __future__ import annotations

import pytest

from orpilot.benchmark.case import BenchmarkCase
from orpilot.benchmark.runner import BenchmarkRunner


@pytest.mark.llm
def test_transportation_full_pipeline(llm_fixture):
    """Transportation — full pipeline (TextIngestor → ir_builder → compiler → solver)."""
    from orpilot.benchmark.loader import load_benchmark_case
    from pathlib import Path

    case_dir = Path(__file__).parent.parent.parent / "benchmarks" / "nlp4lp" / "001_transportation"
    case = load_benchmark_case(case_dir)

    # Strip pre-loaded artifacts so we actually exercise the full pipeline
    case = BenchmarkCase(
        name=case.name,
        problem_text=case.problem_text,
        expected_objective=case.expected_objective,
        expected_status=case.expected_status,
        objective_tolerance=case.objective_tolerance,
        source=case.source,
        tags=case.tags,
    )

    runner = BenchmarkRunner(timeout=120)
    result = runner.run_full_pipeline(case, llm_fixture, solver="pulp")

    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.passed, (
        f"Objective mismatch: got {result.objective_value}, expected {case.expected_objective}"
    )


@pytest.mark.llm
def test_transportation_ir_builder(llm_fixture):
    """Transportation — IR builder mode (pre-extracted tables, 1 LLM call)."""
    from orpilot.benchmark.loader import load_benchmark_case
    from pathlib import Path

    case_dir = Path(__file__).parent.parent.parent / "benchmarks" / "nlp4lp" / "001_transportation"
    case = load_benchmark_case(case_dir)
    assert case.tables is not None

    runner = BenchmarkRunner(timeout=120)
    result = runner.run_with_ir_builder(case, case.tables, llm_fixture, solver="pulp")

    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.passed, (
        f"Objective mismatch: got {result.objective_value}, expected {case.expected_objective}"
    )


@pytest.mark.llm
@pytest.mark.parametrize("case_name", ["001_transportation", "002_knapsack"])
def test_all_cases_ir_builder(case_name: str, llm_fixture):
    """Parametrised IR-builder test over named benchmark cases."""
    from orpilot.benchmark.loader import load_benchmark_case
    from pathlib import Path

    case_dir = Path(__file__).parent.parent.parent / "benchmarks" / "nlp4lp" / case_name
    if not case_dir.exists():
        pytest.skip(f"Case not found: {case_dir}")

    case = load_benchmark_case(case_dir)
    if case.tables is None:
        pytest.skip(f"No pre-extracted tables for {case_name} — run full pipeline instead")

    runner = BenchmarkRunner(timeout=120)
    result = runner.run_with_ir_builder(case, case.tables, llm_fixture, solver="pulp")

    assert result.passed, (
        f"{case_name}: status={result.status}, obj={result.objective_value} "
        f"(expected {case.expected_objective}), error={result.error}"
    )
