"""Integration tests for the knapsack example problem.

Expected optimal value: 35
  camera(10) + book(5) + phone(8) + tablet(12) selected, weight=3+1+2+4=10
"""

from __future__ import annotations

import pytest

from orpilot.cli import _parse_variable_dimensions

pytestmark = pytest.mark.integration

SEP = "\x1f"
EXPECTED_OBJ = 35.0
TOL = 0.5


# ---------------------------------------------------------------------------
# PuLP
# ---------------------------------------------------------------------------


def test_knapsack_pulp_optimal_status(knapsack_pulp):
    assert knapsack_pulp["error"] is None
    assert knapsack_pulp["result"]["status"] == "optimal"


def test_knapsack_pulp_objective(knapsack_pulp):
    r = knapsack_pulp["result"]
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL


def test_knapsack_pulp_selected_items(knapsack_pulp):
    """camera, book, phone, tablet selected; laptop not selected."""
    r = knapsack_pulp["result"]
    assert abs(r["variables"][f"x{SEP}camera"] - 1.0) < 0.1
    assert abs(r["variables"][f"x{SEP}book"] - 1.0) < 0.1
    assert abs(r["variables"][f"x{SEP}phone"] - 1.0) < 0.1
    assert abs(r["variables"][f"x{SEP}tablet"] - 1.0) < 0.1
    assert abs(r["variables"][f"x{SEP}laptop"]) < 0.1


def test_knapsack_pulp_solution_csv(knapsack_pulp):
    """CSV parsing: item_id column must not be split on underscores."""
    r = knapsack_pulp["result"]
    grp = next(g for g in r["variable_groups"] if g["group_name"] == "x")
    headers, rows = _parse_variable_dimensions(
        grp["variables"], "x", dimension_labels=["item_id"]
    )
    assert headers == ["item_id", "value"]
    item_ids = {row[0] for row in rows}
    # All five items should appear (no extra splits)
    assert item_ids == {"laptop", "camera", "book", "phone", "tablet"}


# ---------------------------------------------------------------------------
# Pyomo
# ---------------------------------------------------------------------------


def test_knapsack_pyomo_objective(knapsack_pyomo):
    r = knapsack_pyomo["result"]
    if r.get("status") == "error" and "solver" in r.get("error", "").lower():
        pytest.skip("No Pyomo-compatible solver installed")
    assert knapsack_pyomo["error"] is None
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL


def test_knapsack_pyomo_status(knapsack_pyomo):
    r = knapsack_pyomo["result"]
    if r.get("status") == "error" and "solver" in r.get("error", "").lower():
        pytest.skip("No Pyomo-compatible solver installed")
    assert r["status"] == "optimal"


# ---------------------------------------------------------------------------
# OR-Tools
# ---------------------------------------------------------------------------


def test_knapsack_ortools_objective(knapsack_ortools):
    assert knapsack_ortools["error"] is None
    r = knapsack_ortools["result"]
    assert r["status"] == "optimal"
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL
