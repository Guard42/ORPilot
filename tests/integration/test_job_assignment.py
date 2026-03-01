"""Integration tests for the job assignment example problem.

Expected optimal value: 12
  alice→task_1 (4), bob→task_2 (3), carol→task_3 (5)

Task IDs contain underscores (task_1, task_2, task_3) — this is a regression
test that the \\x1f separator correctly preserves underscore-containing IDs.
"""

from __future__ import annotations

import pytest

from orpilot.cli import _parse_variable_dimensions

pytestmark = pytest.mark.integration

SEP = "\x1f"
EXPECTED_OBJ = 12.0
TOL = 0.5


# ---------------------------------------------------------------------------
# PuLP
# ---------------------------------------------------------------------------


def test_job_assignment_pulp_optimal_status(job_assignment_pulp):
    assert job_assignment_pulp["error"] is None
    assert job_assignment_pulp["result"]["status"] == "optimal"


def test_job_assignment_pulp_objective(job_assignment_pulp):
    r = job_assignment_pulp["result"]
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL


def test_job_assignment_pulp_assignments(job_assignment_pulp):
    """Verify the optimal assignment: alice→task_1, bob→task_2, carol→task_3."""
    r = job_assignment_pulp["result"]
    assert abs(r["variables"][f"assign{SEP}alice{SEP}task_1"] - 1.0) < 0.1
    assert abs(r["variables"][f"assign{SEP}bob{SEP}task_2"] - 1.0) < 0.1
    assert abs(r["variables"][f"assign{SEP}carol{SEP}task_3"] - 1.0) < 0.1


def test_job_assignment_pulp_solution_csv(job_assignment_pulp):
    """CSV parsing must preserve task IDs with underscores as single values."""
    r = job_assignment_pulp["result"]
    grp = next(g for g in r["variable_groups"] if g["group_name"] == "assign")
    headers, rows = _parse_variable_dimensions(
        grp["variables"], "assign", dimension_labels=["worker_id", "task_id"]
    )
    assert headers == ["worker_id", "task_id", "value"]
    # task_id column (index 1) must contain whole IDs, not split on underscore
    task_ids = {row[1] for row in rows}
    assert "task_1" in task_ids
    assert "task_2" in task_ids
    assert "task_3" in task_ids
    # worker_id column (index 0) must also be intact
    worker_ids = {row[0] for row in rows}
    assert worker_ids == {"alice", "bob", "carol"}


# ---------------------------------------------------------------------------
# Pyomo
# ---------------------------------------------------------------------------


def test_job_assignment_pyomo_objective(job_assignment_pyomo):
    r = job_assignment_pyomo["result"]
    if r.get("status") == "error" and "solver" in r.get("error", "").lower():
        pytest.skip("No Pyomo-compatible solver installed")
    assert job_assignment_pyomo["error"] is None
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL


def test_job_assignment_pyomo_status(job_assignment_pyomo):
    r = job_assignment_pyomo["result"]
    if r.get("status") == "error" and "solver" in r.get("error", "").lower():
        pytest.skip("No Pyomo-compatible solver installed")
    assert r["status"] == "optimal"


# ---------------------------------------------------------------------------
# OR-Tools
# ---------------------------------------------------------------------------


def test_job_assignment_ortools_objective(job_assignment_ortools):
    assert job_assignment_ortools["error"] is None
    r = job_assignment_ortools["result"]
    assert r["status"] == "optimal"
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL
