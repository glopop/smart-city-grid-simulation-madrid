# optimization/scheduler.py
# PuLP-based binary load scheduling optimizer.
# Triggered when power flow detects stability violations.
# Attempts to reschedule flexible loads to restore grid stability.

import pulp
import time

# ─────────────────────────────────────────
# OPTIMIZATION THRESHOLDS
# ─────────────────────────────────────────
V_MIN = 0.95
V_MAX = 1.05
TRAFO_LIMIT = 100.0


def build_schedule(
    ev_demands,
    dc_demands,
    ev_capacity_mw,
    dc_capacity_mw,
    target_ev_mw,
    target_dc_mw,
    timestep=0
):
    """
    Solves a binary load scheduling problem to reduce
    aggregate demand below stability thresholds.

    Parameters:
        ev_demands     : list of MW demand per EV hub agent
        dc_demands     : list of MW demand per data center agent
        ev_capacity_mw : maximum allowable total EV demand after optimization
        dc_capacity_mw : maximum allowable total DC demand after optimization
        target_ev_mw   : target EV demand to restore voltage stability
        target_dc_mw   : target DC demand to restore voltage stability
        timestep       : current simulation timestep (for logging)

    Returns:
        dict with optimization results and recommended schedules
    """

    start_time = time.time()

    n_ev = len(ev_demands)
    n_dc = len(dc_demands)

    # ─────────────────────────────────────────
    # DEFINE PROBLEM
    # ─────────────────────────────────────────
    prob = pulp.LpProblem(f"LoadScheduling_t{timestep}", pulp.LpMinimize)

    # Binary decision variables
    # x_ev[i] = 1 means EV hub i is active this timestep
    # x_ev[i] = 0 means EV hub i is deferred
    x_ev = [
        pulp.LpVariable(f"ev_{i}", cat="Binary")
        for i in range(n_ev)
    ]
    x_dc = [
        pulp.LpVariable(f"dc_{i}", cat="Binary")
        for i in range(n_dc)
    ]

    # ─────────────────────────────────────────
    # OBJECTIVE: minimize total deferred load
    # (prefer to keep as many loads active as possible
    # while staying within stability limits)
    # ─────────────────────────────────────────
    prob += pulp.lpSum(
        [(1 - x_ev[i]) * ev_demands[i] for i in range(n_ev)] +
        [(1 - x_dc[i]) * dc_demands[i] for i in range(n_dc)]
    )

    # ─────────────────────────────────────────
    # CONSTRAINTS
    # ─────────────────────────────────────────

    # Total EV demand must stay below target
    prob += pulp.lpSum([x_ev[i] * ev_demands[i] for i in range(n_ev)]) <= target_ev_mw

    # Total DC demand must stay below target
    prob += pulp.lpSum([x_dc[i] * dc_demands[i] for i in range(n_dc)]) <= target_dc_mw

    # At least 30% of EV hubs must remain active (service continuity)
    prob += pulp.lpSum(x_ev) >= max(0, int(n_ev * 0.3))

    # At least 50% of data centers must remain active (critical infrastructure)
    prob += pulp.lpSum(x_dc) >= max(0, int(n_dc * 0.5))

    # ─────────────────────────────────────────
    # SOLVE
    # ─────────────────────────────────────────
    solver = pulp.PULP_CBC_CMD(msg=0)  # msg=0 suppresses solver output
    status = prob.solve(solver)
    runtime = time.time() - start_time

    feasible = pulp.LpStatus[status] == "Optimal"

    # ─────────────────────────────────────────
    # EXTRACT RESULTS
    # ─────────────────────────────────────────
    if feasible:
        ev_schedule = [int(pulp.value(x_ev[i])) for i in range(n_ev)]
        dc_schedule = [int(pulp.value(x_dc[i])) for i in range(n_dc)]

        optimized_ev_mw = sum(
            ev_demands[i] * ev_schedule[i] for i in range(n_ev)
        )
        optimized_dc_mw = sum(
            dc_demands[i] * dc_schedule[i] for i in range(n_dc)
        )

        ev_deferred = sum(1 for s in ev_schedule if s == 0)
        dc_deferred = sum(1 for s in dc_schedule if s == 0)

        demand_reduction_mw = (
            sum(ev_demands) + sum(dc_demands)
        ) - (optimized_ev_mw + optimized_dc_mw)

    else:
        # Fallback: defer highest demand agents manually
        ev_schedule = [1] * n_ev
        dc_schedule = [1] * n_dc
        optimized_ev_mw = sum(ev_demands)
        optimized_dc_mw = sum(dc_demands)
        ev_deferred = 0
        dc_deferred = 0
        demand_reduction_mw = 0.0

    return {
        "feasible": feasible,
        "status": pulp.LpStatus[status],
        "runtime_sec": round(runtime, 4),
        "ev_schedule": ev_schedule,
        "dc_schedule": dc_schedule,
        "optimized_ev_mw": round(optimized_ev_mw, 3),
        "optimized_dc_mw": round(optimized_dc_mw, 3),
        "optimized_total_mw": round(optimized_ev_mw + optimized_dc_mw, 3),
        "demand_reduction_mw": round(demand_reduction_mw, 3),
        "ev_agents_deferred": ev_deferred,
        "dc_agents_deferred": dc_deferred,
        "timestep": timestep,
    }


