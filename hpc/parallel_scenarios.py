# hpc/parallel_scenarios.py
#
# MPI-based parallel scenario execution for the Smart City Grid Simulation.
# Gloria Paraschivoiu · IE University · April 2026
#
# PURPOSE:
#   Distributes the three simulation scenarios across MPI processes so they
#   run simultaneously rather than sequentially. This is the core HPC
#   contribution of the project — see Section 5.8 and Section 6.4 of the report.
#
# HOW TO RUN:
#   Sequential baseline (1 process):  python hpc/parallel_scenarios.py
#   Parallel (2 processes):           mpirun -n 2 python hpc/parallel_scenarios.py
#   Parallel (3 processes):           mpirun -n 3 python hpc/parallel_scenarios.py
#
# PARALLELISATION STRATEGY:
#   Each MPI process runs one scenario independently. The three scenarios
#   share no state and require no inter-process communication during
#   simulation — only a single gather call at completion to collect results
#   at rank 0. This makes scenario-parallel execution the natural and
#   efficient strategy for this architecture.
#
# SCALING RESULTS (Kaggle cloud, 2 physical CPU cores):
#   1 process:  16.61s  speedup 1.00x  efficiency 100.0%
#   2 processes: 7.19s  speedup 2.31x  efficiency 115.6% (environment-specific)
#   3 processes: 11.25s speedup 1.48x  efficiency 49.2%  (load imbalance)

import time
import os
import sys
import json

# add project root to path so all modules are importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mpi4py import MPI
import pandas as pd

from simulation.scenarios import SCENARIOS
from simulation.agents import GridDemandModel
from grid.grid_model import create_grid
from grid.powerflow import run_powerflow

# corrected import — build_schedule and compute_targets are the actual
# function names exported by scheduler.py
from optimization.scheduler import build_schedule, compute_targets


def run_scenario(scenario_name, scenario_params):
    """
    Run a single complete scenario and return timestep results with timing.

    Each call runs 96 timesteps (24-hour simulation) for results, or 960
    timesteps for HPC scaling experiments. The same closed-loop logic
    applies at every timestep:
        1. Step agents to generate demand
        2. Run OpenDSS power flow
        3. Check for voltage violations
        4. If violations detected, run PuLP optimiser
        5. Record all metrics

    Parameters:
        scenario_name   : string key matching SCENARIOS dict
        scenario_params : full scenario parameter dictionary

    Returns:
        results  : list of dicts, one per timestep
        runtime  : total wall-clock time in seconds
    """
    start_time = time.time()
    rank = MPI.COMM_WORLD.Get_rank()

    print(f"[Rank {rank}] Starting scenario: {scenario_name}")

    # initialise the OpenDSS IEEE 33-bus distribution grid
    dss = create_grid()

    # initialise the Mesa agent model with scenario parameters and fixed seed
    # seed 42 is used across all scenarios for full reproducibility
    model = GridDemandModel(scenario=scenario_params, seed=scenario_params["seed"])

    results = []

    for t in range(scenario_params["timesteps"]):

        # ── STAGE 1: DEMAND GENERATION ───────────────────────────────────
        # step all agents forward — EVHubAgents generate time-of-day demand
        # with surge events, DataCenterAgents accumulate step-load increases
        model.step()

        # separate agent types to track EV and DC demand independently
        ev_agents = [a for a in model.agents if a.__class__.__name__ == "EVHubAgent"]
        dc_agents = [a for a in model.agents if a.__class__.__name__ == "DataCenterAgent"]

        # apply weather multiplier to aggregate demand
        weather = scenario_params.get("weather_multiplier", 1.0)
        ev_mw   = sum(a.current_demand_mw   for a in ev_agents) * weather
        ev_mvar = sum(a.current_demand_mvar for a in ev_agents) * weather
        dc_mw   = sum(a.current_demand_mw   for a in dc_agents) * weather
        dc_mvar = sum(a.current_demand_mvar for a in dc_agents) * weather

        # ── STAGE 2: POWER FLOW ──────────────────────────────────────────
        # inject aggregate demand into OpenDSS and run snapshot power flow
        # returns per-unit voltages at all monitored buses
        pf = run_powerflow(ev_mw, ev_mvar, dc_mw, dc_mvar)

        # ── STAGE 3: OPTIMISATION TRIGGER ────────────────────────────────
        # check whether any monitored bus has violated the 0.95-1.05 pu range
        opt_result = None

        if pf["n_violations"] > 0:
            # find worst-case voltage across all monitored buses
            monitored_voltages = [
                v for v in [
                    pf["ev_bus_voltage_pu"],
                    pf["ai_bus_voltage_pu"],
                    pf["dist_bus_voltage_pu"]
                ] if v is not None
            ]
            worst_voltage = min(monitored_voltages)

            # compute voltage-adaptive demand reduction targets
            # 15% reduction at 0.90-0.95 pu, 20% at 0.85-0.90 pu, 30% below 0.85 pu
            target_ev_mw, target_dc_mw = compute_targets(
                ev_mw, dc_mw, worst_voltage
            )

            # extract per-agent demand lists for the binary scheduler
            ev_demands = [a.current_demand_mw * weather for a in ev_agents]
            dc_demands = [a.current_demand_mw * weather for a in dc_agents]

            # ── STAGE 4: LOAD RESCHEDULING ───────────────────────────────
            # PuLP binary MILP: decide which agents to keep active vs defer
            # objective: minimise deferred load while restoring voltage safety
            opt_result = build_schedule(
                ev_demands=ev_demands,
                dc_demands=dc_demands,
                ev_capacity_mw=ev_mw,
                dc_capacity_mw=dc_mw,
                target_ev_mw=target_ev_mw,
                target_dc_mw=target_dc_mw,
                timestep=t
            )

            # ── STAGE 5: REINTEGRATION ───────────────────────────────────
            # re-run power flow with optimised demand to measure voltage recovery
            if opt_result["feasible"]:
                pf_post = run_powerflow(
                    opt_result["optimized_ev_mw"],
                    ev_mvar * (opt_result["optimized_ev_mw"] / ev_mw if ev_mw > 0 else 0),
                    opt_result["optimized_dc_mw"],
                    dc_mvar * (opt_result["optimized_dc_mw"] / dc_mw if dc_mw > 0 else 0)
                )
                opt_result["post_opt_voltage"] = pf_post["ev_bus_voltage_pu"]
                opt_result["post_opt_ai_voltage"] = pf_post["ai_bus_voltage_pu"]
            else:
                opt_result["post_opt_voltage"] = None
                opt_result["post_opt_ai_voltage"] = None

        # ── RECORD RESULTS ────────────────────────────────────────────────
        results.append({
            "scenario":              scenario_name,
            "timestep":              t,
            "ev_mw":                 round(ev_mw, 3),
            "dc_mw":                 round(dc_mw, 3),
            "total_mw":              round(ev_mw + dc_mw, 3),
            "ev_bus_voltage_pu":     pf["ev_bus_voltage_pu"],
            "ai_bus_voltage_pu":     pf["ai_bus_voltage_pu"],
            "dist_bus_voltage_pu":   pf["dist_bus_voltage_pu"],
            "n_violations_pre":      pf["n_violations"],
            "optimization_triggered": opt_result is not None,
            "optimization_feasible":  opt_result["feasible"] if opt_result else False,
            "demand_reduction_mw":    opt_result["demand_reduction_mw"] if opt_result else 0.0,
            "post_opt_ev_voltage":    opt_result.get("post_opt_voltage") if opt_result else None,
            "post_opt_ai_voltage":    opt_result.get("post_opt_ai_voltage") if opt_result else None,
        })

    runtime = time.time() - start_time
    print(f"[Rank {rank}] Completed {scenario_name} in {runtime:.2f}s")

    return results, runtime


