"""Deterministic IR → Python compiler (PuLP, Pyomo, OR-Tools backends)."""

from __future__ import annotations

from pathlib import Path


class IRCompiler:
    """Compiles a JSON IR dict into a solver-specific Python solve(data) function."""

    @staticmethod
    def _normalize_ir(ir: dict) -> dict:
        """Strip ':alias' suffixes from domain arrays in variables, constraints, and parameters.

        The LLM occasionally writes the 'Set:alias' notation (only valid inside
        indexed_sum.over arrays) into variable/constraint/parameter domain fields.
        This causes a KeyError in _domain_idx_vars because 'Locations:l' is not
        a key in index_map.  Normalise before compiling so the compiler always
        receives plain set names in domain fields.
        """
        def _strip(items: list[str]) -> list[str]:
            return [s.split(":")[0].strip() if ":" in s else s for s in items]

        for meta in ir.get("variables", {}).values():
            meta["domain"] = _strip(meta.get("domain", []))
        for meta in ir.get("constraints", {}).values():
            meta["domain"] = _strip(meta.get("domain", []))
        for meta in ir.get("parameters", {}).values():
            meta["domain"] = _strip(meta.get("domain", []))
        return ir

    def compile(self, ir: dict, solver_framework: str = "pulp") -> str:
        ir = self._normalize_ir(ir)
        if solver_framework == "pulp":
            return self._compile_pulp(ir)
        if solver_framework == "pyomo":
            return self._compile_pyomo(ir)
        if solver_framework in ("ortools", "or-tools"):
            return self._compile_ortools(ir)
        raise NotImplementedError(f"Solver framework '{solver_framework}' is not yet supported.")

    # ------------------------------------------------------------------
    # Shared helpers — set/parameter loading, variable groups
    # ------------------------------------------------------------------

    def _emit_set_loading(self, sets: dict, set_column: dict) -> list[str]:
        """Emit lines that load each set's members from data."""
        lines = []
        for set_name, meta in sets.items():
            source = meta.get("source")
            column = meta.get("column")
            table_stem = Path(source).stem if source else None

            if table_stem and column:
                lines.append(
                    f"    {set_name} = list(dict.fromkeys("
                    f"row[{column!r}] for row in data[{table_stem!r}]))"
                )
            elif table_stem:
                lines.append(
                    f"    {set_name} = list(dict.fromkeys("
                    f"next(iter(row.values())) for row in data[{table_stem!r}]))"
                )
            else:
                size = meta.get("size")
                size_source = meta.get("size_source")
                size_column = meta.get("size_column")
                if size_source and size_column:
                    size_stem = Path(size_source).stem
                    lines.append(
                        f"    {set_name} = list(range(int(float("
                        f"data[{size_stem!r}][0][{size_column!r}]))))"
                    )
                elif size is not None:
                    lines.append(f"    {set_name} = list(range({size}))")
                else:
                    lines.append(
                        f"    {set_name} = []  # TODO: no source specified for set {set_name!r}"
                    )
        return lines

    def _emit_parameter_loading(
        self, parameters: dict, set_column: dict, index_map: dict
    ) -> list[str]:
        """Emit lines that load each parameter as a dict keyed by set indices."""
        lines = []
        for param_name, meta in parameters.items():
            domain = meta.get("domain", [])
            source = meta.get("source")
            table_stem = Path(source).stem if source else None

            if not table_stem:
                lines.append(
                    f"    {param_name} = {{}}  # TODO: no source for parameter {param_name!r}"
                )
                continue

            # Per-index key columns: use explicit index_columns if provided, else fall back to
            # set_column (the set's own "column" field) or the index symbol / lowercased set name.
            index_columns = meta.get("index_columns")
            if index_columns:
                col_names = list(index_columns)
            else:
                col_names = [set_column.get(s) or index_map.get(s, s.lower()) for s in domain]
            # Column that holds the parameter's value in the CSV.
            # Use the explicit "column" from the IR if present; fall back to param_name.
            value_col = meta.get("column") or param_name

            # Scalar parameter (no domain): read directly from the first CSV row.
            if not domain:
                lines.append(
                    f"    {param_name} = float(data[{table_stem!r}][0][{value_col!r}])"
                )
                continue

            lines.append(f"    {param_name} = {{}}")
            lines.append(f"    for _row in data[{table_stem!r}]:")

            if len(domain) == 1:
                c0 = col_names[0]
                lines.append(
                    f"        _key = _row.get({c0!r}) or next("
                    f"v for k, v in _row.items() if k != {value_col!r})"
                )
                lines.append(f"        {param_name}[_key] = float(_row[{value_col!r}])")
            elif len(domain) == 2:
                c0, c1 = col_names[0], col_names[1]
                lines.append(
                    f"        _k1 = _row.get({c0!r}) or _row.get({domain[0].lower()!r})"
                )
                lines.append(
                    f"        _k2 = _row.get({c1!r}) or _row.get({domain[1].lower()!r})"
                )
                lines.append(
                    f"        {param_name}[(_k1, _k2)] = float(_row[{value_col!r}])"
                )
            else:
                lines.append(f"        pass  # TODO: domain {domain!r} not supported")
        return lines

    def _emit_variable_groups(self, variables: dict) -> list[str]:
        """Emit lines that build result['variable_groups'] from result['variables']."""
        lines = []
        for var_name, meta in variables.items():
            dim_labels = [d.lower() for d in meta.get("domain", [])]
            group_name = meta.get("label") or var_name
            lines.extend([
                f"    _grp_{var_name} = {{",
                f"        k: v for k, v in result['variables'].items()",
                f"        if k.startswith({var_name!r} + '\\x1f')",
                f"    }}",
                f"    result['variable_groups'].append({{",
                f"        'group_name': {group_name!r},",
                f"        'dimension_labels': {dim_labels!r},",
                f"        'variables': _grp_{var_name},",
                f"    }})",
            ])
        return lines

    # ------------------------------------------------------------------
    # Expression tree walkers
    # ------------------------------------------------------------------

    def _var_ref(
        self,
        name: str,
        indices: list[str],
        domain: list[str],
        known_symbols: set[str] | None = None,
        use_get: bool = False,
    ) -> str:
        """Return the dict-style variable reference used by PuLP and OR-Tools.

        Any index that is not a recognised loop-variable symbol is treated as a
        string literal and emitted with ``repr()`` (e.g. the hard-coded depot
        label ``"depot"`` in depot_start_end constraints).

        When *use_get* is True, emits ``name.get(key, 0)`` instead of
        ``name[key]``, so that variables with ``exclude_diagonal`` never raise
        a KeyError for self-loop indices.
        """
        if not indices or not domain:
            return name

        def _fmt(idx: str) -> str:
            if known_symbols is not None and idx not in known_symbols:
                return repr(idx)
            return idx

        if len(domain) == 1:
            key = _fmt(indices[0])
            return f"{name}.get({key}, 0)" if use_get else f"{name}[{key}]"
        idx_parts = ", ".join(_fmt(i) for i in indices[: len(domain)])
        key = f"({idx_parts})"
        return f"{name}.get({key}, 0)" if use_get else f"{name}[{key}]"

    @staticmethod
    def _domain_idx_vars(domain: list[str], index_map: dict[str, str]) -> list[str]:
        """Return a unique loop-variable name for each set in *domain*.

        When the same set appears more than once, a 1-based numeric suffix is
        appended so the generated Python code has distinct loop variables:
        e.g. ``["Locations", "Locations", "Trips"]`` → ``["l1", "l2", "t"]``.
        Single-occurrence sets keep their plain symbol (``"t"``).
        """
        counts: dict[str, int] = {}
        for s in domain:
            counts[s] = counts.get(s, 0) + 1
        seen: dict[str, int] = {}
        result: list[str] = []
        for s in domain:
            base = index_map[s]
            seen[s] = seen.get(s, 0) + 1
            result.append(f"{base}{seen[s]}" if counts[s] > 1 else base)
        return result

    @staticmethod
    def _constraint_diagonal_guard(domain: list[str], idx_vars: list[str]) -> str | None:
        """Return an 'idxA == idxB' guard expression if the same set appears twice in domain.

        Used to skip trivial self-pair iterations in constraint loops (e.g. MTZ where
        c1==c2 produces 0 <= N-1, wasting solver time on junk constraints).
        Returns the first duplicate pair found, or None if all sets are distinct.
        """
        seen: dict[str, int] = {}
        for i, s in enumerate(domain):
            if s in seen:
                return f"{idx_vars[seen[s]]} == {idx_vars[i]}"
            seen[s] = i
        return None

    @staticmethod
    def _index_key(indices: list[str], domain: list[str], known: set[str]) -> str:
        """Return the dict-key expression for a variable reference (without the variable name).

        Used by the OR-Tools emitter to call ``var.get(key)`` separately from the
        variable name so the result can be guarded with ``if _v is not None``.
        """
        def _fmt(idx: str) -> str:
            return idx if idx in known else repr(idx)

        if len(domain) == 1:
            return _fmt(indices[0])
        idx_parts = ", ".join(_fmt(i) for i in indices[: len(domain)])
        return f"({idx_parts})"

    @staticmethod
    def _parse_over_item(item: str, index_map: dict[str, str]) -> tuple[str, str]:
        """Parse a single ``over`` entry, returning ``(set_name, loop_var)``.

        Supports the extended ``"SetName:alias"`` syntax to allow the same set
        to appear twice with different loop-variable names (e.g. when summing
        over Locations × Locations with distinct symbols ``l1`` and ``l2``).
        """
        if ":" in item:
            set_name, alias = item.split(":", 1)
            return set_name.strip(), alias.strip()
        return item, index_map[item]

    def _emit_expr(
        self,
        node: dict,
        index_map: dict[str, str],
        variables: dict,
        parameters: dict,
        extra_known: set[str] | None = None,
    ) -> str:
        """Emit a Python expression string (PuLP lpSum / plain Python for OR-Tools RHS)."""
        node_type = node.get("type")
        operation = node.get("operation")

        if node_type == "constant":
            return str(node["value"])

        known = set(index_map.values())
        if extra_known:
            known |= extra_known

        if node_type == "variable":
            name = node["name"]
            indices = node.get("indices", [])
            domain = variables.get(name, {}).get("domain", [])
            use_get = bool(variables.get(name, {}).get("exclude_diagonal", False))
            return self._var_ref(name, indices, domain, known, use_get=use_get)

        if node_type == "parameter":
            name = node["name"]
            indices = node.get("indices", [])
            domain = parameters.get(name, {}).get("domain", [])
            if not indices or not domain:
                return name
            if len(domain) == 1:
                return f"{name}[{indices[0]}]"
            idx_tuple = ", ".join(indices[: len(domain)])
            # Use .get() when the same set appears twice in the domain — diagonal keys
            # won't exist in the loaded dict (e.g. distance[('depot','depot')] missing),
            # and the paired variable will also be 0 for those indices.
            if len(set(domain)) < len(domain):
                return f"{name}.get(({idx_tuple}), 0.0)"
            return f"{name}[({idx_tuple})]"

        if node_type == "set_size":
            return f"len({node['set']})"

        if operation in ("sum", "subtract", "multiply"):
            left = self._emit_expr(node["left"], index_map, variables, parameters, extra_known)
            right = self._emit_expr(node["right"], index_map, variables, parameters, extra_known)
            if operation == "multiply":
                return f"{left} * {right}"
            op = "+" if operation == "sum" else "-"
            return f"({left} {op} {right})"

        if operation == "indexed_sum":
            over = node.get("over", [])
            alias_vars: set[str] = set()
            iter_parts: list[str] = []
            for item in over:
                set_name, loop_var = self._parse_over_item(item, index_map)
                iter_parts.append(f"for {loop_var} in {set_name}")
                alias_vars.add(loop_var)
            new_extra = (extra_known or set()) | alias_vars
            body = self._emit_expr(node["body"], index_map, variables, parameters, new_extra)
            iterators = " ".join(iter_parts)
            return f"pulp.lpSum({body} {iterators})"

        return "0"

    def _emit_pyomo_expr(
        self,
        node: dict,
        index_map: dict[str, str],
        variables: dict,
        parameters: dict,
        extra_known: set[str] | None = None,
    ) -> str:
        """Emit a Pyomo-compatible Python expression string.

        Differences from _emit_expr:
        - Variables are referenced as ``model.x[i, j]`` (no tuple, comma-separated)
        - indexed_sum uses ``sum(...)`` instead of ``pulp.lpSum(...)``
        """
        node_type = node.get("type")
        operation = node.get("operation")

        if node_type == "constant":
            return str(node["value"])

        known = set(index_map.values())
        if extra_known:
            known |= extra_known

        def _fmt(idx: str) -> str:
            return idx if idx in known else repr(idx)

        if node_type == "variable":
            name = node["name"]
            indices = node.get("indices", [])
            domain = variables.get(name, {}).get("domain", [])
            if not indices or not domain:
                return f"model.{name}"
            if len(domain) == 1:
                return f"model.{name}[{_fmt(indices[0])}]"
            idx_str = ", ".join(_fmt(i) for i in indices[: len(domain)])
            return f"model.{name}[{idx_str}]"

        if node_type == "parameter":
            name = node["name"]
            indices = node.get("indices", [])
            domain = parameters.get(name, {}).get("domain", [])
            if not indices or not domain:
                return name
            if len(domain) == 1:
                return f"{name}[{indices[0]}]"
            idx_tuple = ", ".join(indices[: len(domain)])
            # Use .get() when the same set appears twice in the domain.
            if len(set(domain)) < len(domain):
                return f"{name}.get(({idx_tuple}), 0.0)"
            return f"{name}[({idx_tuple})]"

        if node_type == "set_size":
            return f"len({node['set']})"

        if operation in ("sum", "subtract", "multiply"):
            left = self._emit_pyomo_expr(node["left"], index_map, variables, parameters, extra_known)
            right = self._emit_pyomo_expr(node["right"], index_map, variables, parameters, extra_known)
            if operation == "multiply":
                return f"{left} * {right}"
            op = "+" if operation == "sum" else "-"
            return f"({left} {op} {right})"

        if operation == "indexed_sum":
            over = node.get("over", [])
            alias_vars: set[str] = set()
            iter_parts: list[str] = []
            for item in over:
                set_name, loop_var = self._parse_over_item(item, index_map)
                iter_parts.append(f"for {loop_var} in {set_name}")
                alias_vars.add(loop_var)
            new_extra = (extra_known or set()) | alias_vars
            body = self._emit_pyomo_expr(node["body"], index_map, variables, parameters, new_extra)
            iterators = " ".join(iter_parts)
            return f"sum({body} {iterators})"

        return "0"

    def _emit_ortools_coefficients(
        self,
        node: dict,
        target: str,
        index_map: dict[str, str],
        variables: dict,
        parameters: dict,
        lines: list[str],
        indent: int,
        sign: int = 1,
        extra_known: set[str] | None = None,
    ) -> None:
        """Append OR-Tools SetCoefficient calls to *lines* for a linear expression node.

        *target* is the Python name of the OR-Tools objective or constraint object.
        *indent* is the current indentation level (1 = 4 spaces = inside solve()).
        *sign* is +1 or -1, accumulated through subtract nodes.
        *extra_known* carries loop-variable aliases from enclosing indexed_sum nodes.
        """
        pad = "    " * indent
        op = node.get("operation")
        ntype = node.get("type")

        if op == "indexed_sum":
            alias_vars: set[str] = set()
            for item in node["over"]:
                set_name, loop_var = self._parse_over_item(item, index_map)
                pad = "    " * indent
                lines.append(f"{pad}for {loop_var} in {set_name}:")
                indent += 1
                alias_vars.add(loop_var)
            new_extra = (extra_known or set()) | alias_vars
            self._emit_ortools_coefficients(
                node["body"], target, index_map, variables, parameters, lines, indent, sign, new_extra
            )
            return

        known = set(index_map.values()) | (extra_known or set())

        if ntype == "variable":
            name = node["name"]
            indices = node.get("indices", [])
            domain = variables.get(name, {}).get("domain", [])
            excl = bool(variables.get(name, {}).get("exclude_diagonal", False))
            var_ref = self._var_ref(name, indices, domain, known)
            coeff = "1.0" if sign == 1 else "-1.0"
            if excl:
                # Use .get() and guard: OR-Tools SetCoefficient needs an actual variable object
                guard_ref = self._var_ref(name, indices, domain, known)
                lines.append(f"{pad}_v = {name}.get({self._index_key(indices, domain, known)})")
                lines.append(f"{pad}if _v is not None: {target}.SetCoefficient(_v, {coeff})")
            else:
                lines.append(f"{pad}{target}.SetCoefficient({var_ref}, {coeff})")
            return

        if op == "multiply":
            left, right = node["left"], node["right"]
            # Identify which operand is the variable
            if right.get("type") == "variable":
                coeff_node, var_node = left, right
            else:
                coeff_node, var_node = right, left
            name = var_node["name"]
            indices = var_node.get("indices", [])
            domain = variables.get(name, {}).get("domain", [])
            excl = bool(variables.get(name, {}).get("exclude_diagonal", False))
            coeff_str = self._emit_expr(coeff_node, index_map, variables, parameters, extra_known)
            if sign == -1:
                coeff_str = f"-({coeff_str})"
            if excl:
                lines.append(f"{pad}_v = {name}.get({self._index_key(indices, domain, known)})")
                lines.append(f"{pad}if _v is not None: {target}.SetCoefficient(_v, {coeff_str})")
            else:
                var_ref = self._var_ref(name, indices, domain, known)
                lines.append(f"{pad}{target}.SetCoefficient({var_ref}, {coeff_str})")
            return

        if op == "sum":
            self._emit_ortools_coefficients(
                node["left"], target, index_map, variables, parameters, lines, indent, sign, extra_known
            )
            self._emit_ortools_coefficients(
                node["right"], target, index_map, variables, parameters, lines, indent, sign, extra_known
            )
            return

        if op == "subtract":
            self._emit_ortools_coefficients(
                node["left"], target, index_map, variables, parameters, lines, indent, sign, extra_known
            )
            self._emit_ortools_coefficients(
                node["right"], target, index_map, variables, parameters, lines, indent, -sign, extra_known
            )
            return

        lines.append(f"{pad}# TODO: unsupported expression node type={ntype!r} op={op!r}")

    # ------------------------------------------------------------------
    # PuLP backend
    # ------------------------------------------------------------------

    def _compile_pulp(self, ir: dict) -> str:
        sets = ir.get("sets", {})
        parameters = ir.get("parameters", {})
        variables = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        objective = ir.get("objective", {})
        sense = ir.get("sense", "minimize")
        problem_class = ir.get("problem_class", "Model")

        index_map: dict[str, str] = {n: m["index_symbol"] for n, m in sets.items()}
        set_column: dict[str, str | None] = {n: m.get("column") for n, m in sets.items()}

        lines: list[str] = [
            "import pulp",
            "",
            "",
            "def solve(data: dict, time_limit: int | None = None, show_solver_log: bool = False) -> dict:",
            "    # --- Load sets ---",
        ]
        lines += self._emit_set_loading(sets, set_column)
        lines.append("")
        lines.append("    # --- Load parameters ---")
        lines += self._emit_parameter_loading(parameters, set_column, index_map)

        lp_sense = "pulp.LpMinimize" if sense == "minimize" else "pulp.LpMaximize"
        lines += [
            "",
            "    # --- Build model ---",
            f"    prob = pulp.LpProblem({problem_class!r}, {lp_sense})",
            "",
            "    # --- Decision variables ---",
        ]

        cat_map = {
            "continuous": "pulp.LpContinuous",
            "integer": "pulp.LpInteger",
            "binary": "pulp.LpBinary",
        }
        for var_name, meta in variables.items():
            domain = meta.get("domain", [])
            cat = cat_map.get(meta.get("type", "continuous"), "pulp.LpContinuous")
            lb = meta.get("lower_bound")
            ub = meta.get("upper_bound")
            lb_str = str(lb) if lb is not None else "0"
            if ub is not None:
                ub_str = str(ub)
            elif meta.get("upper_bound_set"):
                ub_str = f"len({meta['upper_bound_set']})"
            else:
                ub_str = "None"
            excl = meta.get("exclude_diagonal", False)

            if not domain:
                lines.append(
                    f"    {var_name} = pulp.LpVariable({var_name!r}, "
                    f"lowBound={lb_str}, upBound={ub_str}, cat={cat})"
                )
            elif len(domain) == 1:
                lines.append(
                    f"    {var_name} = pulp.LpVariable.dicts("
                    f"{var_name!r}, {domain[0]}, lowBound={lb_str}, upBound={ub_str}, cat={cat})"
                )
            elif len(domain) == 2:
                s0, s1 = domain[0], domain[1]
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                guard = f" if {idx0} != {idx1}" if excl else ""
                lines.append(
                    f"    {var_name} = pulp.LpVariable.dicts("
                    f"{var_name!r}, [({idx0}, {idx1}) for {idx0} in {s0} for {idx1} in {s1}{guard}], "
                    f"lowBound={lb_str}, upBound={ub_str}, cat={cat})"
                )
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                iterators = " ".join(
                    f"for {iv} in {s}" for iv, s in zip(idx_vars, domain)
                )
                idx_tuple = "(" + ", ".join(idx_vars) + ")"
                guard = f" if {idx_vars[0]} != {idx_vars[1]}" if excl and len(idx_vars) >= 2 else ""
                lines.append(
                    f"    {var_name} = pulp.LpVariable.dicts("
                    f"{var_name!r}, [{idx_tuple} {iterators}{guard}], "
                    f"lowBound={lb_str}, upBound={ub_str}, cat={cat})"
                )

        lines.append("")
        lines.append("    # --- Objective ---")
        obj_expr = self._emit_expr(objective["expression"], index_map, variables, parameters)
        lines.append(f"    prob += {obj_expr}, 'objective'")

        lines.append("")
        lines.append("    # --- Constraints ---")
        for cname, cmeta in constraints.items():
            domain = cmeta.get("domain", [])
            sense_op = {"<=": "<=", ">=": ">=", "=": "=="}.get(cmeta.get("sense", "<="), "<=")
            domain_loop_vars = set(self._domain_idx_vars(domain, index_map)) if domain else set()
            lhs = self._emit_expr(cmeta["expression"], index_map, variables, parameters, extra_known=domain_loop_vars)
            rhs = self._emit_expr(cmeta["rhs"], index_map, variables, parameters, extra_known=domain_loop_vars)

            if not domain:
                lines.append(f"    prob += {lhs} {sense_op} {rhs}, {cname!r}")
            elif len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        prob += {lhs} {sense_op} {rhs}, f\"{cname}_{{{idx0}}}\"")
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                guard = self._constraint_diagonal_guard(domain, [idx0, idx1])
                if guard:
                    lines.append(f"            if {guard}: continue")
                lines.append(
                    f"            prob += {lhs} {sense_op} {rhs}, "
                    f"f\"{cname}_{{{idx0}}}_{{{idx1}}}\""
                )
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                name_parts = "\\x1f".join(f"{{{iv}}}" for iv in idx_vars)
                inner = "    " * (len(domain) + 1)
                guard = self._constraint_diagonal_guard(domain, idx_vars)
                if guard:
                    lines.append(f"{inner}if {guard}: continue")
                lines.append(
                    f"{inner}prob += {lhs} {sense_op} {rhs}, f\"{cname}_{name_parts}\""
                )

        lines += [
            "",
            "    # --- Solve ---",
            "    prob.writeLP('model.lp')",
            "    _cbc_kwargs = {'msg': 1 if show_solver_log else 0}",
            "    if time_limit is not None:",
            "        _cbc_kwargs['timeLimit'] = time_limit",
            "    prob.solve(pulp.PULP_CBC_CMD(**_cbc_kwargs))",
            "",
            "    _sol_status_map = {",
            "        pulp.constants.LpSolutionOptimal:         'optimal',",
            "        pulp.constants.LpSolutionIntegerFeasible: 'feasible',",
            "        pulp.constants.LpSolutionInfeasible:      'infeasible',",
            "        pulp.constants.LpSolutionUnbounded:       'unbounded',",
            "    }",
            "    result = {",
            "        'status': _sol_status_map.get(prob.sol_status, 'error'),",
            "        'objective_value': None,",
            "        'variables': {},",
            "        'variable_groups': [],",
            "    }",
            "    if prob.sol_status in (pulp.constants.LpSolutionOptimal, pulp.constants.LpSolutionIntegerFeasible):",
            "        result['objective_value'] = pulp.value(prob.objective)",
        ]

        for var_name, meta in variables.items():
            domain = meta.get("domain", [])
            excl = meta.get("exclude_diagonal", False)
            lines.append(f"    # extract {var_name}")
            if not domain:
                lines.append(
                    f"    result['variables'][{var_name!r}] = pulp.value({var_name})"
                )
            elif len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(
                    f"        result['variables'][f\"{var_name}\\x1f{{{idx0}}}\"] = "
                    f"pulp.value({var_name}[{idx0}])"
                )
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                if excl:
                    lines.append(f"            if {idx0} == {idx1}: continue")
                lines.append(
                    f"            result['variables'][f\"{var_name}\\x1f{{{idx0}}}\\x1f{{{idx1}}}\"] = "
                    f"pulp.value({var_name}[({idx0}, {idx1})])"
                )
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                inner = "    " * (len(domain) + 1)
                if excl and len(idx_vars) >= 2:
                    lines.append(f"{inner}if {idx_vars[0]} == {idx_vars[1]}: continue")
                idx_tuple = "(" + ", ".join(idx_vars) + ")"
                name_parts = "\\x1f".join(f"{{{iv}}}" for iv in idx_vars)
                lines.append(
                    f"{inner}result['variables'][f\"{var_name}\\x1f{name_parts}\"] = "
                    f"pulp.value({var_name}[{idx_tuple}])"
                )

        lines += self._emit_variable_groups(variables)
        lines.append("    return result")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Pyomo backend
    # ------------------------------------------------------------------

    def _compile_pyomo(self, ir: dict) -> str:
        sets = ir.get("sets", {})
        parameters = ir.get("parameters", {})
        variables = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        objective = ir.get("objective", {})
        sense = ir.get("sense", "minimize")
        problem_class = ir.get("problem_class", "Model")

        index_map: dict[str, str] = {n: m["index_symbol"] for n, m in sets.items()}
        set_column: dict[str, str | None] = {n: m.get("column") for n, m in sets.items()}

        lines: list[str] = [
            "import pyomo.environ as pyo",
            "",
            "",
            "def solve(data: dict, time_limit: int | None = None, show_solver_log: bool = False) -> dict:",
            "    # --- Load sets ---",
        ]
        lines += self._emit_set_loading(sets, set_column)
        lines.append("")
        lines.append("    # --- Load parameters ---")
        lines += self._emit_parameter_loading(parameters, set_column, index_map)

        pyo_sense = "pyo.minimize" if sense == "minimize" else "pyo.maximize"
        lines += [
            "",
            "    # --- Build model ---",
            f"    model = pyo.ConcreteModel(name={problem_class!r})",
            "",
            "    # --- Decision variables ---",
        ]

        for var_name, meta in variables.items():
            domain = meta.get("domain", [])
            vtype = meta.get("type", "continuous")
            lb = meta.get("lower_bound")
            ub = meta.get("upper_bound")
            lb_str = str(lb) if lb is not None else "0"
            if ub is not None:
                ub_str = str(ub)
            elif meta.get("upper_bound_set"):
                ub_str = f"len({meta['upper_bound_set']})"
            else:
                ub_str = "None"
            excl = meta.get("exclude_diagonal", False)

            if vtype == "binary":
                within = "pyo.Binary"
                bounds = ""
            elif vtype == "integer":
                within = "pyo.Integers"
                bounds = f", bounds=({lb_str}, {ub_str})"
            else:
                within = "pyo.Reals"
                bounds = f", bounds=({lb_str}, {ub_str})"

            if not domain:
                lines.append(
                    f"    model.{var_name} = pyo.Var(within={within}{bounds})"
                )
            elif len(domain) == 1:
                lines.append(
                    f"    model.{var_name} = pyo.Var({domain[0]}, within={within}{bounds})"
                )
            elif len(domain) == 2:
                s0, s1 = domain[0], domain[1]
                idx0, idx1 = index_map[s0], index_map[s1]
                if excl:
                    lines.append(
                        f"    model.{var_name} = pyo.Var("
                        f"[({idx0}, {idx1}) for {idx0} in {s0} for {idx1} in {s1} if {idx0} != {idx1}], "
                        f"within={within}{bounds})"
                    )
                else:
                    lines.append(
                        f"    model.{var_name} = pyo.Var({s0}, {s1}, within={within}{bounds})"
                    )
            else:
                idx_vars = [index_map[s] for s in domain]
                iterators = " ".join(f"for {iv} in {s}" for iv, s in zip(idx_vars, domain))
                idx_tuple = "(" + ", ".join(idx_vars) + ")"
                guard = f" if {idx_vars[0]} != {idx_vars[1]}" if excl and len(idx_vars) >= 2 else ""
                if excl:
                    lines.append(
                        f"    model.{var_name} = pyo.Var("
                        f"[{idx_tuple} {iterators}{guard}], within={within}{bounds})"
                    )
                else:
                    set_args = ", ".join(domain)
                    lines.append(
                        f"    model.{var_name} = pyo.Var({set_args}, within={within}{bounds})"
                    )

        lines.append("")
        lines.append("    # --- Objective ---")
        obj_expr = self._emit_pyomo_expr(
            objective["expression"], index_map, variables, parameters
        )
        lines.append(f"    model.obj = pyo.Objective(expr={obj_expr}, sense={pyo_sense})")

        lines.append("")
        lines.append("    # --- Constraints ---")
        for cname, cmeta in constraints.items():
            domain = cmeta.get("domain", [])
            sense_op = {"<=": "<=", ">=": ">=", "=": "=="}.get(cmeta.get("sense", "<="), "<=")
            domain_loop_vars = set(self._domain_idx_vars(domain, index_map)) if domain else set()
            lhs = self._emit_pyomo_expr(cmeta["expression"], index_map, variables, parameters, extra_known=domain_loop_vars)
            rhs = self._emit_pyomo_expr(cmeta["rhs"], index_map, variables, parameters, extra_known=domain_loop_vars)

            lines.append(f"    model.{cname} = pyo.ConstraintList()")
            if not domain:
                lines.append(f"    model.{cname}.add({lhs} {sense_op} {rhs})")
            elif len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        model.{cname}.add({lhs} {sense_op} {rhs})")
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                guard = self._constraint_diagonal_guard(domain, [idx0, idx1])
                if guard:
                    lines.append(f"            if {guard}: continue")
                lines.append(f"            model.{cname}.add({lhs} {sense_op} {rhs})")
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                inner = "    " * (len(domain) + 1)
                guard = self._constraint_diagonal_guard(domain, idx_vars)
                if guard:
                    lines.append(f"{inner}if {guard}: continue")
                lines.append(f"{inner}model.{cname}.add({lhs} {sense_op} {rhs})")

        lines += [
            "",
            "    # --- Solve ---",
            "    try:",
            "        model.write('model.lp', io_options={'symbolic_solver_labels': True})",
            "    except Exception:",
            "        try:",
            "            model.write('model.lp')",
            "        except Exception:",
            "            pass  # LP write is best-effort",
            "    _solver = None",
            "    for _sname in ['appsi_highs', 'glpk', 'cbc']:",
            "        _s = pyo.SolverFactory(_sname)",
            "        if _s.available(exception_flag=False):",
            "            _solver = _s",
            "            break",
            "    if _solver is None:",
            "        raise RuntimeError(",
            "            'No Pyomo solver found. Install HiGHS (pip install highspy), GLPK, or CBC.'",
            "        )",
            "    if time_limit is not None:",
            "        _sname_used = type(_solver).__name__.lower()",
            "        if 'highs' in _sname_used or 'appsi' in _sname_used:",
            "            _solver.options['time_limit'] = time_limit",
            "        elif 'glpk' in _sname_used:",
            "            _solver.options['tmlim'] = time_limit",
            "        else:  # cbc",
            "            _solver.options['sec'] = time_limit",
            "    _results = _solver.solve(model, tee=show_solver_log)",
            "",
            "    _tc = str(_results.solver.termination_condition).lower()",
            "    if 'optimal' in _tc:",
            "        _status = 'optimal'",
            "    elif 'feasible' in _tc:",
            "        _status = 'feasible'",
            "    elif 'infeasible' in _tc:",
            "        _status = 'infeasible'",
            "    elif 'unbounded' in _tc:",
            "        _status = 'unbounded'",
            "    else:",
            "        _status = 'error'",
            "    result = {",
            "        'status': _status,",
            "        'objective_value': None,",
            "        'variables': {},",
            "        'variable_groups': [],",
            "    }",
            "    if _status in ('optimal', 'feasible'):",
            "        result['objective_value'] = pyo.value(model.obj)",
        ]

        for var_name, meta in variables.items():
            domain = meta.get("domain", [])
            excl = meta.get("exclude_diagonal", False)
            lines.append(f"    # extract {var_name}")
            if not domain:
                lines.append(
                    f"    result['variables'][{var_name!r}] = pyo.value(model.{var_name})"
                )
            elif len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(
                    f"        result['variables'][f\"{var_name}\\x1f{{{idx0}}}\"] = "
                    f"pyo.value(model.{var_name}[{idx0}])"
                )
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                if excl:
                    lines.append(f"            if {idx0} == {idx1}: continue")
                lines.append(
                    f"            result['variables'][f\"{var_name}\\x1f{{{idx0}}}\\x1f{{{idx1}}}\"] = "
                    f"pyo.value(model.{var_name}[{idx0}, {idx1}])"
                )
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                inner = "    " * (len(domain) + 1)
                if excl and len(idx_vars) >= 2:
                    lines.append(f"{inner}if {idx_vars[0]} == {idx_vars[1]}: continue")
                idx_str = ", ".join(idx_vars)
                name_parts = "\\x1f".join(f"{{{iv}}}" for iv in idx_vars)
                lines.append(
                    f"{inner}result['variables'][f\"{var_name}\\x1f{name_parts}\"] = "
                    f"pyo.value(model.{var_name}[{idx_str}])"
                )

        lines += self._emit_variable_groups(variables)
        lines.append("    return result")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # OR-Tools backend
    # ------------------------------------------------------------------

    def _compile_ortools(self, ir: dict) -> str:
        sets = ir.get("sets", {})
        parameters = ir.get("parameters", {})
        variables = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        objective = ir.get("objective", {})
        sense = ir.get("sense", "minimize")
        problem_class = ir.get("problem_class", "Model")
        model_type = ir.get("model_type", "Linear Program")

        index_map: dict[str, str] = {n: m["index_symbol"] for n, m in sets.items()}
        set_column: dict[str, str | None] = {n: m.get("column") for n, m in sets.items()}

        is_mip = "Integer" in model_type or "Mixed" in model_type
        solver_type = "'SCIP'" if is_mip else "'GLOP'"

        lines: list[str] = [
            "from ortools.linear_solver import pywraplp",
            "",
            "",
            "def solve(data: dict, time_limit: int | None = None, show_solver_log: bool = False) -> dict:",
            "    # --- Load sets ---",
        ]
        lines += self._emit_set_loading(sets, set_column)
        lines.append("")
        lines.append("    # --- Load parameters ---")
        lines += self._emit_parameter_loading(parameters, set_column, index_map)

        lines += [
            "",
            "    # --- Build solver ---",
            f"    solver = pywraplp.Solver.CreateSolver({solver_type})",
            "    if not solver:",
            "        solver = pywraplp.Solver.CreateSolver('SCIP')",
            "    if not solver:",
            f'        raise RuntimeError("OR-Tools solver {solver_type} not available")',
            f"    solver.SetSolverSpecificParametersAsString('')",
            "",
            "    # --- Decision variables ---",
        ]

        for var_name, meta in variables.items():
            domain = meta.get("domain", [])
            vtype = meta.get("type", "continuous")
            lb = meta.get("lower_bound")
            ub = meta.get("upper_bound")
            lb_str = str(float(lb)) if lb is not None else "0.0"

            # Upper bound expression: solver.infinity() for continuous, int cap for integer
            if ub is not None:
                if vtype == "integer":
                    ub_str = str(int(ub))
                else:
                    ub_str = str(float(ub))
            elif vtype == "continuous":
                ub_str = "solver.infinity()"
            elif meta.get("upper_bound_set"):
                ub_str = f"len({meta['upper_bound_set']})"
            else:
                ub_str = "int(1e9)"

            if not domain:
                if vtype == "binary":
                    lines.append(f"    {var_name} = solver.BoolVar({var_name!r})")
                elif vtype == "integer":
                    lines.append(
                        f"    {var_name} = solver.IntVar({lb_str}, {ub_str}, {var_name!r})"
                    )
                else:
                    lines.append(
                        f"    {var_name} = solver.NumVar({lb_str}, {ub_str}, {var_name!r})"
                    )
                continue

            lines.append(f"    {var_name} = {{}}")
            if len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                if vtype == "binary":
                    lines.append(
                        f"        {var_name}[{idx0}] = solver.BoolVar(f'{var_name}_{{{idx0}}}')"
                    )
                elif vtype == "integer":
                    lines.append(
                        f"        {var_name}[{idx0}] = solver.IntVar("
                        f"{lb_str}, {ub_str}, f'{var_name}_{{{idx0}}}')"
                    )
                else:
                    lines.append(
                        f"        {var_name}[{idx0}] = solver.NumVar("
                        f"{lb_str}, {ub_str}, f'{var_name}_{{{idx0}}}')"
                    )
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                excl = meta.get("exclude_diagonal", False)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                if excl:
                    lines.append(f"            if {idx0} == {idx1}: continue")
                if vtype == "binary":
                    lines.append(
                        f"            {var_name}[({idx0}, {idx1})] = "
                        f"solver.BoolVar(f'{var_name}_{{{idx0}}}_{{{idx1}}}')"
                    )
                elif vtype == "integer":
                    lines.append(
                        f"            {var_name}[({idx0}, {idx1})] = solver.IntVar("
                        f"{lb_str}, {ub_str}, f'{var_name}_{{{idx0}}}_{{{idx1}}}')"
                    )
                else:
                    lines.append(
                        f"            {var_name}[({idx0}, {idx1})] = solver.NumVar("
                        f"{lb_str}, {ub_str}, f'{var_name}_{{{idx0}}}_{{{idx1}}}')"
                    )
            else:
                excl = meta.get("exclude_diagonal", False)
                idx_vars = [index_map[s] for s in domain]
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                # Emit diagonal guard as a continue statement inside the innermost loop
                if excl and len(idx_vars) >= 2:
                    skip_pad = "    " * (len(idx_vars) + 1)
                    lines.append(f"{skip_pad}if {idx_vars[0]} == {idx_vars[1]}: continue")
                idx_tuple = "(" + ", ".join(idx_vars) + ")"
                name_str = "_".join(f"{{{iv}}}" for iv in idx_vars)
                inner = "    " * (len(domain) + 1)
                if vtype == "binary":
                    lines.append(
                        f"{inner}{var_name}[{idx_tuple}] = solver.BoolVar(f'{var_name}_{name_str}')"
                    )
                elif vtype == "integer":
                    lines.append(
                        f"{inner}{var_name}[{idx_tuple}] = solver.IntVar("
                        f"{lb_str}, {ub_str}, f'{var_name}_{name_str}')"
                    )
                else:
                    lines.append(
                        f"{inner}{var_name}[{idx_tuple}] = solver.NumVar("
                        f"{lb_str}, {ub_str}, f'{var_name}_{name_str}')"
                    )

        # Objective
        lines += [
            "",
            "    # --- Objective ---",
            "    objective = solver.Objective()",
        ]
        self._emit_ortools_coefficients(
            objective["expression"], "objective", index_map, variables, parameters, lines, indent=1
        )
        if sense == "minimize":
            lines.append("    objective.SetMinimization()")
        else:
            lines.append("    objective.SetMaximization()")

        # Constraints
        lines.append("")
        lines.append("    # --- Constraints ---")
        for cname, cmeta in constraints.items():
            domain = cmeta.get("domain", [])
            sense_c = cmeta.get("sense", "<=")
            rhs_node = cmeta["rhs"]
            domain_loop_vars = set(self._domain_idx_vars(domain, index_map)) if domain else set()

            # Helper to emit the constraint body (ct declaration + SetCoefficient calls)
            # at a given indent level, with rhs already in scope as a Python expression.
            def _emit_ct_body(rhs_expr: str, ct_indent: int, name_expr: str, extra_known: set[str] | None = None) -> None:
                pad = "    " * ct_indent
                if sense_c == "<=":
                    lines.append(
                        f"{pad}ct = solver.Constraint(-solver.infinity(), "
                        f"float({rhs_expr}), {name_expr})"
                    )
                elif sense_c == ">=":
                    lines.append(
                        f"{pad}ct = solver.Constraint("
                        f"float({rhs_expr}), solver.infinity(), {name_expr})"
                    )
                else:  # "="
                    lines.append(
                        f"{pad}ct = solver.Constraint("
                        f"float({rhs_expr}), float({rhs_expr}), {name_expr})"
                    )
                self._emit_ortools_coefficients(
                    cmeta["expression"],
                    "ct",
                    index_map,
                    variables,
                    parameters,
                    lines,
                    ct_indent,
                    extra_known=extra_known,
                )

            if not domain:
                rhs_expr = self._emit_expr(rhs_node, index_map, variables, parameters)
                _emit_ct_body(rhs_expr, ct_indent=1, name_expr=repr(cname))
            elif len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                rhs_expr = self._emit_expr(rhs_node, index_map, variables, parameters, extra_known=domain_loop_vars)
                _emit_ct_body(rhs_expr, ct_indent=2, name_expr=f"f\"{cname}_{{{idx0}}}\"", extra_known=domain_loop_vars)
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                guard = self._constraint_diagonal_guard(domain, [idx0, idx1])
                if guard:
                    lines.append(f"            if {guard}: continue")
                rhs_expr = self._emit_expr(rhs_node, index_map, variables, parameters, extra_known=domain_loop_vars)
                _emit_ct_body(
                    rhs_expr,
                    ct_indent=3,
                    name_expr=f"f\"{cname}_{{{idx0}}}_{{{idx1}}}\"",
                    extra_known=domain_loop_vars,
                )
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                name_parts = "\\x1f".join(f"{{{iv}}}" for iv in idx_vars)
                guard = self._constraint_diagonal_guard(domain, idx_vars)
                if guard:
                    inner_pad = "    " * (len(domain) + 1)
                    lines.append(f"{inner_pad}if {guard}: continue")
                rhs_expr = self._emit_expr(rhs_node, index_map, variables, parameters, extra_known=domain_loop_vars)
                _emit_ct_body(
                    rhs_expr,
                    ct_indent=len(domain) + 1,
                    name_expr=f"f\"{cname}_{name_parts}\"",
                    extra_known=domain_loop_vars,
                )

        # LP export + solve + result
        lines += [
            "",
            "    # --- Solve ---",
            "    try:",
            "        with open('model.lp', 'w') as _lp_f:",
            "            _lp_f.write(solver.ExportModelAsLpFormat(False))",
            "    except Exception:",
            "        pass  # LP export is best-effort",
            "    if show_solver_log:",
            "        solver.EnableOutput()",
            "    else:",
            "        solver.SuppressOutput()",
            "    if time_limit is not None:",
            "        solver.set_time_limit(time_limit * 1000)  # OR-Tools expects milliseconds",
            "    _status_int = solver.Solve()",
            "    _status_map = {",
            "        pywraplp.Solver.OPTIMAL: 'optimal',",
            "        pywraplp.Solver.FEASIBLE: 'feasible',",
            "        pywraplp.Solver.INFEASIBLE: 'infeasible',",
            "        pywraplp.Solver.UNBOUNDED: 'unbounded',",
            "    }",
            "    result = {",
            "        'status': _status_map.get(_status_int, 'error'),",
            "        'objective_value': None,",
            "        'variables': {},",
            "        'variable_groups': [],",
            "    }",
            "    if _status_int in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):",
            "        result['objective_value'] = solver.Objective().Value()",
        ]

        for var_name, meta in variables.items():
            domain = meta.get("domain", [])
            excl = meta.get("exclude_diagonal", False)
            lines.append(f"    # extract {var_name}")
            if not domain:
                lines.append(
                    f"    result['variables'][{var_name!r}] = {var_name}.solution_value()"
                )
            elif len(domain) == 1:
                idx0 = index_map[domain[0]]
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(
                    f"        result['variables'][f\"{var_name}\\x1f{{{idx0}}}\"] = "
                    f"{var_name}[{idx0}].solution_value()"
                )
            elif len(domain) == 2:
                idx0, idx1 = self._domain_idx_vars(domain, index_map)
                lines.append(f"    for {idx0} in {domain[0]}:")
                lines.append(f"        for {idx1} in {domain[1]}:")
                if excl:
                    lines.append(f"            if {idx0} == {idx1}: continue")
                lines.append(
                    f"            result['variables'][f\"{var_name}\\x1f{{{idx0}}}\\x1f{{{idx1}}}\"] = "
                    f"{var_name}[({idx0}, {idx1})].solution_value()"
                )
            else:
                idx_vars = self._domain_idx_vars(domain, index_map)
                for k, (iv, s) in enumerate(zip(idx_vars, domain)):
                    lines.append(f"    {'    ' * k}for {iv} in {s}:")
                inner = "    " * (len(domain) + 1)
                if excl and len(idx_vars) >= 2:
                    lines.append(f"{inner}if {idx_vars[0]} == {idx_vars[1]}: continue")
                idx_tuple = "(" + ", ".join(idx_vars) + ")"
                name_parts = "\\x1f".join(f"{{{iv}}}" for iv in idx_vars)
                lines.append(
                    f"{inner}result['variables'][f\"{var_name}\\x1f{name_parts}\"] = "
                    f"{var_name}[{idx_tuple}].solution_value()"
                )

        lines += self._emit_variable_groups(variables)
        lines.append("    return result")
        return "\n".join(lines) + "\n"
