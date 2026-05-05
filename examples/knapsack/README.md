# Knapsack Problem

Select items to maximize total value without exceeding the weight capacity.

## Problem

- **Decision variable:** `x[i]` — binary, 1 if item `i` is selected
- **Objective:** Maximize Σ value[i] × x[i]
- **Constraint:** Σ weight[i] × x[i] ≤ capacity

## Data

| File | Description |
|------|-------------|
| `data/items.csv` | Item IDs, values, and weights |
| `data/capacity.csv` | Knapsack weight capacity (scalar) |

### items.csv
| item_id | value | weight |
|---|---|---|
| laptop | 15 | 5 |
| camera | 10 | 3 |
| book | 5 | 1 |
| phone | 8 | 2 |
| tablet | 12 | 4 |

### capacity.csv
| capacity |
|---|
| 10 |

## Expected Optimal Solution

**Objective value: 35**

| Item | Selected | Value | Weight |
|------|----------|-------|--------|
| laptop | 0 | — | — |
| camera | 1 | 10 | 3 |
| book | 1 | 5 | 1 |
| phone | 1 | 8 | 2 |
| tablet | 1 | 12 | 4 |
| **Total** | | **35** | **10** |
