# IR v2 Schema — Complete Reference

This is the **definitive reference** for OR-Copilot's Intermediate Representation (IR) v2.0. Both LLMs (when generating IR) and humans (when writing, debugging, or validating IR) should use this document as the single source of truth.

## Overview

The IR is a solver-agnostic JSON document that fully describes an optimization problem. It is the universal exchange format between:
- **LLM → Compiler**: LLMs generate IR from natural language descriptions
- **Compiler → Solver**: The deterministic compiler emits solver-specific code from IR
- **Human → System**: Users can write, inspect, and edit IR manually

### IR in the Pipeline

```
Natural Language → [LLM Extraction] → IR v2 JSON → [Compiler] → Solver Code
```

## Schema Version

- **schema_version**: `"2.0"` (string, required)

## Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | `string` | Yes | Always `"2.0"` |
| `metadata` | object | No | Traceability and audit info |
| `problem_class` | `string` | Yes | CoE-style OR problem type (e.g., `"transportation"`) |
| `problem_type` | `string` | Yes | Mathematical type: `"LP"`, `"MILP"`, `"MINLP"`, `"CP"`, `"combinatorial"` |
| `model_type` | `string` | Yes | Legacy alias for `problem_type` (for backward compat) |
| `sense` | `string` | Yes | `"minimize"` or `"maximize"` |
| `description` | `string` | No | Human-readable problem summary |
| `sets` | object | Yes | Index sets (keys are set names) |
| `parameters` | object | Yes | Input data parameters (keys are param names) |
| `variables` | object | Yes | Decision variables (keys are variable names) |
| `constraints` | object | Yes | Constraints (keys are constraint names) |
| `objective` | object | Yes | Objective function definition |

### Metadata (optional)

```json
{
  "metadata": {
    "generated_by": "or-copilot-v2",
    "timestamp": "2026-06-22T10:00:00",
    "assumptions": ["Non-negativity of all variables is assumed"],
    "known_limitations": ["Sparse routes not pre-validated"]
  }
}
```

---

## Sets

Each set defines an index dimension for parameters, variables, and constraints.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `index_symbol` | `string` | Yes | — | Single-letter loop variable, e.g. `"i"`, `"j"`, `"t"` |
| `size` | `integer` | No* | — | Explicit size (number of members) |
| `source` | `string` | No* | — | CSV filename that contains members |
| `column` | `string` | No* | — | Column name in the source CSV |
| `size_source` | `string` | No | — | CSV from which to derive size |
| `size_column` | `string` | No | — | Column in size_source CSV |
| `filter_column` | `string` | No | — | CSV column to filter on |
| `filter_value` | `string` | No | — | Value to match in filter_column |
| `ordered` | `boolean` | No | `false` | Whether this set has meaningful ordering |
| `members` | `list` | No | — | Explicit list of members (NL2OR mode) |
| `domain_type` | `string` | No | — | `"discrete"`, `"continuous"`, `"temporal"`, `"categorical"` |

\* At least one of `size`, `source`, `size_source`, or `members` must be provided.

### Set Loading Patterns

**Pattern 1: From CSV column**
```json
"Warehouses": {
  "index_symbol": "i",
  "source": "sets.csv",
  "column": "element",
  "filter_column": "set_name",
  "filter_value": "warehouses"
}
```
→ Compiler emits: `Warehouses = list(dict.fromkeys(str(row['element']) for row in data['sets'] if str(row['set_name']) == 'warehouses'))`

**Pattern 2: From range**
```json
"Periods": {
  "index_symbol": "t",
  "size": 12
}
```
→ `Periods = list(range(12))`

**Pattern 3: From parameter**
```json
"Products": {
  "index_symbol": "p",
  "size_source": "bigM",
  "size_column": "num_products"
}
```
→ `Products = list(range(int(float(data['bigM'][0]['num_products']))))`

**Pattern 4: Explicit members**
```json
"Workers": {
  "index_symbol": "w",
  "members": ["Alice", "Bob", "Carol"]
}
```

