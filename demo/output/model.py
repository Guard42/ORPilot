import gurobipy as gp
from gurobipy import GRB

def solve(data, time_limit=None, show_solver_log=False):
    SEP = "\x1f"

    # ---- Load sets from sets.csv (authoritative) ----
    sets_data = {r["set_name"]: r["element"] for r in data["sets"]}
    # Build set lists by name
    set_members = {}
    for r in data["sets"]:
        sn = r["set_name"]
        el = r["element"]
        set_members.setdefault(sn, []).append(el)

    production_sites = set_members.get("production_sites", [])
    distribution_centers = set_members.get("distribution_centers", [])
    customers = set_members.get("customers", [])
    products = set_members.get("products", [])
    periods = set_members.get("periods", [])

    # ---- Load parameters ----
    # Demand: customer_id, product_id, period_id, demand
    demand_data = {}
    for r in data["demand"]:
        k = r["customer_id"]
        p = r["product_id"]
        t = r["period_id"]
        demand_data[(k, p, t)] = float(r["demand"])

    # Production capacity: site_id, period_id, capacity
    prod_cap_data = {}
    for r in data["production_capacity"]:
        prod_cap_data[(r["site_id"], r["period_id"])] = float(r["capacity"])

    # Throughput capacity: dc_id, period_id, capacity
    throughput_cap_data = {}
    for r in data["throughput_capacity"]:
        throughput_cap_data[(r["dc_id"], r["period_id"])] = float(r["capacity"])

    # Storage capacity sites: site_id, capacity
    storage_cap_site = {}
    for r in data["storage_capacity_sites"]:
        storage_cap_site[r["site_id"]] = float(r["capacity"])

    # Storage capacity DCs: dc_id, capacity
    storage_cap_dc = {}
    for r in data["storage_capacity_dcs"]:
        storage_cap_dc[r["dc_id"]] = float(r["capacity"])

    # Production cost: site_id, product_id, unit_cost
    prod_cost_data = {}
    for r in data["production_cost"]:
        prod_cost_data[(r["site_id"], r["product_id"])] = float(r["unit_cost"])

    # Transport prod->dc: site_id, dc_id, unit_cost - sparse (only valid lanes)
    transp_cost_pd = {}
    transp_lanes_pd = set()
    for r in data["transport_cost_prod_to_dc"]:
        key = (r["site_id"], r["dc_id"])
        transp_cost_pd[key] = float(r["unit_cost"])
        transp_lanes_pd.add(key)

    # Transport dc->cust: dc_id, customer_id, unit_cost - sparse
    transp_cost_dc = {}
    transp_lanes_dc = set()
    for r in data["transport_cost_dc_to_cust"]:
        key = (r["dc_id"], r["customer_id"])
        transp_cost_dc[key] = float(r["unit_cost"])
        transp_lanes_dc.add(key)

    # Holding cost sites: site_id, product_id, unit_cost
    hold_cost_site_data = {}
    for r in data["holding_cost_sites"]:
        hold_cost_site_data[(r["site_id"], r["product_id"])] = float(r["unit_cost"])

    # Holding cost DCs: dc_id, product_id, unit_cost
    hold_cost_dc_data = {}
    for r in data["holding_cost_dcs"]:
        hold_cost_dc_data[(r["dc_id"], r["product_id"])] = float(r["unit_cost"])

    # Fixed cost open sites: site_id, cost
    fixed_cost_site = {}
    for r in data["fixed_cost_open_sites"]:
        fixed_cost_site[r["site_id"]] = float(r["cost"])

    # Fixed cost open DCs: dc_id, cost
    fixed_cost_dc = {}
    for r in data["fixed_cost_open_dcs"]:
        fixed_cost_dc[r["dc_id"]] = float(r["cost"])

    # Operating cost sites: site_id, cost
    operating_cost_site = {}
    for r in data["operating_cost_sites"]:
        operating_cost_site[r["site_id"]] = float(r["cost"])

    # Operating cost DCs: dc_id, cost
    operating_cost_dc = {}
    for r in data["operating_cost_dcs"]:
        operating_cost_dc[r["dc_id"]] = float(r["cost"])

    # Revenue: product_id, unit_revenue
    revenue_data = {}
    for r in data["revenue"]:
        revenue_data[r["product_id"]] = float(r["unit_revenue"])

    # Initial inventory sites (optional)
    init_inv_site = {}
    for r in data.get("initial_inventory_sites", []):
        init_inv_site[(r["site_id"], r["product_id"])] = float(r["quantity"])

    # Initial inventory DCs (optional)
    init_inv_dc = {}
    for r in data.get("initial_inventory_dcs", []):
        init_inv_dc[(r["dc_id"], r["product_id"])] = float(r["quantity"])

    # Big M
    bigM_val = float(data["bigM"][0]["bigM"])

    # ---- Build model ----
    env = gp.Env(empty=True)
    env.setParam("LogToConsole", 1 if show_solver_log else 0)
    env.start()
    m = gp.Model(env=env)
    if time_limit is not None:
        m.Params.TimeLimit = time_limit

    # ---- Decision variables ----
    # prod[i, p, t]
    prod = {}
    for i in production_sites:
        for p in products:
            for t in periods:
                prod[i, p, t] = m.addVar(lb=0, name=f"prod{SEP}{i}{SEP}{p}{SEP}{t}")

    # flow_prod_to_dc[i, j, p, t] - only for valid lanes
    flow_pd = {}
    for (i, j) in transp_lanes_pd:
        for p in products:
            for t in periods:
                flow_pd[i, j, p, t] = m.addVar(lb=0, name=f"flow_prod_to_dc{SEP}{i}{SEP}{j}{SEP}{p}{SEP}{t}")

    # flow_dc_to_cust[j, k, p, t] - only for valid lanes
    flow_dc = {}
    for (j, k) in transp_lanes_dc:
        for p in products:
            for t in periods:
                flow_dc[j, k, p, t] = m.addVar(lb=0, name=f"flow_dc_to_cust{SEP}{j}{SEP}{k}{SEP}{p}{SEP}{t}")

    # inv_site[i, p, t]
    inv_site = {}
    for i in production_sites:
        for p in products:
            for t in periods:
                inv_site[i, p, t] = m.addVar(lb=0, name=f"inv_site{SEP}{i}{SEP}{p}{SEP}{t}")

    # inv_dc[j, p, t]
    inv_dc = {}
    for j in distribution_centers:
        for p in products:
            for t in periods:
                inv_dc[j, p, t] = m.addVar(lb=0, name=f"inv_dc{SEP}{j}{SEP}{p}{SEP}{t}")

    # open_site[i, t]
    open_site = {}
    for i in production_sites:
        for t in periods:
            open_site[i, t] = m.addVar(vtype=GRB.BINARY, name=f"open_site{SEP}{i}{SEP}{t}")

    # open_dc[j, t]
    open_dc = {}
    for j in distribution_centers:
        for t in periods:
            open_dc[j, t] = m.addVar(vtype=GRB.BINARY, name=f"open_dc{SEP}{j}{SEP}{t}")

    m.update()

    # ---- Objective: Maximize profit ----
    # Revenue from sales (flow_dc_to_cust)
    revenue_expr = gp.quicksum(
        revenue_data.get(p, 0.0) * flow_dc[j, k, p, t]
        for (j, k, p, t), _ in flow_dc.items()
    )

    # Production cost
    prod_cost_expr = gp.quicksum(
        prod_cost_data.get((i, p), float('inf')) * prod[i, p, t]
        for i in production_sites for p in products for t in periods
    )

    # Transport prod->dc cost
    transp_pd_cost_expr = gp.quicksum(
        transp_cost_pd[(i, j)] * flow_pd[i, j, p, t]
        for (i, j, p, t), _ in flow_pd.items()
    )

    # Transport dc->cust cost
    transp_dc_cost_expr = gp.quicksum(
        transp_cost_dc[(j, k)] * flow_dc[j, k, p, t]
        for (j, k, p, t), _ in flow_dc.items()
    )

    # Holding cost sites
    hold_site_cost_expr = gp.quicksum(
        hold_cost_site_data.get((i, p), 0.0) * inv_site[i, p, t]
        for i in production_sites for p in products for t in periods
    )

    # Holding cost DCs
    hold_dc_cost_expr = gp.quicksum(
        hold_cost_dc_data.get((j, p), 0.0) * inv_dc[j, p, t]
        for j in distribution_centers for p in products for t in periods
    )

    # Fixed opening costs (incurred once when first opened)
    # open_site[i, t] is binary; opening cost incurred in period t if open_site[i,t] - open_site[i,t-1] = 1
    # To model this linearly, use: fixed_cost * (open_site[i, t] - open_site[i, t-1]) for t>0, and fixed_cost * open_site[i, 0] for t=0
    open_site_fixed_expr = gp.LinExpr()
    for i in production_sites:
        cost_i = fixed_cost_site.get(i, 0.0)
        # For t = first period: cost incurred if open in period 1
        first_t = periods[0]
        open_site_fixed_expr += cost_i * open_site[i, first_t]
        # For subsequent periods: cost incurred if newly opened (open_site[i,t] - open_site[i,t-1])
        for idx in range(1, len(periods)):
            t_curr = periods[idx]
            t_prev = periods[idx - 1]
            open_site_fixed_expr += cost_i * (open_site[i, t_curr] - open_site[i, t_prev])
    # The above is equivalent to cost_i * open_site[i, last_period] because of telescoping,
    # but only if opening cost is incurred once. Let me fix:
    # Actually fixed opening cost is incurred when the site first opens. The standard way:
    # open_site[i,t] >= open_site[i,t-1] (non-closing constraint)
    # So once open_site becomes 1, it stays 1.
    # The opening cost is incurred in the first period where open_site[i,t] = 1.
    # Sum over t of cost_i * (open_site[i,t] - open_site[i,t-1]) where open_site[i,0] := 0
    # = cost_i * open_site[i, last_period] (telescoping sum).
    # So we just charge cost_i * open_site[i, last_period] if opening cost is incurred once.
    # But actually the problem says "Fixed opening costs are incurred once when site/DC is opened"
    # So it's cost_i * open_site[i, last_t].
    # Let me redo this more cleanly.

    # Fixed opening costs - incurred once, so charge on the last period's value (since it's monotonically non-decreasing)
    # open_site[i, first_t] is the opening decision (since before that, it's closed).
    # Actually if open_site[i,t] = 1 for all t >= t0, then open_site[i, first_t] captures the decision.
    # Let me just use: opening cost = cost_i * open_site[i, first_period]? No, what if they open later?
    # The constraint open_site[i,t] >= open_site[i,t-1] means once 1, always 1.
    # So the first period where it's 1 is the opening period.
    # The telescoping sum: cost_i * (open_site[i,last] - 0) = cost_i * open_site[i,last]
    # But that gives cost_i if ever opened, regardless of when. That's correct for "once when opened".
    # Let me rebuild the expressions.

    m.update()

    # Now build objective properly
    obj = revenue_expr - prod_cost_expr - transp_pd_cost_expr - transp_dc_cost_expr - hold_site_cost_expr - hold_dc_cost_expr

    # Fixed opening costs
    for i in production_sites:
        cost_i = fixed_cost_site.get(i, 0.0)
        if cost_i != 0.0:
            obj -= cost_i * open_site[i, periods[-1]]  # once if ever opened

    for j in distribution_centers:
        cost_j = fixed_cost_dc.get(j, 0.0)
        if cost_j != 0.0:
            obj -= cost_j * open_dc[j, periods[-1]]  # once if ever opened

    # Operating costs - incurred each period the facility is open
    for i in production_sites:
        cost_i = operating_cost_site.get(i, 0.0)
        if cost_i != 0.0:
            for t in periods:
                obj -= cost_i * open_site[i, t]

    for j in distribution_centers:
        cost_j = operating_cost_dc.get(j, 0.0)
        if cost_j != 0.0:
            for t in periods:
                obj -= cost_j * open_dc[j, t]

    m.setObjective(obj, GRB.MAXIMIZE)

    # ---- Constraints ----

    # 1. Production capacity: sum_p prod[i,p,t] <= production_capacity[i,t]
    for i in production_sites:
        for t in periods:
            cap = prod_cap_data.get((i, t), float('inf'))
            if cap < float('inf'):
                m.addConstr(
                    gp.quicksum(prod[i, p, t] for p in products) <= cap,
                    name=f"prod_cap{SEP}{i}{SEP}{t}"
                )

    # 2. Throughput capacity: sum_{k,p} flow_dc_to_cust[j,k,p,t] <= throughput_capacity[j,t]
    for j in distribution_centers:
        for t in periods:
            cap = throughput_cap_data.get((j, t), float('inf'))
            if cap < float('inf'):
                m.addConstr(
                    gp.quicksum(
                        var
                        for (dc, k, p, tt), var in flow_dc.items()
                        if dc == j and tt == t
                    ) <= cap,
                    name=f"throughput_cap{SEP}{j}{SEP}{t}"
                )

    # 3. Storage capacity sites: sum_p inv_site[i,p,t] <= storage_capacity_site[i]
    for i in production_sites:
        cap = storage_cap_site.get(i, float('inf'))
        if cap < float('inf'):
            for t in periods:
                m.addConstr(
                    gp.quicksum(inv_site[i, p, t] for p in products) <= cap,
                    name=f"store_site{SEP}{i}{SEP}{t}"
                )

    # 4. Storage capacity DCs: sum_p inv_dc[j,p,t] <= storage_capacity_dc[j]
    for j in distribution_centers:
        cap = storage_cap_dc.get(j, float('inf'))
        if cap < float('inf'):
            for t in periods:
                m.addConstr(
                    gp.quicksum(inv_dc[j, p, t] for p in products) <= cap,
                    name=f"store_dc{SEP}{j}{SEP}{t}"
                )

    # 5. Demand fulfillment: sum_j flow_dc_to_cust[j,k,p,t] = demand[k,p,t]
    for k in customers:
        for p in products:
            for t in periods:
                dmd = demand_data.get((k, p, t), 0.0)
                m.addConstr(
                    gp.quicksum(
                        var
                        for (dc, cust, prod_id, tt), var in flow_dc.items()
                        if cust == k and prod_id == p and tt == t
                    ) == dmd,
                    name=f"demand{SEP}{k}{SEP}{p}{SEP}{t}"
                )

    # 6. Production site open constraint (absorb binary into capacity)
    # sum_p prod[i,p,t] <= bigM * open_site[i,t]  ->  use bigM for this logical constraint
    # Actually the instruction says to absorb binary into capacity. But the production capacity
    # is period-specific. We can combine: prod[i,p,t] constraint: open_site controls whether prod can happen.
    # We'll use the RHS multiplication pattern: capacity * open_site
    for i in production_sites:
        for t in periods:
            cap = prod_cap_data.get((i, t), float('inf'))
            if cap < float('inf'):
                # Already have prod_cap constraint above. Instead of having separate big-M,
                # we absorb open_site into the capacity constraint RHS.
                # Remove the previous constraint and add the combined one.
                pass  # We'll handle this differently - replace the capacity constraint
    # Actually, let me restructure. I'll use the open variable to multiply capacity.

    # Let me remove the production capacity constraints I already added and redo them.
    # Actually I can't easily remove. Let me just rebuild properly.
    # Since I haven't optimized yet, I'll clear and rebuild.

    # Remove all constraints from model
    # m.remove(m.getConstrs())  -- simpler: just clear and rebuild from scratch

    # Actually let me just refactor the code to build in one pass below.
    # I'll clear the model and rebuild cleanly.

    # Remove all constraints
    constrs_to_remove = list(m.getConstrs())
    for c in constrs_to_remove:
        m.remove(c)
    m.update()

    # ---- Rebuild constraints with open variables absorbed ----

    # 1. Production capacity (with open_site absorbed): sum_p prod[i,p,t] <= production_capacity[i,t] * open_site[i,t]
    for i in production_sites:
        for t in periods:
            cap = prod_cap_data.get((i, t), float('inf'))
            if cap < float('inf'):
                m.addConstr(
                    gp.quicksum(prod[i, p, t] for p in products) <= cap * open_site[i, t],
                    name=f"prod_cap{SEP}{i}{SEP}{t}"
                )

    # 2. Throughput capacity (with open_dc absorbed): sum_{k,p} flow_dc_to_cust <= throughput_capacity[j,t] * open_dc[j,t]
    for j in distribution_centers:
        for t in periods:
            cap = throughput_cap_data.get((j, t), float('inf'))
            if cap < float('inf'):
                m.addConstr(
                    gp.quicksum(
                        var
                        for (dc, k, p, tt), var in flow_dc.items()
                        if dc == j and tt == t
                    ) <= cap * open_dc[j, t],
                    name=f"throughput_cap{SEP}{j}{SEP}{t}"
                )

    # 3. Storage capacity sites (time-invariant, so no open absorption needed - storage can exist even if closed?
    #    Actually if site is closed, inventory must be zero. So we use open_site.)
    for i in production_sites:
        cap = storage_cap_site.get(i, float('inf'))
        if cap < float('inf'):
            for t in periods:
                m.addConstr(
                    gp.quicksum(inv_site[i, p, t] for p in products) <= cap * open_site[i, t],
                    name=f"store_site{SEP}{i}{SEP}{t}"
                )

    # 4. Storage capacity DCs (with open_dc absorbed)
    for j in distribution_centers:
        cap = storage_cap_dc.get(j, float('inf'))
        if cap < float('inf'):
            for t in periods:
                m.addConstr(
                    gp.quicksum(inv_dc[j, p, t] for p in products) <= cap * open_dc[j, t],
                    name=f"store_dc{SEP}{j}{SEP}{t}"
                )

    # 5. Demand fulfillment
    for k in customers:
        for p in products:
            for t in periods:
                dmd = demand_data.get((k, p, t), 0.0)
                m.addConstr(
                    gp.quicksum(
                        var
                        for (dc, cust, prod_id, tt), var in flow_dc.items()
                        if cust == k and prod_id == p and tt == t
                    ) == dmd,
                    name=f"demand{SEP}{k}{SEP}{p}{SEP}{t}"
                )

    # 6-7. The big-M logical constraints for open_site/open_dc are now absorbed into capacity.
    # But we also need to handle inbound flow to DC being limited by open_dc.
    # Inbound flow to DC constraint: sum_{i,p} flow_prod_to_dc[i,j,p,t] <= bigM * open_dc[j,t]
    # Absorb into a constraint. Actually we can use throughput capacity to also limit inbound
    # if throughput applies to outbound only. Let's add a constraint using bigM for inbound.
    # The problem states: "A distribution center j can have inbound flow from production sites in period t
    # only if it is open in that period." Using the absorption pattern:
    # sum_{i,p} flow_prod_to_dc[i,j,p,t] <= (sum of all possible inbound) * open_dc[j,t]
    # Use a large number. The problem-provided bigM is fine here since it's a logical constraint.
    for j in distribution_centers:
        for t in periods:
            # Sum inbound flows
            m.addConstr(
                gp.quicksum(
                    var
                    for (i, dc, p, tt), var in flow_pd.items()
                    if dc == j and tt == t
                ) <= bigM_val * open_dc[j, t],
                name=f"inbound_dc{SEP}{j}{SEP}{t}"
            )

    # 8. Outbound flow already handled by throughput capacity absorbing open_dc.

    # 9. Non-closing constraint for production sites: open_site[i,t] >= open_site[i,t-1]
    for i in production_sites:
        for idx in range(1, len(periods)):
            t_curr = periods[idx]
            t_prev = periods[idx - 1]
            m.addConstr(open_site[i, t_curr] >= open_site[i, t_prev], name=f"nonclose_site{SEP}{i}{SEP}{t_curr}")

    # 10. Non-closing constraint for DCs
    for j in distribution_centers:
        for idx in range(1, len(periods)):
            t_curr = periods[idx]
            t_prev = periods[idx - 1]
            m.addConstr(open_dc[j, t_curr] >= open_dc[j, t_prev], name=f"nonclose_dc{SEP}{j}{SEP}{t_curr}")

    # 11. Inventory balance for production sites
    # inv_site[i,p,t-1] + prod[i,p,t] = sum_j flow_prod_to_dc[i,j,p,t] + inv_site[i,p,t]
    for i in production_sites:
        for p in products:
            # For t = first period, use initial inventory
            first_t = periods[0]
            init_val = init_inv_site.get((i, p), 0.0)
            m.addConstr(
                init_val + prod[i, p, first_t] ==
                gp.quicksum(
                    var
                    for (site, dc, prod_id, tt), var in flow_pd.items()
                    if site == i and prod_id == p and tt == first_t
                ) + inv_site[i, p, first_t],
                name=f"inv_bal_site{SEP}{i}{SEP}{p}{SEP}{first_t}"
            )
            # For t > first period
            for idx in range(1, len(periods)):
                t_curr = periods[idx]
                t_prev = periods[idx - 1]
                m.addConstr(
                    inv_site[i, p, t_prev] + prod[i, p, t_curr] ==
                    gp.quicksum(
                        var
                        for (site, dc, prod_id, tt), var in flow_pd.items()
                        if site == i and prod_id == p and tt == t_curr
                    ) + inv_site[i, p, t_curr],
                    name=f"inv_bal_site{SEP}{i}{SEP}{p}{SEP}{t_curr}"
                )

    # 12. Inventory balance for distribution centers
    # inv_dc[j,p,t-1] + sum_i flow_prod_to_dc[i,j,p,t] = sum_k flow_dc_to_cust[j,k,p,t] + inv_dc[j,p,t]
    for j in distribution_centers:
        for p in products:
            first_t = periods[0]
            init_val = init_inv_dc.get((j, p), 0.0)
            m.addConstr(
                init_val + gp.quicksum(
                    var
                    for (site, dc, prod_id, tt), var in flow_pd.items()
                    if dc == j and prod_id == p and tt == first_t
                ) == gp.quicksum(
                    var
                    for (dc, cust, prod_id, tt), var in flow_dc.items()
                    if dc == j and prod_id == p and tt == first_t
                ) + inv_dc[j, p, first_t],
                name=f"inv_bal_dc{SEP}{j}{SEP}{p}{SEP}{first_t}"
            )
            for idx in range(1, len(periods)):
                t_curr = periods[idx]
                t_prev = periods[idx - 1]
                m.addConstr(
                    inv_dc[j, p, t_prev] + gp.quicksum(
                        var
                        for (site, dc, prod_id, tt), var in flow_pd.items()
                        if dc == j and prod_id == p and tt == t_curr
                    ) == gp.quicksum(
                        var
                        for (dc, cust, prod_id, tt), var in flow_dc.items()
                        if dc == j and prod_id == p and tt == t_curr
                    ) + inv_dc[j, p, t_curr],
                    name=f"inv_bal_dc{SEP}{j}{SEP}{p}{SEP}{t_curr}"
                )

    m.update()

    # Write LP
    try:
        m.write("model.lp")
    except Exception:
        pass

    # Optimize
    m.optimize()

    # ---- Process results ----
    _status_map = {
        GRB.OPTIMAL: "optimal",
        GRB.SUBOPTIMAL: "feasible",
        GRB.INFEASIBLE: "infeasible",
        GRB.UNBOUNDED: "unbounded",
    }
    status = _status_map.get(m.Status, "error")
    obj = m.ObjVal if m.Status in (GRB.OPTIMAL, GRB.SUBOPTIMAL) else None

    variables = {}
    if status in ("optimal", "feasible"):
        for v in m.getVars():
            variables[v.VarName] = v.X

    # Build variable groups
    var_groups_map = {}
    dim_labels_map = {
        "prod": ["site_id", "product_id", "period_id"],
        "flow_prod_to_dc": ["site_id", "dc_id", "product_id", "period_id"],
        "flow_dc_to_cust": ["dc_id", "customer_id", "product_id", "period_id"],
        "inv_site": ["site_id", "product_id", "period_id"],
        "inv_dc": ["dc_id", "product_id", "period_id"],
        "open_site": ["site_id", "period_id"],
        "open_dc": ["dc_id", "period_id"],
    }

    for varname, val in variables.items():
        prefix = varname.split(SEP, 1)[0] if SEP in varname else varname
        var_groups_map.setdefault(prefix, {})[varname] = val

    variable_groups = [
        {
            "group_name": gname,
            "dimension_labels": dim_labels_map.get(gname, []),
            "variables": gvars,
        }
        for gname, gvars in var_groups_map.items()
    ]

    return {
        "status": status,
        "objective_value": obj,
        "variables": variables,
        "variable_groups": variable_groups,
    }