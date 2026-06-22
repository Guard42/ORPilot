# Writing IR — Guide for LLMs

This guide is written **for LLMs** that generate OR-Copilot IR v2 JSON from natural language problem descriptions. It covers the IR structure, common mistakes, domain-specific templates, and validation rules.

> **Human readers**: This document doubles as an IR authoring reference. The same rules and templates apply whether you're writing IR by hand or inspecting LLM-generated IR.

## The IR Contract

When you generate IR, you are writing a **formal contract** that the deterministic compiler interprets to produce solver code. The contract has 5 required components:

```
Sets → Parameters → Variables → Constraints → Objective
```

**Key principle**: The IR must be **complete and self-contained**. Every reference must be resolvable. No guessing allowed.

---

## Common Mistakes and Fixes

### Mistake 1: Undefined Set in Domain

❌ **Bad**:
```json
"variables": {
  "shipment_ij": {
    "domain": ["Warehouses", "Customers"],
    ...
  }
}
// But "Warehouses" is not in "sets"!
```

✅ **Good**: Always define every set referenced in parameters, variables, and constraints.
```json
"sets": {
  "Warehouses": {"index_symbol": "i", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "warehouses"},
  "Customers": {"index_symbol": "j", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "customers"}
}
```

### Mistake 2: Index Variable Mismatch

❌ **Bad**:
```json
"constraints": {
  "demand": {
    "domain": ["Customers"],
    "expression": {
      "type": "indexed_sum",
      "over": ["Warehouses:i"],      // Uses "i"
      "body": {"type": "variable", "name": "x", "indices": ["i", "k"]}  // "k" is undefined here!
    },
    ...
  }
}
```

✅ **Good**: Index variables in `over` must match indices in the body, and body indices must match domain order.
```json
"expression": {
  "type": "indexed_sum",
  "over": ["Warehouses:i"],
  "body": {"type": "variable", "name": "shipment_ij", "indices": ["i", "j"]}
}
```
→ "i" is defined by the `over` clause, "j" by the constraint's domain `["Customers"]`.

### Mistake 3: Missing `missing_default` for Sparse Data

❌ **Bad**:
```json
"transport_cost_ij": {
  "domain": ["Warehouses", "Customers"],
  "type": "float",
  "source": "transport_cost.csv",
  "index_columns": ["warehouse_id", "customer_id"],
  "column": "unit_cost"
  // Missing missing_default!
}
```
→ If some (warehouse, customer) pairs are absent from the CSV, accessing `transport_cost_ij[(key1, key2)]` will KeyError.

✅ **Good**: Always specify `missing_default` for sparse tables.
```json
"missing_default": "inf"  // Route doesn't exist → infinite cost
// or
"missing_default": "zero"  // No demand → zero
```

### Mistake 4: Wrong Sense in Constraint

❌ **Bad**:
```json
"sense": "="   // The compiler only accepts "=", not "=="
```

✅ **Good**:
```json
"sense": "<=", "sense": ">=", "sense": "="
```

### Mistake 5: `:alias` Suffix Leaking from Indexed Sum

❌ **Bad**:
```json
"variables": {
  "x_i": {
    "domain": ["Locations:l"]   // Wrong! :alias only belongs in indexed_sum.over
  }
}
```

✅ **Good**: Domain fields should only contain plain set names.
```json
"domain": ["Locations"]
```

---

## Domain-Specific IR Templates

### Template 1: Transportation / Network Flow

```json
{
  "schema_version": "2.0",
  "problem_class": "transportation",
  "problem_type": "LP",
  "sense": "minimize",
  "sets": {
    "Sources": {"index_symbol": "i", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "sources"},
    "Destinations": {"index_symbol": "j", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "destinations"}
  },
  "parameters": {
    "supply_i": {"domain": ["Sources"], "type": "float", "source": "supply.csv", "column": "supply", "index_columns": ["source_id"]},
    "demand_j": {"domain": ["Destinations"], "type": "float", "source": "demand.csv", "column": "demand", "index_columns": ["dest_id"]},
    "cost_ij": {"domain": ["Sources", "Destinations"], "type": "float", "source": "cost.csv", "index_columns": ["source_id", "dest_id"], "column": "unit_cost", "missing_default": "inf"}
  },
  "variables": {
    "flow_ij": {"description": "Units shipped from i to j", "domain": ["Sources", "Destinations"], "type": "continuous", "lower_bound": 0.0}
  },
  "constraints": {
    "supply_limit": {
      "domain": ["Sources"],
      "expression": {"type": "indexed_sum", "over": ["Destinations:j"], "body": {"type": "variable", "name": "flow_ij", "indices": ["i", "j"]}},
      "sense": "<=",
      "rhs": {"type": "parameter", "name": "supply_i", "indices": ["i"]}
    },
    "demand_met": {
      "domain": ["Destinations"],
      "expression": {"type": "indexed_sum", "over": ["Sources:i"], "body": {"type": "variable", "name": "flow_ij", "indices": ["i", "j"]}},
      "sense": "=",
      "rhs": {"type": "parameter", "name": "demand_j", "indices": ["j"]}
    }
  },
  "objective": {
    "sense": "minimize",
    "expression": {
      "type": "indexed_sum", "over": ["Sources:i", "Destinations:j"],
      "body": {"type": "multiply", "left": {"type": "parameter", "name": "cost_ij", "indices": ["i", "j"]}, "right": {"type": "variable", "name": "flow_ij", "indices": ["i", "j"]}}
    }
  }
}
```