---

## Parameters

Each parameter defines an input data element indexed over zero or more sets.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `domain` | `list[string]` | Yes | — | Set names this parameter is indexed over (empty list = scalar) |
| `type` | `string` | Yes | — | `"float"`, `"integer"`, `"string"`, `"boolean"` |
| `source` | `string` | No | — | CSV filename containing values |
| `column` | `string` | No | — | CSV column holding this parameter's value. Defaults to param name. |
| `index_columns` | `list[string]` | No | — | CSV columns that form the key (overrides set column lookup) |
| `missing_default` | `string` | No | `"zero"` | Handling for missing rows: `"zero"` → 0.0, `"inf"` → ∞ |
| `optional` | `boolean` | No | `false` | When true, missing source file loads as empty dict |
| `description` | `string` | No | — | Human-readable explanation |
| `unit` | `string` | No | — | Physical unit, e.g. `"USD"`, `"kg"`, `"hours"` |
| `default_value` | any | No | — | Default when data is absent |

### Examples

**Scalar parameter:**
```json
"num_workers": {
  "domain": [],
  "type": "integer",
  "source": "config.csv",
  "column": "num_workers",
  "missing_default": "zero"
}
```

**1D indexed parameter:**
```json
"demand_i": {
  "domain": ["Customers"],
  "type": "float",
  "source": "demand.csv",
  "column": "demand",
  "index_columns": ["customer_id"],
  "missing_default": "zero"
}
```
→ Compiler emits: `demand_i = {}` and `demand_i[_key] = float(row.get('demand')) if row.get('demand') is not None else 0.0`

**2D sparse parameter:**
```json
"transport_cost_ij": {
  "domain": ["Warehouses", "Customers"],
  "type": "float",
  "source": "transport_cost.csv",
  "index_columns": ["warehouse_id", "customer_id"],
  "column": "unit_cost",
  "missing_default": "inf"
}
```
→ Compiler emits `.get()` pattern with `float('inf')` default

---

## Variables

Each variable defines a decision to be optimized.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | `string` | Yes | — | What this variable represents |
| `label` | `string` | No | variable name | Short slug for output files (e.g. `"shipments"`) |
| `domain` | `list[string]` | Yes | — | Sets this variable is indexed over |
| `type` | `string` | Yes | — | `"continuous"`, `"integer"`, `"binary"` |
| `lower_bound` | `float` | No | `0.0` | Lower bound value |
| `upper_bound` | `float` | No | solver default | Upper bound (omitted = unbounded) |
| `upper_bound_set` | `string` | No | — | Set whose size provides the upper bound |
| `exclude_diagonal` | `boolean` | No | `false` | Exclude (i,i) keys when domain repeats a set |
| `domain_filter` | `string` | No | — | Parameter name to use for sparse variable creation |
| `semantic_role` | `string` | No | — | `"flow"`, `"inventory"`, `"assignment"`, `"production"`, `"selection"` |
| `sos_weights` | `list[float]` | No | — | Weights for SOS1/SOS2 variables (OptiMUS) |
| `indicator_trigger` | `string` | No | — | Trigger variable name for indicator variables (OptiMUS) |

### Variable Type Matrix

| Type | Gurobi | PuLP | OR-Tools |
|---|---|---|---|
| `"continuous"` | `GRB.CONTINUOUS` | `LpContinuous` | `model.NewIntVar` with lb/ub |
| `"integer"` | `GRB.INTEGER` | `LpInteger` | `model.NewIntVar` |
| `"binary"` | `GRB.BINARY` | `LpBinary` | `model.NewBoolVar` |

### Examples

**Scalar variable:**
```json
"total_cost": {
  "description": "Total transportation cost",
  "domain": [],
  "type": "continuous",
  "lower_bound": 0.0
}
```

**1D indexed variable:**
```json
"shipment_ij": {
  "description": "Units shipped from warehouse i to customer j",
  "label": "shipments",
  "domain": ["Warehouses", "Customers"],
  "type": "continuous",
  "lower_bound": 0.0
}
```

