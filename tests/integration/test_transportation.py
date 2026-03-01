"""Integration tests for the transportation example problem.

Expected optimal value: 280
  W1→C3=30 (cost 1), W1→C1=20 (cost 2), W2→C1=10 (cost 5), W2→C2=40 (cost 4)
  Total = 30+40+50+160 = 280
"""

from __future__ import annotations

import pytest

from orpilot.cli import _parse_variable_dimensions

pytestmark = pytest.mark.integration

SEP = "\x1f"
EXPECTED_OBJ = 280.0
TOL = 1.0  # absolute tolerance for floating-point objective comparison


# ---------------------------------------------------------------------------
# PuLP
# ---------------------------------------------------------------------------


def test_transportation_pulp_optimal_status(transportation_pulp):
    assert transportation_pulp["error"] is None
    assert transportation_pulp["result"]["status"] == "optimal"


def test_transportation_pulp_objective(transportation_pulp):
    r = transportation_pulp["result"]
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL


def test_transportation_pulp_flow_values(transportation_pulp):
    """Spot-check: W1→C3 must carry the full C3 demand (30 units) at optimality."""
    r = transportation_pulp["result"]
    flow_w1_c3 = r["variables"][f"flow{SEP}W1{SEP}C3"]
    assert abs(flow_w1_c3 - 30.0) < 0.1


def test_transportation_pulp_solution_csv(transportation_pulp):
    """CSV parsing of the flow variable must not split IDs on underscores."""
    r = transportation_pulp["result"]
    grp = next(g for g in r["variable_groups"] if g["group_name"] == "flow")
    headers, rows = _parse_variable_dimensions(
        grp["variables"], "flow", dimension_labels=["warehouse_id", "customer_id"]
    )
    assert headers == ["warehouse_id", "customer_id", "value"]
    # Every warehouse_id value must be exactly "W1" or "W2" (not split)
    warehouse_ids = {row[0] for row in rows}
    assert warehouse_ids == {"W1", "W2"}
    # Every customer_id value must be exactly "C1", "C2", or "C3"
    customer_ids = {row[1] for row in rows}
    assert customer_ids == {"C1", "C2", "C3"}


# ---------------------------------------------------------------------------
# Pyomo
# ---------------------------------------------------------------------------


def test_transportation_pyomo_objective(transportation_pyomo):
    r = transportation_pyomo["result"]
    if r.get("status") == "error" and "solver" in r.get("error", "").lower():
        pytest.skip("No Pyomo-compatible solver installed")
    assert transportation_pyomo["error"] is None
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL


def test_transportation_pyomo_status(transportation_pyomo):
    r = transportation_pyomo["result"]
    if r.get("status") == "error" and "solver" in r.get("error", "").lower():
        pytest.skip("No Pyomo-compatible solver installed")
    assert r["status"] == "optimal"


# ---------------------------------------------------------------------------
# OR-Tools
# ---------------------------------------------------------------------------


def test_transportation_ortools_objective(transportation_ortools):
    assert transportation_ortools["error"] is None
    r = transportation_ortools["result"]
    assert r["status"] == "optimal"
    assert abs(r["objective_value"] - EXPECTED_OBJ) < TOL