### Template 2: Assignment / Matching

```json
{
  "schema_version": "2.0",
  "problem_class": "assignment",
  "problem_type": "MILP",
  "sense": "minimize",
  "sets": {
    "Workers": {"index_symbol": "i", "members": ["W1", "W2", "W3"]},
    "Tasks": {"index_symbol": "j", "members": ["T1", "T2", "T3"]}
  },
  "parameters": {
    "cost_ij": {"domain": ["Workers", "Tasks"], "type": "float", "source": "costs.csv", "index_columns": ["worker", "task"], "column": "cost"}
  },
  "variables": {
    "assign_ij": {"description": "1 if worker i assigned to task j", "domain": ["Workers", "Tasks"], "type": "binary", "lower_bound": 0.0, "upper_bound": 1.0}
  },
  "constraints": {
    "task_covered": {"domain": ["Tasks"], "expression": {"type": "indexed_sum", "over": ["Workers:i"], "body": {"type": "variable", "name": "assign_ij", "indices": ["i", "j"]}}, "sense": "=", "rhs": {"type": "constant", "value": 1}},
    "worker_limit": {"domain": ["Workers"], "expression": {"type": "indexed_sum", "over": ["Tasks:j"], "body": {"type": "variable", "name": "assign_ij", "indices": ["i", "j"]}}, "sense": "<=", "rhs": {"type": "constant", "value": 1}}
  },
  "objective": {
    "sense": "minimize",
    "expression": {"type": "indexed_sum", "over": ["Workers:i", "Tasks:j"], "body": {"type": "multiply", "left": {"type": "parameter", "name": "cost_ij", "indices": ["i", "j"]}, "right": {"type": "variable", "name": "assign_ij", "indices": ["i", "j"]}}}
  }
}
```

### Template 3: Production Planning (Multi-Period)

```json
{
  "schema_version": "2.0",
  "problem_class": "production_planning",
  "problem_type": "LP",
  "sense": "maximize",
  "sets": {
    "Products": {"index_symbol": "p", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "products"},
    "Periods": {"index_symbol": "t", "size": 12, "ordered": true}
  },
  "parameters": {
    "demand_pt": {"domain": ["Products", "Periods"], "type": "float", "source": "demand.csv", "index_columns": ["product_id", "period_id"], "column": "demand"},
    "production_cost_p": {"domain": ["Products"], "type": "float", "source": "costs.csv", "column": "prod_cost", "index_columns": ["product_id"]},
    "revenue_p": {"domain": ["Products"], "type": "float", "source": "costs.csv", "column": "revenue", "index_columns": ["product_id"]},
    "capacity_t": {"domain": ["Periods"], "type": "float", "source": "capacity.csv", "column": "capacity", "index_columns": ["period_id"]},
    "holding_cost_p": {"domain": ["Products"], "type": "float", "source": "costs.csv", "column": "holding_cost", "index_columns": ["product_id"]}
  },
  "variables": {
    "produce_pt": {"description": "Units of p produced in t", "domain": ["Products", "Periods"], "type": "continuous", "lower_bound": 0.0},
    "inventory_pt": {"description": "Units of p held at end of t", "domain": ["Products", "Periods"], "type": "continuous", "lower_bound": 0.0}
  },
  "constraints": {
    "capacity": {
      "domain": ["Periods"], "expression": {"type": "indexed_sum", "over": ["Products:p"], "body": {"type": "variable", "name": "produce_pt", "indices": ["p", "t"]}}, "sense": "<=", "rhs": {"type": "parameter", "name": "capacity_t", "indices": ["t"]}
    },
    "inventory_balance": {
      "domain": ["Products", "Periods"],
      "expression": {"type": "variable", "name": "inventory_pt", "indices": ["p", "t"]},
      "sense": "=",
      "rhs": {
        "type": "sum",
        "left": {"type": "variable", "name": "inventory_pt", "indices": ["p", "t"], "lag": -1},
        "right": {
          "type": "subtract",
          "left": {"type": "variable", "name": "produce_pt", "indices": ["p", "t"]},
          "right": {"type": "parameter", "name": "demand_pt", "indices": ["p", "t"]}
        }
      }
    }
  },
  "objective": {
    "sense": "maximize",
    "expression": {
      "type": "subtract",
      "left": {"type": "indexed_sum", "over": ["Products:p", "Periods:t"], "body": {"type": "multiply", "left": {"type": "parameter", "name": "revenue_p", "indices": ["p"]}, "right": {"type": "variable", "name": "produce_pt", "indices": ["p", "t"]}}},
      "right": {
        "type": "sum",
        "left": {"type": "indexed_sum", "over": ["Products:p", "Periods:t"], "body": {"type": "multiply", "left": {"type": "parameter", "name": "production_cost_p", "indices": ["p"]}, "right": {"type": "variable", "name": "produce_pt", "indices": ["p", "t"]}}},
        "right": {"type": "indexed_sum", "over": ["Products:p", "Periods:t"], "body": {"type": "multiply", "left": {"type": "parameter", "name": "holding_cost_p", "indices": ["p"]}, "right": {"type": "variable", "name": "inventory_pt", "indices": ["p", "t"]}}}
      }
    }
  }
}
```

