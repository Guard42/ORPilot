# Transportation Problem (Coordinate-Based Costs)

Minimize the total shipping cost from warehouses to customers subject to supply and demand constraints. Unlike the standard transportation example, **per-unit shipping costs are not given directly** — only the (x, y) coordinates of each node. The cost is $1 per unit shipped per unit of Euclidean distance, so the parameter computation agent must derive the cost matrix from the coordinates before solving.

## Problem

- **Decision variable:** `flow[w, c]` — units shipped from warehouse `w` to customer `c`
- **Objective:** Minimize total cost = Σ dist(w, c) × flow[w, c]
- **Constraints:**
  - Supply: total outbound from each warehouse ≤ supply capacity
  - Demand: total inbound to each customer = demand requirement

## Data

The problem text embeds coordinates rather than a cost matrix. The `orpilot solve` pipeline handles this in two steps:

1. **TextIngestor** extracts the coordinates, supply, and demand from the problem text into structured tables.
2. **param_computation** computes the pairwise Euclidean distance between every (warehouse, customer) pair and writes it as the per-unit shipping cost (cost = distance × $1).

### Node coordinates

| node_id | x | y |
|---------|---|---|
| W1      | 1 | 4 |
| W2      | 1 | 8 |
| C1      | 5 | 1 |
| C2      | 8 | 6 |
| C3      | 4 | 10 |

### Supply

| warehouse_id | supply |
|---|---|
| W1 | 50 |
| W2 | 60 |

### Demand

| customer_id | demand |
|---|---|
| C1 | 30 |
| C2 | 40 |
| C3 | 30 |

### Derived cost matrix (computed by param_computation)

Cost per unit shipped = Euclidean distance between source and destination.

|    | C1 | C2 | C3 |
|----|----|----|-----|
| W1 | √25 = 5.00 | √53 ≈ 7.28 | √45 ≈ 6.71 |
| W2 | √65 ≈ 8.06 | √53 ≈ 7.28 | √13 ≈ 3.61 |

## Expected Optimal Solution

**Objective value: 150 + 40√53 + 30√13 ≈ 549.37**

| Flow | Amount | Unit Cost | Subtotal |
|------|--------|-----------|----------|
| W1 → C1 | 30 | √25 = 5.00 | 150.00 |
| W1 → C2 | 20 | √53 ≈ 7.28 | ≈ 145.60 |
| W2 → C2 | 20 | √53 ≈ 7.28 | ≈ 145.60 |
| W2 → C3 | 30 | √13 ≈ 3.61 | ≈ 108.17 |
| **Total** | | | **≈ 549.37** |

W2 exclusively serves C3 (its nearest customer at distance √13 ≈ 3.61). W1 exclusively serves C1 (its nearest customer at distance 5). Both share C2 equally since W1→C2 and W2→C2 have identical cost (√53 ≈ 7.28), with each contributing 20 units to fill C2's demand of 40.
