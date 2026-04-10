# optimization/scheduler.py
#
# this file contains the pulp binary load scheduling optimiser
# it is triggered by the simulation whenever a power flow detects voltage violations
#
# the optimiser decides which ev hubs and data centres to keep active this timestep
# and which ones to defer to a later time. the goal is to reduce total demand
# enough to bring voltage back within safe limits, while keeping as many
# loads running as possible to avoid unnecessary service disruption
#
# i used pulp with the cbc solver because it is open source, integrates
# directly with python, and handles the binary problem sizes here
# (up to 8 ev variables and 3 dc variables in high stress) very quickly
# each optimisation call typically completes in under 0.01 seconds

import pulp
import time

# voltage thresholds — same as in powerflow.py
# copied here so the scheduler can be tested independently
V_MIN       = 0.95
V_MAX       = 1.05
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
    solves a binary load scheduling problem to reduce total demand
    below the voltage-adaptive targets computed by compute_targets().

    each agent is represented by a binary decision variable:
        1 = agent stays active this timestep
        0 = agent is deferred to a later timestep

    the objective minimises total deferred load — so the solver keeps
    as many loads running as possible while satisfying the demand targets.
    minimum active constraints ensure service continuity for both load types.

    parameters:
        ev_demands     : list of mw demand per ev hub agent
        dc_demands     : list of mw demand per data centre agent
        ev_capacity_mw : current total ev demand before optimisation
        dc_capacity_mw : current total dc demand before optimisation
        target_ev_mw   : maximum ev demand allowed after optimisation
        target_dc_mw   : maximum dc demand allowed after optimisation
        timestep       : current timestep index used for problem naming

    returns a dict with the schedule, feasibility flag, and demand metrics
    """
    start_time = time.time()

    n_ev = len(ev_demands)
    n_dc = len(dc_demands)

    # create the pulp minimisation problem
    prob = pulp.LpProblem(f"LoadScheduling_t{timestep}", pulp.LpMinimize)

    # one binary variable per agent
    # ev_{i} = 1 means ev hub i stays active, 0 means it is deferred
    x_ev = [pulp.LpVariable(f"ev_{i}", cat="Binary") for i in range(n_ev)]
    x_dc = [pulp.LpVariable(f"dc_{i}", cat="Binary") for i in range(n_dc)]

    # objective: minimise the total mw that gets deferred
    # (1 - x) gives the deferred fraction for each agent
    prob += pulp.lpSum(
        [(1 - x_ev[i]) * ev_demands[i] for i in range(n_ev)] +
        [(1 - x_dc[i]) * dc_demands[i] for i in range(n_dc)]
    )

    # constraint: total active ev demand must stay below the voltage-adaptive target
    prob += pulp.lpSum([x_ev[i] * ev_demands[i] for i in range(n_ev)]) <= target_ev_mw

    # constraint: total active dc demand must stay below the voltage-adaptive target
    prob += pulp.lpSum([x_dc[i] * dc_demands[i] for i in range(n_dc)]) <= target_dc_mw

    # constraint: at least 30% of ev hubs must stay active for service continuity
    # this prevents the optimiser from deferring all charging during peak hours
    prob += pulp.lpSum(x_ev) >= max(0, int(n_ev * 0.3))

    # constraint: at least 50% of data centres must stay active
    # data centres are critical infrastructure and cannot all be paused
    prob += pulp.lpSum(x_dc) >= max(0, int(n_dc * 0.5))

    # solve using the cbc solver — msg=0 suppresses the solver console output
    solver = pulp.PULP_CBC_CMD(msg=0)
    status  = prob.solve(solver)
    runtime = time.time() - start_time

    feasible = pulp.LpStatus[status] == "Optimal"

    if feasible:
        # extract the binary schedule — 1 = active, 0 = deferred
        ev_schedule = [int(pulp.value(x_ev[i])) for i in range(n_ev)]
        dc_schedule = [int(pulp.value(x_dc[i])) for i in range(n_dc)]

        # calculate how much demand remains after deferral
        optimized_ev_mw = sum(ev_demands[i] * ev_schedule[i] for i in range(n_ev))
        optimized_dc_mw = sum(dc_demands[i] * dc_schedule[i] for i in range(n_dc))

        ev_deferred = sum(1 for s in ev_schedule if s == 0)
        dc_deferred = sum(1 for s in dc_schedule if s == 0)

        # total mw successfully deferred by this optimisation cycle
        demand_reduction_mw = (
            sum(ev_demands) + sum(dc_demands)
        ) - (optimized_ev_mw + optimized_dc_mw)

    else:
        # fallback if no optimal solution found — keep everything active
        # this counts as infeasible but does not crash the simulation
        ev_schedule         = [1] * n_ev
        dc_schedule         = [1] * n_dc
        optimized_ev_mw     = sum(ev_demands)
        optimized_dc_mw     = sum(dc_demands)
        ev_deferred         = 0
        dc_deferred         = 0
        demand_reduction_mw = 0.0

    return {
        "feasible":            feasible,
        "status":              pulp.LpStatus[status],
        "runtime_sec":         round(runtime, 4),
        "ev_schedule":         ev_schedule,
        "dc_schedule":         dc_schedule,
        "optimized_ev_mw":     round(optimized_ev_mw, 3),
        "optimized_dc_mw":     round(optimized_dc_mw, 3),
        "optimized_total_mw":  round(optimized_ev_mw + optimized_dc_mw, 3),
        "demand_reduction_mw": round(demand_reduction_mw, 3),
        "ev_agents_deferred":  ev_deferred,
        "dc_agents_deferred":  dc_deferred,
        "timestep":            timestep,
    }


def compute_targets(ev_mw, dc_mw, voltage_pu, reduction_factor=0.85):
    """
    computes how much we need to reduce demand to bring voltage back to safety.
    the reduction is voltage-adaptive — more aggressive when voltage is lower.

    at 0.90-0.95 pu we reduce by 15 percent (mild violation)
    at 0.85-0.90 pu we reduce by 20 percent (moderate violation)
    below 0.85 pu we reduce by 30 percent (severe violation)

    these thresholds are documented in section 5.3.1 of the report and match
    the implementation notes in the methodology section

    parameters:
        ev_mw            : current total ev demand in mw
        dc_mw            : current total dc demand in mw
        voltage_pu       : worst-case bus voltage at this timestep in per unit
        reduction_factor : default reduction of 15 percent (0.85 factor)

    returns target_ev_mw and target_dc_mw as a tuple
    """
    if voltage_pu < 0.85:
        factor = 0.70       # 30% reduction for severe voltage collapse
    elif voltage_pu < 0.90:
        factor = 0.80       # 20% reduction for moderate violation
    else:
        factor = reduction_factor   # 15% reduction for mild violation

    return ev_mw * factor, dc_mw * factor


# quick test — run this file directly to check the optimiser works correctly
# and that the binary schedule and demand reduction numbers make sense
if __name__ == "__main__":
    print("testing optimiser with a sample violation scenario\n")

    # sample agent demands at a stressed timestep
    ev_demands = [12.5, 18.3, 9.7, 15.2, 11.8]   # 5 ev hubs in mw
    dc_demands = [72.4, 85.1, 68.9]                # 3 data centres in mw

    current_ev = sum(ev_demands)
    current_dc = sum(dc_demands)

    print(f"pre-optimisation:")
    print(f"  total ev demand:  {current_ev:.1f} mw")
    print(f"  total dc demand:  {current_dc:.1f} mw")
    print(f"  total demand:     {current_ev + current_dc:.1f} mw")

    # compute targets assuming voltage is at 0.87 pu (moderate violation)
    target_ev, target_dc = compute_targets(current_ev, current_dc, voltage_pu=0.87)

    print(f"\noptimisation targets (voltage = 0.87 pu, 20% reduction):")
    print(f"  target ev:  {target_ev:.1f} mw")
    print(f"  target dc:  {target_dc:.1f} mw")

    result = build_schedule(
        ev_demands=ev_demands,
        dc_demands=dc_demands,
        ev_capacity_mw=current_ev,
        dc_capacity_mw=current_dc,
        target_ev_mw=target_ev,
        target_dc_mw=target_dc,
        timestep=42
    )

    print(f"\noptimisation results:")
    print(f"  status:             {result['status']}")
    print(f"  feasible:           {result['feasible']}")
    print(f"  runtime:            {result['runtime_sec']} sec")
    print(f"  optimised ev mw:    {result['optimized_ev_mw']}")
    print(f"  optimised dc mw:    {result['optimized_dc_mw']}")
    print(f"  total after opt:    {result['optimized_total_mw']} mw")
    print(f"  demand reduced by:  {result['demand_reduction_mw']} mw")
    print(f"  ev hubs deferred:   {result['ev_agents_deferred']}")
    print(f"  dc agents deferred: {result['dc_agents_deferred']}")
    print(f"  ev schedule:        {result['ev_schedule']}")
    print(f"  dc schedule:        {result['dc_schedule']}")
