# hpc/analyze_scaling.py
# Run this after collecting timing results from 1, 2, and 3 processes
# Produces the scaling table and chart for section 5.4

import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def load_timing(n_processes):
    filename = f"hpc_timing_np{n_processes}.json"
    if os.path.exists(filename):
        with open(filename) as f:
            return json.load(f)
    return None

def analyze():
    print("Loading timing results...")
    
    results = {}
    for n in [1, 2, 3]:
        data = load_timing(n)
        if data:
            results[n] = data
            print(f"  {n} process(es): {data['total_runtime_sec']:.2f}s")
        else:
            print(f"  {n} process(es): NOT FOUND - run with mpirun -n {n} first")
    
    if 1 not in results:
        print("\nERROR: Need baseline run with 1 process first")
        return
    
    baseline = results[1]["total_runtime_sec"]
    
    print(f"\n{'='*55}")
    print(f"{'Processes':<12} {'Runtime (s)':<14} {'Speedup':<12} {'Efficiency':<12}")
    print(f"{'='*55}")
    
    speedups = []
    efficiencies = []
    process_counts = []
    runtimes = []
    
    for n in sorted(results.keys()):
        runtime = results[n]["total_runtime_sec"]
        speedup = baseline / runtime
        efficiency = speedup / n * 100
        speedups.append(speedup)
        efficiencies.append(efficiency)
        process_counts.append(n)
        runtimes.append(runtime)
        print(f"{n:<12} {runtime:<14.2f} {speedup:<12.3f} {efficiency:<10.1f}%")
    
    print(f"{'='*55}")
    
    # Generate scaling chart
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        "Strong Scaling Results: MPI Parallel Scenario Execution\n"
        "IEEE 33-Bus Feeder, 3 Scenarios, 96 Timesteps Each",
        fontsize=12
    )
    
    # Runtime chart
    axes[0].bar(process_counts, runtimes, color="#2ecc71", alpha=0.8, edgecolor="black")
    axes[0].set_xlabel("Number of MPI Processes")
    axes[0].set_ylabel("Total Runtime (seconds)")
    axes[0].set_title("Total Runtime")
    axes[0].set_xticks(process_counts)
    axes[0].grid(True, alpha=0.3)
    
    # Speedup chart
    ideal = [float(n) for n in process_counts]
    axes[1].plot(process_counts, speedups, "bo-", linewidth=2,
                 markersize=8, label="Measured speedup")
    axes[1].plot(process_counts, ideal, "r--", linewidth=1.5, label="Ideal linear speedup")
    axes[1].set_xlabel("Number of MPI Processes")
    axes[1].set_ylabel("Speedup")
    axes[1].set_title("Speedup vs Ideal")
    axes[1].legend()
    axes[1].set_xticks(process_counts)
    axes[1].grid(True, alpha=0.3)
    
    # Efficiency chart
    axes[2].bar(process_counts, efficiencies, color="#3498db", alpha=0.8, edgecolor="black")
    axes[2].axhline(y=100, color="red", linestyle="--", linewidth=1.5, label="100% efficiency")
    axes[2].set_xlabel("Number of MPI Processes")
    axes[2].set_ylabel("Parallel Efficiency (%)")
    axes[2].set_title("Parallel Efficiency")
    axes[2].set_xticks(process_counts)
    axes[2].set_ylim(0, 120)
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig("data/hpc_scaling_results.png", dpi=150, bbox_inches="tight")
    print(f"\nScaling chart saved to data/hpc_scaling_results.png")
    
    # Save table as text for section 5.4
    with open("hpc_scaling_table.txt", "w") as f:
        f.write("Strong Scaling Results\n")
        f.write("="*55 + "\n")
        f.write(f"{'Processes':<12} {'Runtime (s)':<14} {'Speedup':<12} {'Efficiency'}\n")
        f.write("="*55 + "\n")
        for n, rt, sp, ef in zip(process_counts, runtimes, speedups, efficiencies):
            f.write(f"{n:<12} {rt:<14.2f} {sp:<12.3f} {ef:.1f}%\n")
    
    print("Scaling table saved to hpc_scaling_table.txt")

if __name__ == "__main__":
    analyze()