def compute_targets(ev_mw, dc_mw, voltage_pu, reduction_factor=0.85):
    """
    Computes target demand levels needed to restore voltage stability.
    Scales down current demand by reduction factor when violations detected.

    Parameters:
        ev_mw            : current total EV demand in MW
        dc_mw            : current total DC demand in MW
        voltage_pu       : current worst-case bus voltage in per unit
        reduction_factor : how aggressively to reduce demand (default 15%)

    Returns:
        target_ev_mw, target_dc_mw
    """
    # More aggressive reduction if voltage is severely low
    if voltage_pu < 0.85:
        factor = 0.70  # reduce by 30%
    elif voltage_pu < 0.90:
        factor = 0.80  # reduce by 20%
    else:
        factor = reduction_factor  # reduce by 15%

    return ev_mw * factor, dc_mw * factor


# ─────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("Testing optimizer with sample violation scenario...\n")

    # Simulate agent demands at a stressed timestep
    ev_demands = [12.5, 18.3, 9.7, 15.2, 11.8]   # 5 EV hubs in MW
    dc_demands = [72.4, 85.1, 68.9]                # 3 data centers in MW

    current_ev_total = sum(ev_demands)
    current_dc_total = sum(dc_demands)

    print(f"Pre-optimization:")
    print(f"  Total EV demand:  {current_ev_total:.1f} MW")
    print(f"  Total DC demand:  {current_dc_total:.1f} MW")
    print(f"  Total demand:     {current_ev_total + current_dc_total:.1f} MW")

    # Compute targets assuming voltage is at 0.87 pu
    target_ev, target_dc = compute_targets(
        current_ev_total,
        current_dc_total,
        voltage_pu=0.87
    )

    print(f"\nOptimization targets:")
    print(f"  Target EV:  {target_ev:.1f} MW")
    print(f"  Target DC:  {target_dc:.1f} MW")

    # Run optimizer
    result = build_schedule(
        ev_demands=ev_demands,
        dc_demands=dc_demands,
        ev_capacity_mw=current_ev_total,
        dc_capacity_mw=current_dc_total,
        target_ev_mw=target_ev,
        target_dc_mw=target_dc,
        timestep=42
    )

    print(f"\nOptimization results:")
    print(f"  Status:             {result['status']}")
    print(f"  Feasible:           {result['feasible']}")
    print(f"  Runtime:            {result['runtime_sec']} sec")
    print(f"  Optimized EV MW:    {result['optimized_ev_mw']}")
    print(f"  Optimized DC MW:    {result['optimized_dc_mw']}")
    print(f"  Total after opt:    {result['optimized_total_mw']} MW")
    print(f"  Demand reduced by:  {result['demand_reduction_mw']} MW")
    print(f"  EV hubs deferred:   {result['ev_agents_deferred']}")
    print(f"  DC agents deferred: {result['dc_agents_deferred']}")
    print(f"  EV schedule:        {result['ev_schedule']}")
    print(f"  DC schedule:        {result['dc_schedule']}")
