"""IndustryOR HuggingFace dataset benchmark tests — require a live LLM API key."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from orpilot.benchmark.runner import BenchmarkRunner

log = logging.getLogger(__name__)


def _save_artifacts(result, case, out_dir: Path) -> None:
    """Write ir.json, model.py, and model.lp for a case into out_dir/<case_name>/."""
    case_dir = out_dir / case.name
    case_dir.mkdir(parents=True, exist_ok=True)
    if result.ir_model:
        (case_dir / "ir.json").write_text(json.dumps(result.ir_model, indent=2), encoding="utf-8")
    if result.generated_code:
        (case_dir / "model.py").write_text(result.generated_code, encoding="utf-8")
    if result.lp_content:
        (case_dir / "model.lp").write_text(result.lp_content, encoding="utf-8")


@pytest.mark.llm
@pytest.mark.industryOR
def test_industryOR_sample(llm_fixture, save_dir, generate_ir, difficulty, limit):
    """Load IndustryOR cases and run the direct code gen pipeline for each.

    Pass --difficulty Easy|Medium|Hard to select the difficulty tier (default: Easy).
    Pass --limit N to cap the number of cases (default: all).
    Pass --generate-ir to also produce a solver-agnostic IR blueprint after each
    successful solve (or set generate_ir=true in orpilot.toml).
    """
    pytest.importorskip("datasets", reason="pip install 'orpilot[hf]' to run IndustryOR tests")

    from orpilot.benchmark.loader_hf import load_hf_cases

    cases = load_hf_cases("CardinalOperations/IndustryOR", difficulty=difficulty, limit=limit)
    assert cases, f"No {difficulty} cases loaded from CardinalOperations/IndustryOR"

    runner = BenchmarkRunner(timeout=180)
    passed = 0
    failures: list[str] = []
    solve_times: list[float] = []

    mode_label = "direct+ir" if generate_ir else "direct"
    log.info("Running %d IndustryOR %s cases (mode=%s)", len(cases), difficulty, mode_label)
    suite_start = time.monotonic()
    for i, case in enumerate(cases, 1):
        log.info("[%d/%d] %s (expected %s) ...", i, len(cases), case.name, case.expected_objective)
        result = runner.run_direct_pipeline(case, llm_fixture, solver="pulp", generate_ir=generate_ir)
        solve_times.append(result.solve_time)
        if save_dir:
            _save_artifacts(result, case, save_dir)
        if result.passed:
            passed += 1
            log.info("  PASS  (obj=%s, time=%.1fs)", result.objective_value, result.solve_time)
        else:
            msg = (
                f"status={result.status}, "
                f"obj={result.objective_value} (expected {case.expected_objective}), "
                f"error={result.error}"
            )
            log.info("  FAIL  (%s)", msg)
            failures.append(f"{case.name}: {msg}")

    total = len(cases)
    pct = 100.0 * passed / total if total else 0.0
    total_wall = time.monotonic() - suite_start
    avg_t = sum(solve_times) / len(solve_times) if solve_times else 0.0
    min_t = min(solve_times) if solve_times else 0.0
    max_t = max(solve_times) if solve_times else 0.0
    log.info("=" * 60)
    log.info("  RESULT: %d/%d passed (%.1f%%)", passed, total, pct)
    log.info("  TIME:   total=%.1fs  avg=%.1fs  min=%.1fs  max=%.1fs", total_wall, avg_t, min_t, max_t)
    if failures:
        log.info("  FAILED cases:")
        for f in failures:
            log.info("    - %s", f)
    log.info("=" * 60)

    assert not failures, f"{len(failures)}/{total} IndustryOR cases failed:\n" + "\n".join(failures)
