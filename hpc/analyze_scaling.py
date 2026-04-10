# hpc/analyze_scaling.py
#
# this script reads the timing json files produced by parallel_scenarios.py
# and computes speedup and parallel efficiency for the hpc scaling analysis
#
# run parallel_scenarios.py with 1, 2, and 3 processes first to generate:
#   hpc_timing_np1.json
#   hpc_timing_np2.json
#   hpc_timing_np3.json
#
# then run this script to produce the scaling table and chart
# the chart is saved to data/hpc_scaling_results.png and used in the report
# results are also written to hpc_scaling_table.txt for reference
#
# speedup = baseline_runtime / parallel_runtime
# parallel efficiency = speedup / n_processes * 100
# these follow the standard definitions from amdahl 1967

import json
import os
import matplotlib
matplotlib.use('Agg')   # use non-interactive backend so it works without a display
import matplotlib.pyplot as plt


def load_timing(n_processes):
    """
    loads the timing json file for a given process count
    returns none if the file does not exist yet
    """
    filename = f"hpc_timing_np{n_processes}.json"
    if os.path.exists(filename):
        with open(filename) as f:
            return json.load(f)
    return None


def analyze():
    """
    loads all available timing files, computes scaling metrics,
    prints the results table, and saves the three-panel scaling chart
    """
    print("loading timing results...")

    results = {}
    for n in [1, 2, 3]:
        data = load_timing(n)
        if data:
            results[n] = data
            print(f"  {n} process(es): {data['total_runtime_sec']:.2f}s")
        else:
            print(f"  {n} process(es): not found — run with mpirun -n {n} first")

    # need the single-process baseline to compute speedup
    if 1 not in results:
        print("\nerror: need baseline run with 1 process first")
        return

    baseline = results[1]["total_runtime_sec"]

    print(f"\n{'='*55}")
    print(f"{'processes':<12} {'runtime (s)':<14} {'speedup':<12} {'efficiency':<12}")
    print(f"{'='*55}")

    speedups      = []
    efficiencies  = []
    process_counts = []
    runtimes      = []

    for n in sorted(results.keys()):
        runtime    = results[n]["total_runtime_sec"]
        speedup    = baseline / runtime
        efficiency = speedup / n * 100
        speedups.append(speedup)
        efficiencies.append(efficiency)
        process_counts.append(n)
        runtimes.append(runtime)
        print(f"{n:<12} {runtime:<14.2f} {speedup:<12.3f} {efficiency:<10.1f}%")

    print(f"{'='*55}")

    # three-panel chart: runtime, speedup vs ideal, parallel efficiency
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        "Strong Scaling Results: MPI Parallel Scenario Execution\n"
        "IEEE 33-Bus Feeder, 3 Scenarios, 960 Timesteps Each",
        fontsize=12
    )

    # panel 1: total runtime bar chart
    axes[0].bar(process_counts, runtimes, color="#2ecc71", alpha=0.8, edgecolor="black")
    axes[0].set_xlabel("Number of MPI Processes")
    axes[0].set_ylabel("Total Runtime (seconds)")
    axes[0].set_title("Total Runtime")
    axes[0].set_xticks(process_counts)
    axes[0].grid(True, alpha=0.3)

    # panel 2: measured speedup vs ideal linear speedup
    # ideal = n processes gives exactly n times speedup
    ideal = [float(n) for n in process_counts]
    axes[1].plot(process_counts, speedups, "bo-", linewidth=2,
                 markersize=8, label="Measured speedup")
    axes[1].plot(process_counts, ideal, "r--", linewidth=1.5,
                 label="Ideal linear speedup")
    axes[1].set_xlabel("Number of MPI Processes")
    axes[1].set_ylabel("Speedup")
    axes[1].set_title("Speedup vs Ideal")
    axes[1].legend()
    axes[1].set_xticks(process_counts)
    axes[1].grid(True, alpha=0.3)

    # panel 3: parallel efficiency bar chart
    # 100% means perfect scaling, below 100% means some overhead or imbalance
    axes[2].bar(process_counts, efficiencies, color="#3498db", alpha=0.8, edgecolor="black")
    axes[2].axhline(y=100, color="red", linestyle="--", linewidth=1.5,
                    label="100% efficiency")
    axes[2].set_xlabel("Number of MPI Processes")
    axes[2].set_ylabel("Parallel Efficiency (%)")
    axes[2].set_title("Parallel Efficiency")
    axes[2].set_xticks(process_counts)
    axes[2].set_ylim(0, 180)   # extended to show superlinear result at 2 processes
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("data/hpc_scaling_results.png", dpi=150, bbox_inches="tight")
    print(f"\nscaling chart saved to data/hpc_scaling_results.png")

    # save plain text table for reference
    with open("hpc_scaling_table.txt", "w") as f:
        f.write("strong scaling results\n")
        f.write("=" * 55 + "\n")
        f.write(f"{'processes':<12} {'runtime (s)':<14} {'speedup':<12} {'efficiency'}\n")
        f.write("=" * 55 + "\n")
        for n, rt, sp, ef in zip(process_counts, runtimes, speedups, efficiencies):
            f.write(f"{n:<12} {rt:<14.2f} {sp:<12.3f} {ef:.1f}%\n")

    print("scaling table saved to hpc_scaling_table.txt")


if __name__ == "__main__":
    analyze()
