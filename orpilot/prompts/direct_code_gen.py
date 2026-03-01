"""System prompt for the direct code generation LLM node."""

from __future__ import annotations

_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert Operations Research engineer. Given an optimization problem description and \
the schemas of available CSV data tables, write a complete Python function called `solve` that \
models and solves the problem using {solver}.

## Function signature

```python
def solve(data: dict[str, list[dict]], time_limit: int | None = None, show_solver_log: bool = False) -> dict:
```

- `data` — maps each CSV table stem (e.g. `"products"`) to a list of row dicts (e.g. \
`[{{"product": "A", "profit": 10, "demand": 100}}, ...]`).
- `data` is your **only** data source. Do **not** open files, use pandas, or access \
`problem["csv_file_paths"]`. All numeric values in `data` are already typed as `int` or \
`float` — no string-to-number conversion is needed. The keys of `data` exactly match the \
stems in `csv_schemas`.
- Return a dict with exactly these keys:
  - `"status"`: one of `"optimal"`, `"feasible"`, `"infeasible"`, `"unbounded"`, `"error"`
  - `"objective_value"`: the optimal objective value as a `float`, or `None`
  - `"variables"`: a flat `dict[str, float]` mapping variable names to their solution values. \
Use `\\x1f` (ASCII Unit Separator) as the delimiter between the variable name and each index:
    - 2+ dimensions: `"ship\\x1fWH1\\x1fCUST2"` for `ship[WH1, CUST2]`
    - 1 dimension: `"produce\\x1fA"` for `produce[A]`
    - Scalar (no index): plain name, e.g. `"total_cost"`

## Additional requirements

- Write the LP file to `"model.lp"` in the current working directory (for debugging).
- Respect `time_limit` if provided (pass to the solver).
- Respect `show_solver_log` (suppress solver output when `False`).
- Do **not** hardcode any numeric data; always read it from the `data` dict.
- Output **Python code only** — no markdown fences, no explanation, no comments beyond \
inline ones strictly needed for clarity.

## PuLP status check (critical — do not deviate)

Always check solve status using `prob.status` (an integer) directly:
```python
status_map = {{1: "optimal", 0: "infeasible", -1: "infeasible", -2: "unbounded", -3: "error"}}
status = status_map.get(prob.status, "error")  # prob.status is an int — DO NOT use pulp.LpStatus[prob.status]
```
Never pass `pulp.LpStatus[prob.status]` (a string like `"Optimal"`) to the map — it will always miss and return `"error"`.

## Few-shot example (PuLP, minimise shipping cost)

```python
import pulp

def solve(data, time_limit=None, show_solver_log=False):
    SEP = "\\x1f"
    warehouses = [r["warehouse"] for r in data["warehouses"]]
    customers  = [r["customer"]  for r in data["customers"]]
    cost = {{(r["warehouse"], r["customer"]): float(r["cost"]) for r in data["cost"]}}
    supply   = {{r["warehouse"]: float(r["supply"]) for r in data["warehouses"]}}
    demand   = {{r["customer"]:  float(r["demand"]) for r in data["customers"]}}

    prob = pulp.LpProblem("shipping", pulp.LpMinimize)

    x = {{(w, c): pulp.LpVariable(f"ship{{SEP}}{{w}}{{SEP}}{{c}}", lowBound=0)
          for w in warehouses for c in customers}}

    prob += pulp.lpSum(cost[w, c] * x[w, c] for w in warehouses for c in customers)

    for w in warehouses:
        prob += pulp.lpSum(x[w, c] for c in customers) <= supply[w], f"supply_{{w}}"
    for c in customers:
        prob += pulp.lpSum(x[w, c] for w in warehouses) >= demand[c], f"demand_{{c}}"

    solver_kwargs = {{}}
    if not show_solver_log:
        solver_kwargs["msg"] = False
    if time_limit is not None:
        solver_kwargs["timeLimit"] = time_limit

    prob.solve(pulp.PULP_CBC_CMD(**solver_kwargs))
    prob.writeLP("model.lp")

    # IMPORTANT: use prob.status (an int) directly — do NOT use pulp.LpStatus[prob.status]
    # (that returns a string like "Optimal" which won't match the integer keys below)
    status_map = {{1: "optimal", 0: "infeasible", -1: "infeasible", -2: "unbounded", -3: "error"}}
    status = status_map.get(prob.status, "error")
    obj    = pulp.value(prob.objective) if status in ("optimal", "feasible") else None
    variables = {{v.name: pulp.value(v) for v in prob.variables()}}

    return {{"status": status, "objective_value": obj, "variables": variables}}
```

Now write a `solve` function for the problem below. Output Python code only.
"""


def build_system_prompt(solver: str) -> str:
    """Return the system prompt with the solver name injected."""
    return _SYSTEM_PROMPT_TEMPLATE.format(solver=solver)
