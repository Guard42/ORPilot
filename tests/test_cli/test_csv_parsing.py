"""Tests for _parse_variable_dimensions in orpilot.cli.

Covers:
- Unit-separator (\x1f) dimension splitting — regression for underscore-in-ID bug
- Header generation (from labels vs. auto-generated)
- Legacy underscore fallback
- Tuple-style key fallback
- Row count and zero-dim (scalar) variable
"""

from __future__ import annotations

import pytest

from orpilot.cli import _parse_variable_dimensions

SEP = "\x1f"  # unit separator used by IR compiler


# ---------------------------------------------------------------------------
# Unit-separator regression tests (underscore-in-ID bug)
# ---------------------------------------------------------------------------


def test_unit_sep_1dim_id_with_underscore():
    """Single-dim key with underscore in the ID splits correctly on \\x1f."""
    variables = {f"visits{SEP}customer_10": 5.0}
    headers, rows = _parse_variable_dimensions(variables, "visits")
    assert headers == ["dim_1", "value"]
    assert rows[0] == ["customer_10", 5.0]


def test_unit_sep_2dim_both_ids_have_underscores():
    """2-dim key: each dim value contains underscores, must not be split further."""
    variables = {f"arc_flows{SEP}customer_10{SEP}customer_1": 3.0}
    headers, rows = _parse_variable_dimensions(variables, "arc_flows")
    assert headers == ["dim_1", "dim_2", "value"]
    assert rows[0] == ["customer_10", "customer_1", 3.0]


def test_unit_sep_3dim():
    """3-dim key with unit separators."""
    variables = {f"arc_flows{SEP}customer_10{SEP}customer_1{SEP}0": 1.0}
    headers, rows = _parse_variable_dimensions(variables, "arc_flows")
    assert headers == ["dim_1", "dim_2", "dim_3", "value"]
    assert rows[0] == ["customer_10", "customer_1", "0", 1.0]


# ---------------------------------------------------------------------------
# Header generation
# ---------------------------------------------------------------------------


def test_headers_from_dimension_labels():
    """When dimension_labels are provided, they are used as column names."""
    variables = {
        f"assign{SEP}alice{SEP}task_1": 1.0,
        f"assign{SEP}bob{SEP}task_2": 1.0,
    }
    headers, rows = _parse_variable_dimensions(
        variables, "assign", dimension_labels=["worker_id", "task_id"]
    )
    assert headers == ["worker_id", "task_id", "value"]


def test_headers_auto_generated():
    """Without labels, headers are dim_1, dim_2, ..., value."""
    variables = {f"x{SEP}A{SEP}B": 1.0}
    headers, _ = _parse_variable_dimensions(variables, "x")
    assert headers == ["dim_1", "dim_2", "value"]


# ---------------------------------------------------------------------------
# Legacy underscore fallback (no \x1f in key)
# ---------------------------------------------------------------------------


def test_legacy_underscore_1dim():
    """Legacy key 'flow_WH1' with group_name='flow' → dims=['WH1']."""
    variables = {"flow_WH1": 10.0}
    headers, rows = _parse_variable_dimensions(variables, "flow")
    assert rows[0][0] == "WH1"
    assert rows[0][-1] == 10.0


def test_legacy_underscore_2dim():
    """Legacy key 'flow_WH1_C1' → dims=['WH1', 'C1']."""
    variables = {"flow_WH1_C1": 15.0}
    headers, rows = _parse_variable_dimensions(variables, "flow")
    assert rows[0][:2] == ["WH1", "C1"]
    assert rows[0][-1] == 15.0


# ---------------------------------------------------------------------------
# Tuple-style key fallback
# ---------------------------------------------------------------------------


def test_tuple_style_key():
    """Key in tuple notation: ship_('WH1', 'C1') → dims=['WH1', 'C1']."""
    variables = {"ship_('WH1', 'C1')": 20.0}
    headers, rows = _parse_variable_dimensions(variables, "ship")
    assert rows[0][:2] == ["WH1", "C1"]
    assert rows[0][-1] == 20.0


# ---------------------------------------------------------------------------
# Row count and zero-dim variable
# ---------------------------------------------------------------------------


def test_all_variables_produce_rows():
    """N variables produce exactly N data rows (excluding header)."""
    n = 5
    variables = {f"x{SEP}item_{k}": float(k) for k in range(n)}
    headers, rows = _parse_variable_dimensions(variables, "x")
    assert len(rows) == n


def test_zero_dim_variable():
    """Scalar variable (key == group_name) produces a single row with only the value."""
    variables = {"total_cost": 42.0}
    headers, rows = _parse_variable_dimensions(variables, "total_cost")
    assert headers == ["value"]
    assert rows == [[42.0]]
