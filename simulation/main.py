# simulation/main.py
# Main simulation loop connecting all four layers:
# Agent-Based Demand → Power Flow → Optimization → Results
# Run this file to execute a full simulation scenario.

import sys
import os
import csv
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.agents import GridDemandModel
from simulation.scenarios import get_scenario, list_scenarios
from grid.grid_model import create_grid
from grid.powerflow import run_powerflow
from optimization.scheduler import build_schedule, compute_targets

import opendssdirect as dss


def run_simulation(scenario_name, verbose=True):
    """
    Runs a full simulation for a given scenario.

    Parameters:
        scenario_name : string key from scenarios.py
        verbose       : print timestep results if True

    Returns:
        list of result dictionaries, one per timestep
    """

    # ─────────────────────────────────────────
    # SETUP
    # ─────────────────────────────────────────
    scenario = get_scenario(scenario_name)

    if verbose:
        print(f"\n{'='*55}")
        print(f"Running scenario: {scenario['name']}")
        print(f"  EV hubs:       {scenario['n_ev_hubs']}")
        print(f"  Data centers:  {scenario['n_data_centers']}")
        print(f"  Timesteps:     {scenario['timesteps']}")
        print(f"  Weather mult:  {scenario['weather_multiplier']}")
        print(f"{'='*55}\n")

    # Initialize agent model
    demand_model = GridDemandModel(scenario=scenario)

    # Initialize OpenDSS grid
    create_grid()

    # Results storage
    results = []

    # Counters for summary
    total_violations = 0
    total_optimizations = 0
    total_opt_successes = 0

    # ─────────────────────────────────────────
    # SIMULATION LOOP
    # ─────────────────────────────────────────
    start_time = time.time()

    for t in range(scenario["timesteps"]):

        # STEP 1: Step agents forward
        demand_model.step()
        current = demand_model.demand_history[-1]

        # Separate EV and DC agent demands
        ev_agents = [
            a for a in demand_model.agents
            if a.__class__.__name__ == "EVHubAgent"
        ]
        dc_agents = [
            a for a in demand_model.agents
            if a.__class__.__name__ == "DataCenterAgent"
        ]

        ev_demands = [a.current_demand_mw for a in ev_agents]
        dc_demands = [a.current_demand_mw for a in dc_agents]

        ev_mw   = sum(ev_demands)
        ev_mvar = sum(a.current_demand_mvar for a in ev_agents)
        dc_mw   = sum(dc_demands)
        dc_mvar = sum(a.current_demand_mvar for a in dc_agents)

        # Apply weather multiplier
        wm = scenario["weather_multiplier"]
        ev_mw   *= wm
        ev_mvar *= wm
        dc_mw   *= wm
        dc_mvar *= wm

        # STEP 2: Run power flow
        pf = run_powerflow(ev_mw, ev_mvar, dc_mw, dc_mvar)

        # STEP 3: Optimization trigger
        opt_result = None
        post_pf = None

        if pf["n_violations"] > 0:
            total_violations += pf["n_violations"]
            total_optimizations += 1

            # Compute demand targets to restore stability
            worst_voltage = min(
            v for v in [
                pf["ev_bus_voltage_pu"],
                pf["ai_bus_voltage_pu"],
                pf["dist_bus_voltage_pu"]
            ] if v is not None
        )

            target_ev, target_dc = compute_targets(
                ev_mw, dc_mw, worst_voltage
            )

            # Run optimizer
            opt_result = build_schedule(
                ev_demands=[d * wm for d in ev_demands],
                dc_demands=[d * wm for d in dc_demands],
                ev_capacity_mw=ev_mw,
                dc_capacity_mw=dc_mw,
                target_ev_mw=target_ev,
                target_dc_mw=target_dc,
                timestep=t
            )

            if opt_result["feasible"]:
                total_opt_successes += 1

                # STEP 4: Reintegrate optimized schedule
                post_pf = run_powerflow(
                    opt_result["optimized_ev_mw"],
                    opt_result["optimized_ev_mw"] * 0.15,
                    opt_result["optimized_dc_mw"],
                    opt_result["optimized_dc_mw"] * 0.10
                )

        # ─────────────────────────────────────────
        # RECORD RESULTS
        # ─────────────────────────────────────────
        record = {
            # Timestep info
            "timestep": t,
            "scenario": scenario_name,

            # Demand
            "ev_mw": round(ev_mw, 3),
            "dc_mw": round(dc_mw, 3),
            "total_mw": round(ev_mw + dc_mw, 3),

            # Pre-optimization grid state
            "ev_bus_voltage_pu": pf["ev_bus_voltage_pu"],
            "ai_bus_voltage_pu": pf["ai_bus_voltage_pu"],
            "dist_bus_voltage_pu": pf["dist_bus_voltage_pu"],
            "transformer_loading_pct": pf["transformer_loading_pct"],
            "n_violations_pre": pf["n_violations"],
            "voltage_violation": pf["voltage_violation"],
            "transformer_overload": pf["transformer_overload"],

            # Optimization
            "optimization_triggered": pf["n_violations"] > 0,
            "optimization_feasible": opt_result["feasible"] if opt_result else None,
            "opt_runtime_sec": opt_result["runtime_sec"] if opt_result else None,
            "demand_reduction_mw": opt_result["demand_reduction_mw"] if opt_result else 0.0,
            "optimized_total_mw": opt_result["optimized_total_mw"] if opt_result else None,

            # Post-optimization grid state
            "post_opt_ev_voltage": post_pf["ev_bus_voltage_pu"] if post_pf else None,
            "post_opt_ai_voltage": post_pf["ai_bus_voltage_pu"] if post_pf else None,
            "n_violations_post": post_pf["n_violations"] if post_pf else None,
        }

        results.append(record)

        # Print progress
        if verbose and (t % 10 == 0 or pf["n_violations"] > 0):
            violation_str = f"VIOLATIONS: {pf['n_violations']}" if pf["n_violations"] > 0 else "OK"
            opt_str = f"→ OPT: {opt_result['optimized_total_mw']:.1f} MW" if opt_result else ""
            print(
                f"  t={t:02d} | "
                f"EV: {ev_mw:6.1f} MW | "
                f"DC: {dc_mw:6.1f} MW | "
                f"V_ev: {pf['ev_bus_voltage_pu']:.3f} pu | "
                f"{violation_str} {opt_str}"
            )

    # ─────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────
    elapsed = time.time() - start_time
    feasibility_rate = (
        total_opt_successes / total_optimizations * 100
        if total_optimizations > 0 else 100.0
    )

    if verbose:
        print(f"\n{'─'*55}")
        print(f"Scenario complete: {scenario['name']}")
        print(f"  Runtime:              {elapsed:.2f} sec")
        print(f"  Total violations:     {total_violations}")
        print(f"  Optimizations run:    {total_optimizations}")
        print(f"  Feasibility rate:     {feasibility_rate:.1f}%")
        print(f"{'─'*55}\n")

    return results


def save_results(results, filename="simulation_results.csv"):
    """Saves simulation results to CSV file."""
    if not results:
        print("No results to save.")
        return

    filepath = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        filename
    )

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"Results saved to {filepath}")


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":

    # Run all three main scenarios
    all_results = []

    for scenario_name in ["low_stress", "medium_stress", "high_stress"]:
        results = run_simulation(scenario_name, verbose=True)
        all_results.extend(results)

    # Save combined results
    save_results(all_results)

    print("\nAll scenarios complete.")
    print(f"Total timesteps recorded: {len(all_results)}")
