# Supply Chain Network Optimization Report

## Executive Summary

The optimization model was solved to **global optimality** in 0.07 seconds using Gurobi. The objective — maximizing total profit across a 3-period supply chain network — yields an optimal value of **−$1,419,138.19**. The negative result reflects that fixed facility opening costs substantially outweigh revenues for this small-scale dataset: total revenues are approximately $17,000 while facility fixed and operating costs exceed $1.4 million. The model identifies the lowest-cost configuration that still satisfies all customer demand, which is the best achievable outcome under these economics.

---

## Facility Decisions

### Production Sites
Two of the five candidate production sites are opened:

| Site   | Status | Fixed Cost   | Rationale                                          |
|--------|--------|--------------|----------------------------------------------------|
| PS_042 | Open   | $289,716     | Lowest unit production cost across all products    |
| PS_044 | Open   | $236,107     | Second-lowest fixed cost; handles C_0006's demand  |
| PS_013 | Closed | $489,286     | Higher production and fixed costs; not needed      |
| PS_039 | Closed | $518,120     | Highest fixed cost; most expensive unit costs      |
| PS_047 | Closed | $455,095     | High fixed cost; no customer assigned through it   |

### Distribution Centers
Three of the five candidate DCs are opened:

| DC     | Status | Fixed Cost   | Serves         |
|--------|--------|--------------|----------------|
| DC_002 | Open   | $120,499     | C_0105         |
| DC_005 | Open   | $218,171     | C_0019         |
| DC_044 | Open   | $275,583     | C_0006         |
| DC_006 | Closed | $377,203     | Not needed     |
| DC_041 | Closed | $385,237     | Not needed     |

The model opens exactly the DCs needed to serve each customer group via the cheapest available routes, avoiding the two most expensive DCs (DC_006 and DC_041).

---

## Production Plan

All production is concentrated at PS_042 and PS_044. Production quantities match demand exactly each period — no inventory is held.

**PS_042 (primary site — all three products):**

| Product | Period 1 | Period 2 | Period 3 | Total |
|---------|----------|----------|----------|-------|
| P_135   | 51       | 68       | 79       | 198   |
| P_277   | 32       | 27       | 27       | 86    |
| P_317   | 46       | 42       | 52       | 140   |

**PS_044 (secondary site — P_135 and P_277 only):**

| Product | Period 1 | Period 2 | Period 3 | Total |
|---------|----------|----------|----------|-------|
| P_135   | 10       | 12       | 11       | 33    |
| P_277   | 23       | 19       | 25       | 67    |

PS_042's production capacity (30,000–32,000 units/period) is far larger than the current demand, so the site operates well below capacity. The primary driver for choosing PS_042 is its lowest per-unit production cost: $6.42 for P_135, $6.32 for P_277, and $16.53 for P_317.

---

## Transportation Flows

### Production Sites → Distribution Centers

| From   | To     | Product | P1 | P2 | P3 |
|--------|--------|---------|----|----|----|
| PS_042 | DC_002 | P_317   | 38 | 34 | 43 |
| PS_042 | DC_005 | P_135   | 51 | 68 | 79 |
| PS_042 | DC_005 | P_277   | 32 | 27 | 27 |
| PS_042 | DC_005 | P_317   | 8  | 8  | 9  |
| PS_044 | DC_044 | P_135   | 10 | 12 | 11 |
| PS_044 | DC_044 | P_277   | 23 | 19 | 25 |

### Distribution Centers → Customers

| From   | To     | Product | P1 | P2 | P3 | Meets Demand? |
|--------|--------|---------|----|----|----|---------------|
| DC_002 | C_0105 | P_317   | 38 | 34 | 43 | Yes           |
| DC_005 | C_0019 | P_135   | 51 | 68 | 79 | Yes           |
| DC_005 | C_0019 | P_277   | 32 | 27 | 27 | Yes           |
| DC_005 | C_0019 | P_317   | 8  | 8  | 9  | Yes           |
| DC_044 | C_0006 | P_135   | 10 | 12 | 11 | Yes           |
| DC_044 | C_0006 | P_277   | 23 | 19 | 25 | Yes           |

All customer demand is met in every period. Each customer is served by a single DC, creating clean, non-overlapping service territories.

---