def main():
    """
    Main MPI execution function.

    When run with 1 process: executes all scenarios sequentially (baseline).
    When run with N processes: each rank executes one scenario in parallel.
    Results are gathered to rank 0 for serialisation and CSV export.
    """
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    # the three scenarios used in the study — one per MPI process
    scenario_names = ["low_stress", "medium_stress", "high_stress"]

    all_results  = []
    all_runtimes = {}
    global_start = time.time()

    if size == 1:
        # ── SEQUENTIAL BASELINE ───────────────────────────────────────────
        # rank 0 runs all scenarios one after another
        # this is the timing baseline for speedup calculations
        print(f"[Sequential] Running {len(scenario_names)} scenarios on 1 process")
        for name in scenario_names:
            results, runtime = run_scenario(name, SCENARIOS[name])
            all_results.extend(results)
            all_runtimes[name] = runtime

    else:
        # ── PARALLEL EXECUTION ────────────────────────────────────────────
        # each rank picks one scenario by its rank index
        # no inter-process communication occurs during simulation
        if rank < len(scenario_names):
            scenario_name = scenario_names[rank]
            local_results, local_runtime = run_scenario(
                scenario_name, SCENARIOS[scenario_name]
            )
        else:
            # extra processes beyond 3 have no scenario assigned
            local_results  = []
            local_runtime  = 0.0
            print(f"[Rank {rank}] No scenario assigned — idle")

        # single gather call collects all results at rank 0
        # this is the only inter-process communication in the entire run
        gathered_results  = comm.gather(local_results,  root=0)
        gathered_runtimes = comm.gather(
            {scenario_names[rank] if rank < len(scenario_names) else "idle": local_runtime},
            root=0
        )

        if rank == 0:
            for r in gathered_results:
                all_results.extend(r)
            for rt in gathered_runtimes:
                all_runtimes.update(rt)

    total_runtime = time.time() - global_start

    # ── SAVE RESULTS (rank 0 only) ────────────────────────────────────────
    if rank == 0:
        # save simulation results CSV — used by dashboard and analysis
        df = pd.DataFrame(all_results)
        df.to_csv("simulation_results.csv", index=False)
        print(f"\nResults saved to simulation_results.csv")

        # save timing JSON for HPC scaling analysis
        timing = {
            "n_processes":       size,
            "total_runtime_sec": round(total_runtime, 3),
            "scenario_runtimes": {k: round(v, 3) for k, v in all_runtimes.items()},
            "timestamp":         time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(f"hpc_timing_np{size}.json", "w") as f:
            json.dump(timing, f, indent=2)

        print(f"\n{'='*52}")
        print(f"  HPC SCALING RESULTS")
        print(f"{'='*52}")
        print(f"  Processes:     {size}")
        print(f"  Total runtime: {total_runtime:.2f} seconds")
        for name, rt in all_runtimes.items():
            print(f"  {name}: {rt:.2f}s")
        print(f"  Timing saved:  hpc_timing_np{size}.json")
        print(f"{'='*52}\n")


if __name__ == "__main__":
    main()