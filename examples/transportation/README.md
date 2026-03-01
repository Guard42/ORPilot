# Transportation Problem

Minimize the total shipping cost from warehouses to customers subject to supply and demand constraints.

## Problem

- **Decision variable:** `flow[w, c]` — units shipped from warehouse `w` to customer `c`
- **Objective:** Minimize total cost = Σ cost[w,c] × flow[w,c]
- **Constraints:**
  - Supply: total outbound from each warehouse ≤ supply capacity
  - Demand: total inbound to each customer = demand requirement

## Data

| File | Description |
|------|-------------|
| `data/warehouses.csv` | Warehouse IDs and supply capacities |
| `data/customers.csv` | Customer IDs and demand requirements |
| `data/costs.csv` | Per-unit shipping cost from each warehouse to each customer |

### warehouses.csv
| warehouse_id | supply |
|---|---|
| W1 | 50 |
| W2 | 60 |

### customers.csv
| customer_id | demand |
|---|---|
| C1 | 30 |
| C2 | 40 |
| C3 | 30 |

### costs.csv (W→C cost matrix)
|  | C1 | C2 | C3 |
|---|---|---|---|
| W1 | 2 | 3 | 1 |
| W2 | 5 | 4 | 8 |

## Expected Optimal Solution

**Objective value: 280**

| Flow | Amount | Unit Cost | Subtotal |
|------|--------|-----------|----------|
| W1 → C3 | 30 | 1 | 30 |
| W1 → C1 | 20 | 2 | 40 |
| W2 → C1 | 10 | 5 | 50 |
| W2 → C2 | 40 | 4 | 160 |
| **Total** | | | **280** |