## Inventory

No inventory is held at any production site or DC in any period. The model produces and ships exactly the amount needed each period (just-in-time). This is optimal given that holding costs add expense without revenue benefit in a demand-constrained setting.

---

## Cost Breakdown (Approximate)

| Cost Category             | Amount         |
|---------------------------|---------------|
| Fixed facility opening     | ~$1,140,000   |
| Operating costs (3 periods)| ~$283,000     |
| Production costs           | ~$5,000       |
| Transportation (site→DC)   | ~$5,300       |
| Transportation (DC→cust)   | ~$2,800       |
| **Total Costs**            | **~$1,436,000**|
| Revenue from sales         | ~$17,000      |
| **Net Profit (Objective)** | **−$1,419,138**|

The dominant cost driver is facility fixed costs (~79% of total costs). Variable costs (production, transport) and revenues are negligible by comparison at this demand scale.

---

## Key Findings and Concerns

1. **Fixed costs dominate**: The network loses money at current demand volumes. Facility opening costs alone are ~84× the revenue. This is expected for a demo dataset with small demand numbers but realistic fixed costs.

2. **Single-source routing**: Each customer is served by exactly one DC, and each active DC is supplied by exactly one site. This clean structure minimizes the number of facilities that must be opened.

3. **Cost-driven site selection**: PS_042 is chosen as the primary site purely on unit production cost — it is the cheapest to produce at ($6.42/unit for P_135 vs. $12.87 at PS_039). This offsets its higher fixed cost relative to PS_044.

4. **Unused capacity**: PS_042 operates at less than 1% of its production capacity. If demand were to grow substantially, the existing facility could absorb it without additional site openings.

5. **Seasonal demand growth**: C_0019's demand for P_135 grows from 51 → 68 → 79 units over three periods (+55% total). If this trend continues, transportation flows would need to be revisited.

---

## Suggested Next Steps

- **Sensitivity on demand scale**: Re-run with 10× or 100× demand to identify the break-even volume at which the network becomes profitable, and to understand how facility selection changes.
- **Fixed cost sensitivity**: Examine how the solution changes if PS_042's fixed cost increases (it has the lowest variable cost but non-trivial fixed cost) — is there a threshold where PS_044 becomes the sole active site?
- **Adding customers or products**: The current 3-customer, 3-product scope is small. Adding more customers served by DC_005 (which has large remaining throughput capacity) could improve economics with minimal additional cost.
- **Contract pricing**: With unit revenues of $23–$60 per product and production costs of $6–$34 per unit, the gross margin per unit is positive. The business case depends entirely on whether fixed facility costs can be amortized over higher volume.

---

## Output Files

### `solution_open_dc.csv`
Records whether each distribution center is open in each period. Columns: `dc_id` (the DC identifier), `period_id` (the month), `value` (1.0 = open, 0.0 = closed). Use this to determine which DCs are active and when to begin incurring their operating costs.

### `solution_open_site.csv`
Same structure as above but for production sites. Columns: `site_id`, `period_id`, `value` (1.0 = open, 0.0 = closed). Identifies which manufacturing facilities to activate and in which periods.

### `solution_prod.csv`
Production quantities decided at each site. Columns: `site_id`, `product_id`, `period_id`, `value` (units produced). Use this to set production schedules at each active facility.

### `solution_flow_prod_to_dc.csv`
Shipment volumes from production sites to distribution centers. Columns: `site_id`, `dc_id`, `product_id`, `period_id`, `value` (units shipped). Use this to plan inbound logistics at each DC.

### `solution_flow_dc_to_cust.csv`
Shipment volumes from DCs to customers. Columns: `dc_id`, `customer_id`, `product_id`, `period_id`, `value` (units shipped). Use this to plan outbound delivery schedules and confirm demand fulfillment.

### `solution_inv_site.csv`
Ending inventory held at each production site. Columns: `site_id`, `product_id`, `period_id`, `value` (units in inventory). All values are zero in this solution — no buffer stock is kept at any production site.

### `solution_inv_dc.csv`
Ending inventory held at each DC. Columns: `dc_id`, `product_id`, `period_id`, `value` (units in inventory). All values are zero — DCs ship out everything they receive in the same period, keeping warehouse utilization at a minimum.
