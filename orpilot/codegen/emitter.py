"""Shared constraint loop emitter — eliminates ~350 lines of duplicated code.

The Visitor pattern extracts the domain-loop structure (lag guards, diagonal guards,
sparse-filter guards) that was repeated identically across all 5 backends.
Each backend now only provides solver-specific API calls as callbacks.

Inspired by:
- TypeScript Compiler's visitor pattern (https://github.com/Microsoft/TypeScript/wiki/Using-the-Compiler-API)
- Swift's ASTVisitor (https://github.com/apple/swift/blob/main/include/swift/AST/ASTVisitor.h)
"""

from __future__ import annotations

from typing import Callable, Protocol


# ---------------------------------------------------------------------------
# Solver-specific callbacks (each backend implements these)
# ---------------------------------------------------------------------------

class SolverEmitterCallbacks(Protocol):
    """Callbacks for solver-specific code emission.

    Each solver backend provides implementations that know how to emit
    variable creation, constraint addition, and value extraction calls
    for that specific solver API.
    """

    def emit_variable_scalar(self, name: str, lb: str, ub: str, vtype: str) -> str:
        """Emit a scalar variable declaration, e.g. ``x = m.addVar(...)``."""
        ...

    def emit_variable_1d(self, name: str, set_name: str, loop_var: str, lb: str, ub: str, vtype: str, filter_cond: str | None) -> str:
        """Emit a 1D-indexed variable, e.g. ``x = m.addVars(S, ...)``."""
        ...

    def emit_variable_2d(self, name: str, s0: str, s1: str, i0: str, i1: str, lb: str, ub: str, vtype: str, diag_guard: str, df_guard: str) -> str:
        """Emit a 2D-indexed variable."""
        ...

    def emit_variable_nd(self, name: str, idx_vars: list[str], domain: list[str], lb: str, ub: str, vtype: str, diag_guard: str, df_guard: str) -> str:
        """Emit an N-dimensional indexed variable."""
        ...

    def emit_constraint_scalar(self, name: str, lhs: str, sense: str, rhs: str) -> str:
        """Emit a scalar constraint, e.g. ``m.addConstr(lhs <= rhs)``."""
        ...

    def emit_constraint_1d(self, name: str, loop_var: str, set_name: str, lhs: str, sense: str, rhs: str) -> str:
        """Emit a 1D constraint."""
        ...

    def emit_constraint_2d(self, name: str, i0: str, i1: str, s0: str, s1: str, lhs: str, sense: str, rhs: str) -> str:
        """Emit a 2D constraint."""
        ...

    def emit_constraint_nd(self, name: str, idx_vars: list[str], domain: list[str], lhs: str, sense: str, rhs: str) -> str:
        """Emit an ND constraint."""
        ...

    def emit_extract_scalar(self, var_name: str) -> str:
        """Emit value extraction for a scalar variable, e.g. ``x.X``."""
        ...

    def emit_extract_1d(self, var_name: str, loop_var: str, set_name: str) -> str:
        """Emit value extraction for 1D variable."""
        ...

    def emit_extract_2d(self, var_name: str, i0: str, i1: str, s0: str, s1: str) -> str:
        """Emit value extraction for 2D variable."""
        ...


# ---------------------------------------------------------------------------
# Shared constraint loop emitter
# ---------------------------------------------------------------------------