### Template 4: Facility Location (with binary opening decisions)

```json
{
  "schema_version": "2.0",
  "problem_class": "facility_location",
  "problem_type": "MILP",
  "sense": "minimize",
  "sets": {
    "Facilities": {"index_symbol": "i", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "facilities"},
    "Customers": {"index_symbol": "j", "source": "sets.csv", "column": "element", "filter_column": "set_name", "filter_value": "customers"}
  },
  "parameters": {
    "fixed_cost_i": {"domain": ["Facilities"], "type": "float", "source": "costs.csv", "column": "fixed_cost", "index_columns": ["facility_id"]},
    "transport_cost_ij": {"domain": ["Facilities", "Customers"], "type": "float", "source": "transport.csv", "column": "unit_cost", "index_columns": ["facility_id", "customer_id"], "missing_default": "inf"},
    "demand_j": {"domain": ["Customers"], "type": "float", "source": "demand.csv", "column": "demand", "index_columns": ["customer_id"]},
    "capacity_i": {"domain": ["Facilities"], "type": "float", "source": "capacity.csv", "column": "capacity", "index_columns": ["facility_id"]},
    "bigM": {"domain": [], "type": "float", "source": "bigM.csv", "column": "bigM"}
  },
  "variables": {
    "open_i": {"description": "1 if facility i is opened", "domain": ["Facilities"], "type": "binary"},
    "flow_ij": {"description": "Units from facility i to customer j", "domain": ["Facilities", "Customers"], "type": "continuous", "lower_bound": 0.0, "domain_filter": "transport_cost_ij"}
  },
  "constraints": {
    "capacity": {"domain": ["Facilities"], "expression": {"type": "indexed_sum", "over": ["Customers:j"], "body": {"type": "variable", "name": "flow_ij", "indices": ["i", "j"]}}, "sense": "<=", "rhs": {"type": "multiply", "left": {"type": "parameter", "name": "capacity_i", "indices": ["i"]}, "right": {"type": "variable", "name": "open_i", "indices": ["i"]}}},
    "demand": {"domain": ["Customers"], "expression": {"type": "indexed_sum", "over": ["Facilities:i"], "body": {"type": "variable", "name": "flow_ij", "indices": ["i", "j"]}}, "sense": "=", "rhs": {"type": "parameter", "name": "demand_j", "indices": ["j"]}}
  },
  "objective": {
    "sense": "minimize",
    "expression": {
      "type": "sum",
      "left": {"type": "indexed_sum", "over": ["Facilities:i"], "body": {"type": "multiply", "left": {"type": "parameter", "name": "fixed_cost_i", "indices": ["i"]}, "right": {"type": "variable", "name": "open_i", "indices": ["i"]}}},
      "right": {"type": "indexed_sum", "over": ["Facilities:i", "Customers:j"], "body": {"type": "multiply", "left": {"type": "parameter", "name": "transport_cost_ij", "indices": ["i", "j"]}, "right": {"type": "variable", "name": "flow_ij", "indices": ["i", "j"]}}}
    }
  }
}
```

---

## Validation: How to Self-Check Your IR

Before submitting IR to the compiler, check:

1. **All sets defined**: Every name in `domain` fields must be a key in `sets`
2. **All indices match**: Index variables in expression trees must match their domain ordering
3. **Parameters have sources**: Every parameter should have a `source` (CSV file) or be explicitly scalar
4. **Constraints have complete expressions**: Both `expression` and `rhs` must be present and valid
5. **Sparse tables have defaults**: `missing_default` for any parameter with incomplete Cartesian product coverage
6. **Objective sense is valid**: `"minimize"` or `"maximize"` only
7. **Binary variables have bounds**: `lower_bound: 0.0` and `upper_bound: 1.0` for all binary vars

When validation fails, the compiler returns a numbered error code (e.g., `E003`) pointing to the exact issue. Use this to iteratively fix the IR.

---

## See Also

- [IR Schema Complete Reference](ir-schema.md) — Every field documented
- [Configuration Guide](configuration.md) — orpilot.toml settings
- [Quick Start Guide](quickstart.md) — Your first solve
