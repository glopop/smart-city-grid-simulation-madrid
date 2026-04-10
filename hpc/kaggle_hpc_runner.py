import subprocess
import sys
import os
import time
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

env = os.environ.copy()
env["PYTHONPATH"] = "/kaggle/working/capstoneproject" 
results = {}

# ── Run all three experiments ──
for n_procs, extra_args in [
    (1, []),
    (2, []),
    (3, ["--oversubscribe"])
]:
    print("=" * 50)
    print(f"RUN {n_procs}: {n_procs} process(es)")
    print("=" * 50)

    if n_procs == 1:
        cmd = [sys.executable,
               "/kaggle/working/capstoneproject/hpc/parallel_scenarios.py"]
    else:
        cmd = ["mpirun", "--allow-run-as-root"] + extra_args + [
            "-n", str(n_procs),
            sys.executable,
            "/kaggle/working/capstoneproject/hpc/parallel_scenarios.py"
        ]

    start = time.time()
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd="/kaggle/working", env=env
    )
    elapsed = time.time() - start

    print("STDOUT:")
    print(result.stdout)
    if result.stderr and "error" in result.stderr.lower():
        print("STDERR:")
        print(result.stderr[-500:])
    print(f"Wall clock: {elapsed:.2f}s\n")

    timing_file = f"/kaggle/working/hpc_timing_np{n_procs}.json"
    if os.path.exists(timing_file):
        with open(timing_file) as f:
            data = json.load(f)
        results[n_procs] = data

# ── Summary table ──
print("=" * 55)
print("FINAL SCALING RESULTS")
print("=" * 55)
baseline = results[1]["total_runtime_sec"]
process_counts = sorted(results.keys())
runtimes   = [results[n]["total_runtime_sec"] for n in process_counts]
speedups   = [baseline / r for r in runtimes]
efficiencies = [speedups[i] / process_counts[i] * 100 for i in range(len(process_counts))]

print(f"{'Processes':<12} {'Runtime (s)':<14} {'Speedup':<12} {'Efficiency'}")
print("-" * 55)
for n, rt, sp, ef in zip(process_counts, runtimes, speedups, efficiencies):
    print(f"{n:<12} {rt:<14.3f} {sp:<12.3f} {ef:.1f}%")
print("=" * 55)

# ── Generate chart ──
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle(
    "Strong Scaling Results: MPI Parallel Scenario Execution\n"
    "IEEE 33-Bus Feeder, 3 Scenarios, 960 Timesteps Each",
    fontsize=12
)

axes[0].bar(process_counts, runtimes, color="#2ecc71", alpha=0.8, edgecolor="black")
axes[0].set_xlabel("Number of MPI Processes")
axes[0].set_ylabel("Total Runtime (seconds)")
axes[0].set_title("Total Runtime")
axes[0].set_xticks(process_counts)
axes[0].grid(True, alpha=0.3)

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

axes[2].bar(process_counts, efficiencies, color="#3498db",
            alpha=0.8, edgecolor="black")
axes[2].axhline(y=100, color="red", linestyle="--",
                linewidth=1.5, label="100% efficiency")
axes[2].set_xlabel("Number of MPI Processes")
axes[2].set_ylabel("Parallel Efficiency (%)")
axes[2].set_title("Parallel Efficiency")
axes[2].set_xticks(process_counts)
axes[2].set_ylim(0, 180)
axes[2].legend()
axes[2].grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs('/kaggle/working/capstoneproject/data', exist_ok=True)
plt.savefig('/kaggle/working/capstoneproject/data/hpc_scaling_results.png',
            dpi=150, bbox_inches='tight')
print("\nChart saved to data/hpc_scaling_results.png")
plt.show()
