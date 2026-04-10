# simulation/main.py
#
# this is the main simulation runner for a single scenario
# it connects all four layers together in the correct order:
#   1. agents generate demand (agents.py)
#   2. power flow evaluates grid response (powerflow.py)
#   3. optimiser reschedules loads if violations detected (scheduler.py)
#   4. results are saved to csv for the dashboard (dashboard.py)
#
# for running all three scenarios in parallel, use hpc/parallel_scenarios.py
# this file is useful for testing a single scenario with verbose output
# or for regenerating results without the mpi setup

import sys
import os
import csv
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.agents import GridDemandModel
from simulation.scenarios import get_scenario, list_scenarios
from grid.grid_model import create_grid
from grid.powerflow import run_powerflow
from optimization.scheduler import build_schedule, compute_targets

import opendssdirect as dss


def run_simulation(scenario_name, verbose=True):
    """
    runs the full closed-loop simulation for one scenario.
    each timestep goes through demand generation, power flow,
    optional optimisation, and result recording.

    parameters:
        scenario_name : string key matching a scenario in scenarios.py
        verbose       : if true, prints progress every 10 timesteps
                        and whenever a violation is detected

    returns a list of result dicts, one per timestep
    """
    scenario = get_scenario(scenario_name)

    if verbose:
        print(f"\n{'='*55}")
        print(f"running scenario: {scenario['name']}")
        print(f"  ev hubs:       {scenario['n_ev_hubs']}")
        print(f"  data centres:  {scenario['n_data_centers']}")
        print(f"  timesteps:     {scenario['timesteps']}")
        print(f"  weather mult:  {scenario['weather_multiplier']}")
        print(f"{'='*55}\n")

    # initialise mesa agent model and opendss grid
    demand_model = GridDemandModel(scenario=scenario)
    create_grid()

    results              = []
    total_violations     = 0
    total_optimizations  = 0
    total_opt_successes  = 0

    start_time = time.time()

    for t in range(scenario["timesteps"]):

        # ── stage 1: step agents forward ─────────────────────────────────
        # each agent updates its demand based on time of day and random events
        demand_model.step()

        # separate ev hub agents from data centre agents
        ev_agents = [a for a in demand_model.agents
                     if a.__class__.__name__ == "EVHubAgent"]
        dc_agents = [a for a in demand_model.agents
                     if a.__class__.__name__ == "DataCenterAgent"]

        ev_demands = [a.current_demand_mw   for a in ev_agents]
        dc_demands = [a.current_demand_mw   for a in dc_agents]

        ev_mw   = sum(ev_demands)
        ev_mvar = sum(a.current_demand_mvar for a in ev_agents)
        dc_mw   = sum(dc_demands)
        dc_mvar = sum(a.current_demand_mvar for a in dc_agents)

        # apply weather multiplier — higher in summer scenarios
        wm       = scenario["weather_multiplier"]
        ev_mw   *= wm
        ev_mvar *= wm
        dc_mw   *= wm
        dc_mvar *= wm

        # ── stage 2: run power flow ───────────────────────────────────────
        # inject demand into opendss and solve for bus voltages
        pf = run_powerflow(ev_mw, ev_mvar, dc_mw, dc_mvar)

        # ── stage 3: check for violations and trigger optimiser ───────────
        opt_result = None
        post_pf    = None

        if pf["n_violations"] > 0:
            total_violations    += pf["n_violations"]
            total_optimizations += 1

            # find the worst voltage across all monitored buses
            worst_voltage = min(
                v for v in [
                    pf["ev_bus_voltage_pu"],
                    pf["ai_bus_voltage_pu"],
                    pf["dist_bus_voltage_pu"]
                ] if v is not None
            )

            # compute voltage-adaptive demand reduction targets
            target_ev, target_dc = compute_targets(ev_mw, dc_mw, worst_voltage)

            # run the binary load scheduling optimiser
            opt_result = build_schedule(
                ev_demands=[d * wm for d in ev_demands],
                dc_demands=[d * wm for d in dc_demands],
                ev_capacity_mw=ev_mw,
                dc_capacity_mw=dc_mw,
                target_ev_mw=target_ev,
                target_dc_mw=target_dc,
                timestep=t
            )

            # ── stage 4: reintegrate optimised schedule ───────────────────
            # re-run power flow with the reduced demand to measure voltage recovery
            if opt_result["feasible"]:
                total_opt_successes += 1
                post_pf = run_powerflow(
                    opt_result["optimized_ev_mw"],
                    opt_result["optimized_ev_mw"] * 0.15,   # ev reactive power at 0.15 ratio
                    opt_result["optimized_dc_mw"],
                    opt_result["optimized_dc_mw"] * 0.10    # dc reactive power at 0.10 ratio
                )

        # ── record all metrics for this timestep ──────────────────────────
        record = {
            "timestep":                t,
            "scenario":                scenario_name,
            "ev_mw":                   round(ev_mw, 3),
            "dc_mw":                   round(dc_mw, 3),
            "total_mw":                round(ev_mw + dc_mw, 3),
            "ev_bus_voltage_pu":       pf["ev_bus_voltage_pu"],
            "ai_bus_voltage_pu":       pf["ai_bus_voltage_pu"],
            "dist_bus_voltage_pu":     pf["dist_bus_voltage_pu"],
            "transformer_loading_pct": pf["transformer_loading_pct"],
            "n_violations_pre":        pf["n_violations"],
            "voltage_violation":       pf["voltage_violation"],
            "transformer_overload":    pf["transformer_overload"],
            "optimization_triggered":  pf["n_violations"] > 0,
            "optimization_feasible":   opt_result["feasible"] if opt_result else None,
            "opt_runtime_sec":         opt_result["runtime_sec"] if opt_result else None,
            "demand_reduction_mw":     opt_result["demand_reduction_mw"] if opt_result else 0.0,
            "optimized_total_mw":      opt_result["optimized_total_mw"] if opt_result else None,
            "post_opt_ev_voltage":     post_pf["ev_bus_voltage_pu"] if post_pf else None,
            "post_opt_ai_voltage":     post_pf["ai_bus_voltage_pu"] if post_pf else None,
            "n_violations_post":       post_pf["n_violations"] if post_pf else None,
        }

        results.append(record)

        # print progress every 10 timesteps or whenever violations occur
        if verbose and (t % 10 == 0 or pf["n_violations"] > 0):
            violation_str = f"violations: {pf['n_violations']}" if pf["n_violations"] > 0 else "ok"
            opt_str       = f"-> opt: {opt_result['optimized_total_mw']:.1f} mw" if opt_result else ""
            print(
                f"  t={t:02d} | "
                f"ev: {ev_mw:6.1f} mw | "
                f"dc: {dc_mw:6.1f} mw | "
                f"v_ev: {pf['ev_bus_voltage_pu']:.3f} pu | "
                f"{violation_str} {opt_str}"
            )

    # summary statistics
    elapsed          = time.time() - start_time
    feasibility_rate = (
        total_opt_successes / total_optimizations * 100
        if total_optimizations > 0 else 100.0
    )

    if verbose:
        print(f"\n{'─'*55}")
        print(f"scenario complete: {scenario['name']}")
        print(f"  runtime:              {elapsed:.2f} sec")
        print(f"  total violations:     {total_violations}")
        print(f"  optimisations run:    {total_optimizations}")
        print(f"  feasibility rate:     {feasibility_rate:.1f}%")
        print(f"{'─'*55}\n")

    return results


def save_results(results, filename="simulation_results.csv"):
    """saves simulation results to csv at the project root."""
    if not results:
        print("no results to save")
        return

    filepath = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        filename
    )

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"results saved to {filepath}")


# entry point — runs all three main scenarios sequentially and saves to csv
if __name__ == "__main__":
    all_results = []

    for scenario_name in ["low_stress", "medium_stress", "high_stress"]:
        results = run_simulation(scenario_name, verbose=True)
        all_results.extend(results)

    save_results(all_results)

    print("\nall scenarios complete")
    print(f"total timesteps recorded: {len(all_results)}")