**Sparse variable (only valid routes):**
```json
"shipment2_ij": {
  "description": "Units shipped from DC to customer on valid routes",
  "domain": ["DistributionCenters", "Customers"],
  "type": "continuous",
  "lower_bound": 0.0,
  "domain_filter": "transport_cost_dc_to_cust"
}
```

---

## Constraints

Each constraint defines a restriction on the decision variables.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `domain` | `list[string]` | Yes | — | Sets this constraint is indexed over (empty = scalar) |
| `expression` | object | Yes | — | Expression tree for the LHS |
| `sense` | `string` | Yes | — | `"<="`, `">="`, `"="` |
| `rhs` | object | Yes | — | Expression tree for the RHS |
| `sparse_filter` | `string` | No | — | Parameter to use for sparse constraint filtering |
| `name` | `string` | No | — | Human-readable name for debugging |
| `type` | `string` | No | `"linear"` | `"linear"`, `"quadratic"`, `"logical"`, `"big_m"`, `"indicator"` |
| `technique` | `string` | No | — | Solving technique used |
| `description` | `string` | No | — | Natural language description |
| `derived_from` | `string` | No | — | Original problem text excerpt |
| `connection_graph_id` | `string` | No | — | OptiMUS CG reference |

### Expression Tree Node Types

The `expression` and `rhs` fields use a tree structure with these node types:

| Node Type | Fields | Example |
|---|---|---|
| `constant` | `value` (float) | `{"type": "constant", "value": 100}` |
| `variable` | `name`, `indices` (list) | `{"type": "variable", "name": "x", "indices": ["i"]}` |
| `parameter` | `name`, `indices` (list) | `{"type": "parameter", "name": "demand", "indices": ["i"]}` |
| `set_size` | `set` (string) | `{"type": "set_size", "set": "Products"}` |
| `indexed_sum` | `over` (list), `body` (node) | `{"type": "indexed_sum", "over": ["Products:i"], "body": ...}` |
| `sum` / `subtract` / `multiply` | `left` (node), `right` (node) | Binary operations |

### Examples

**Simple scalar constraint:**
```json
"budget_limit": {
  "domain": [],
  "expression": {"type": "variable", "name": "total_cost", "indices": []},
  "sense": "<=",
  "rhs": {"type": "constant", "value": 10000},
  "description": "Total cost must not exceed budget"
}
```

**Indexed constraint with summation:**
```json
"demand_satisfaction": {
  "domain": ["Customers"],
  "expression": {
    "type": "indexed_sum",
    "over": ["Warehouses:i"],
    "body": {"type": "variable", "name": "shipment_ij", "indices": ["i", "j"]}
  },
  "sense": ">=",
  "rhs": {"type": "parameter", "name": "demand_j", "indices": ["j"]}
}
```

---

## Objective

| Field | Type | Required | Description |
|---|---|---|---|
| `sense` | `string` | Yes | `"minimize"` or `"maximize"` |
| `expression` | object | Yes | Expression tree (same node types as constraints) |
| `description` | `string` | No | Natural language description |

### Multi-term objectives

The compiler supports multi-term objectives via `sum`/`subtract` operations at the top level:

```json
"objective": {
  "sense": "minimize",
  "expression": {
    "type": "sum",
    "left": {
      "type": "indexed_sum",
      "over": ["Warehouses:i", "Customers:j"],
      "body": {
        "type": "multiply",
        "left": {"type": "parameter", "name": "cost_ij", "indices": ["i", "j"]},
        "right": {"type": "variable", "name": "shipment_ij", "indices": ["i", "j"]}
      }
    },
    "right": {
      "type": "indexed_sum",
      "over": ["Warehouses:i"],
      "body": {
        "type": "multiply",
        "left": {"type": "parameter", "name": "fixed_cost_i", "indices": ["i"]},
        "right": {"type": "variable", "name": "open_i", "indices": ["i"]}
      }
    }
  }
}
```