class ConstraintLoopEmitter:
    """Generates constraint loop code that was previously duplicated 5 times.

    Usage::

        emitter = ConstraintLoopEmitter(compiler, index_map, parameters)
        lines = emitter.emit_constraint_loops(constraints, cb)

    Where *cb* is a solver-specific ``SolverEmitterCallbacks`` implementation.
    """

    def __init__(self, compiler, index_map: dict[str, str], parameters: dict):
        self._c = compiler         # IRCompiler instance (for helper methods)
        self._im = index_map       # set_name → index_symbol
        self._params = parameters

    def emit_constraint_loops(
        self,
        constraints: dict,
        variables: dict,
        cb: SolverEmitterCallbacks,
    ) -> list[str]:
        """Emit constraint loops for all constraints using solver callbacks."""
        lines: list[str] = []
        for cname, cmeta in constraints.items():
            domain = cmeta.get("domain", [])
            sense_op = {"<=": "<=", ">=": ">=", "=": "=="}.get(
                cmeta.get("sense", "<="), "<="
            )
            sparse_filter = cmeta.get("sparse_filter")
            extra_known = set(self._c._domain_idx_vars(domain, self._im)) if domain else set()

            # Lag detection
            lag_syms: dict[str, int] = {}
            lag_syms.update(self._c._collect_lag_symbols(
                cmeta["expression"], variables, self._params, self._c.sets_cache
            ))
            lag_syms.update(self._c._collect_lag_symbols(
                cmeta["rhs"], variables, self._params, self._c.sets_cache
            ))
            lag_ctx = self._c._build_lag_context(lag_syms, self._c.sets_cache) if lag_syms else {}

            # Expression emission (backend-specific)
            lhs = cb.emit_expression(cmeta["expression"], extra_known, lag_ctx or None)
            rhs = cb.emit_expression(cmeta["rhs"], extra_known, lag_ctx or None)

            sf_pre, sf_guard = self._c._sparse_filter_guard(
                sparse_filter, self._params, self._im, domain
            )
            if sf_pre:
                lines.append(sf_pre)

            if not domain:
                lines.append(cb.emit_constraint_scalar(cname, lhs, sense_op, rhs))
            elif len(domain) == 1:
                lines += self._emit_1d_loop(cname, domain, lhs, sense_op, rhs, sf_guard, lag_ctx, lag_syms, cb)
            elif len(domain) == 2:
                lines += self._emit_2d_loop(cname, domain, lhs, sense_op, rhs, sf_guard, lag_ctx, lag_syms, cb)
            else:
                lines += self._emit_nd_loop(cname, domain, lhs, sense_op, rhs, sf_guard, lag_ctx, lag_syms, cb)

        return lines

    def _emit_1d_loop(self, cname, domain, lhs, sense, rhs, sf_guard, lag_ctx, lag_syms, cb):
        lines = []
        idx0 = self._im[domain[0]]
        if idx0 in lag_ctx:
            _, _ev0 = lag_ctx[idx0]
            _lv0 = lag_syms[idx0]
            lines.append(f"    for {_ev0}, {idx0} in enumerate({domain[0]}):")
            if _lv0 < 0:
                lines.append(f"        if {_ev0} < {-_lv0}: continue")
            else:
                lines.append(f"        if {_ev0} + {_lv0} >= len({domain[0]}): continue")
        else:
            lines.append(f"    for {idx0} in {domain[0]}:")
        if sf_guard:
            lines.append(f"        if {sf_guard}: continue")
        lines.append(cb.emit_constraint_1d(cname, idx0, domain[0], lhs, sense, rhs))
        return lines

    def _emit_2d_loop(self, cname, domain, lhs, sense, rhs, sf_guard, lag_ctx, lag_syms, cb):
        lines = []
        idx0, idx1 = self._c._domain_idx_vars(domain, self._im)
        for iv, s in [(idx0, domain[0]), (idx1, domain[1])]:
            if iv in lag_ctx:
                prefix = "    " if iv == idx0 else "        "
                _, _ev = lag_ctx[iv]
                _lv = lag_syms[iv]
                lines.append(f"{prefix}for {_ev}, {iv} in enumerate({s}):")
                if _lv < 0:
                    lines.append(f"{prefix}    if {_ev} < {-_lv}: continue")
                else:
                    lines.append(f"{prefix}    if {_ev} + {_lv} >= len({s}): continue")
            else:
                prefix = "    " if iv == idx0 else "        "
                lines.append(f"{prefix}for {iv} in {s}:")
        guard = self._c._constraint_diagonal_guard(domain, [idx0, idx1])
        if guard:
            lines.append(f"            if {guard}: continue")
        if sf_guard:
            lines.append(f"            if {sf_guard}: continue")
        lines.append(cb.emit_constraint_2d(cname, idx0, idx1, domain[0], domain[1], lhs, sense, rhs))
        return lines

    def _emit_nd_loop(self, cname, domain, lhs, sense, rhs, sf_guard, lag_ctx, lag_syms, cb):
        lines = []
        idx_vars = self._c._domain_idx_vars(domain, self._im)
        for k, (iv, s) in enumerate(zip(idx_vars, domain)):
            if iv in lag_ctx:
                _, _ev = lag_ctx[iv]
                _lv = lag_syms[iv]
                lines.append(f"{'    ' * k}for {_ev}, {iv} in enumerate({s}):")
                if _lv < 0:
                    lines.append(f"{'    ' * (k + 1)}if {_ev} < {-_lv}: continue")
                else:
                    lines.append(f"{'    ' * (k + 1)}if {_ev} + {_lv} >= len({s}): continue")
            else:
                lines.append(f"{'    ' * k}for {iv} in {s}:")
        inner = "    " * (len(domain) + 1)
        guard = self._c._constraint_diagonal_guard(domain, idx_vars)
        if guard:
            lines.append(f"{inner}if {guard}: continue")
        if sf_guard:
            lines.append(f"{inner}if {sf_guard}: continue")
        lines.append(cb.emit_constraint_nd(cname, idx_vars, domain, lhs, sense, rhs))
        return lines