---

## Connection Graph (v2 only)

Tracks which parameters and variables appear in each constraint. Used by OptiMUS-style context management to keep LLM prompts focused.

```json
"connection_graph": {
  "parameter_to_clauses": {"demand_j": ["demand_satisfaction"]},
  "variable_to_clauses": {"shipment_ij": ["demand_satisfaction"]},
  "clause_dependencies": {}
}
```

---

## Complete Example: 3-Worker Assignment Problem

```json
{
  "schema_version": "2.0",
  "metadata": {
    "generated_by": "or-copilot-v2",
    "timestamp": "2026-06-22T10:00:00"
  },
  "problem_class": "assignment",
  "problem_type": "MILP",
  "model_type": "MILP",
  "sense": "minimize",
  "description": "Assign 3 workers to 3 tasks at minimum total cost",

  "sets": {
    "Workers": {"index_symbol": "i", "members": ["Alice", "Bob", "Carol"]},
    "Tasks": {"index_symbol": "j", "members": ["task_1", "task_2", "task_3"]}
  },

  "parameters": {
    "cost_ij": {
      "domain": ["Workers", "Tasks"], "type": "float",
      "source": "costs.csv", "index_columns": ["worker", "task"],
      "column": "cost", "missing_default": "inf"
    }
  },

  "variables": {
    "x_ij": {
      "description": "1 if worker i is assigned to task j, 0 otherwise",
      "label": "assignments",
      "domain": ["Workers", "Tasks"],
      "type": "binary",
      "lower_bound": 0.0,
      "upper_bound": 1.0
    }
  },

  "constraints": {
    "each_task": {
      "domain": ["Tasks"],
      "expression": {
        "type": "indexed_sum", "over": ["Workers:i"],
        "body": {"type": "variable", "name": "x_ij", "indices": ["i", "j"]}
      },
      "sense": "=", "rhs": {"type": "constant", "value": 1},
      "description": "Each task must be assigned exactly one worker"
    },
    "each_worker": {
      "domain": ["Workers"],
      "expression": {
        "type": "indexed_sum", "over": ["Tasks:j"],
        "body": {"type": "variable", "name": "x_ij", "indices": ["i", "j"]}
      },
      "sense": "<=", "rhs": {"type": "constant", "value": 1},
      "description": "Each worker handles at most one task"
    }
  },

  "objective": {
    "sense": "minimize",
    "expression": {
      "type": "indexed_sum",
      "over": ["Workers:i", "Tasks:j"],
      "body": {
        "type": "multiply",
        "left": {"type": "parameter", "name": "cost_ij", "indices": ["i", "j"]},
        "right": {"type": "variable", "name": "x_ij", "indices": ["i", "j"]}
      }
    },
    "description": "Minimize total assignment cost"
  }
}
```

---

## Validator Rules

The IR validator (`orpilot/codegen/ir_validator.py`) checks 18+ semantic rules. Key rules include:

| Rule | Check | Error Message |
|---|---|---|
| E001 | Every set has index_symbol | `Set 'X' missing required field 'index_symbol'` |
| E002 | Parameter domain sets exist as IR sets | `Parameter 'X' references undefined set 'Y'` |
| E003 | Variable domain sets exist | `Variable 'X' domain includes undefined set 'Y'` |
| E004 | Expression variable names are declared | `Expression references undeclared variable 'X'` |
| E005 | Expression parameter names are declared | `Expression references undeclared parameter 'X'` |
| E006 | Constraint sense is valid | `Constraint 'X' has invalid sense: 'Y'` |
| E007 | Objective sense is valid | `Objective sense must be 'minimize' or 'maximize'` |

## See Also

- [Writing IR for LLMs](writing-ir.md) — How LLMs should generate IR (common mistakes, templates)
- [Compiler Architecture](../architecture/compiler-internals.md) — How the compiler works internally
- [API Reference: IR Model](../api/ir-model.md) — Pydantic model API
