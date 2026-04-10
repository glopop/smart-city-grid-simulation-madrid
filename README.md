# Smart City Grid Simulation 

**HPC-Accelerated Agent-Based Models for Urban Grid Stability Under High-Density Loads**

*Gloria Paraschivoiu · BCSAI, IE University · Supervised by Prof. Oscar Diez · April 2026*

---

## What This Is

A simulation tool that answers one practical question: **what happens to a city's electricity grid if new EV charging hubs and AI data centres are approved?**

The framework models demand behaviour (how EV hubs surge, how data centres grow), runs that demand through a physical grid model, triggers an optimiser when voltage drops too low, and presents everything in a browser dashboard — no code required to explore results.

---

## How It Works

Four layers talk to each other in a closed loop at each 15-minute timestep:

```
Agent demand → Power flow → Voltage check → Optimiser (if needed) → Next timestep
```

| Layer | What it does | Tool |
|---|---|---|
| Agent-Based Demand | EV hubs and data centres as software agents with realistic behavioural rules | Mesa 3.3.1 |
| Physical Grid | Runs power flow on the IEEE 33-bus feeder, returns voltages at 11 buses | OpenDSS |
| Optimisation | Binary load scheduler — defers loads when voltage violations occur | PuLP / CBC |
| Dashboard & HPC | Interactive browser results explorer; parallel scenario execution | Plotly Dash + mpi4py |

---

## Quick Start

### Requirements

- Python 3.11
- Open MPI 4.1.x (only needed for parallel runs)

```bash
pip install -r requirements.txt
```

### 1. Open the Dashboard (recommended)

The dashboard loads pre-computed results — no simulation needs to run first.

```bash
python -m dashboard.dashboard
```

Then open `http://127.0.0.1:8050` in your browser. Use the dropdown to switch between Low / Medium / High Stress scenarios.

### 2. Run a Single Scenario

```bash
python simulation/main.py
```

Runs medium stress by default. Edit the scenario name at the bottom of `main.py` to change it.

### 3. Run All Scenarios in Parallel (MPI)

Install Open MPI first (macOS: `brew install open-mpi`).

```bash
mpirun -n 2 python hpc/parallel_scenarios.py   # recommended
mpirun -n 1 python hpc/parallel_scenarios.py   # sequential baseline
mpirun -n 3 python hpc/parallel_scenarios.py   # 3 processes
```

> Note: MPI runs use 960 timesteps (10-day horizon). Dashboard uses 96 timesteps (1 day). Do not mix results from the two.

### 4. Docker (easiest for reproducibility)

```bash
docker build -t smart-city-grid .
docker run -p 8050:8050 smart-city-grid          # dashboard
docker run smart-city-grid python simulation/main.py   # simulation
```

---

## Project Structure

```
capstoneproject/
├── README.md
├── requirements.txt
├── simulation_results.csv          ← pre-computed results (288 rows, 3 scenarios)
│
├── simulation/
│   ├── agents.py                   ← EVHubAgent and DataCenterAgent
│   ├── scenarios.py                ← scenario parameter definitions
│   └── main.py                     ← single-scenario runner
│
├── grid/
│   ├── grid_model.py               ← IEEE 33-bus OpenDSS feeder definition
│   ├── powerflow.py                ← power flow execution and voltage extraction
│   └── ieee33bus/ieee33.dss        ← OpenDSS feeder file (Baran & Wu 1989)
│
├── optimization/
│   └── scheduler.py                ← PuLP binary MILP load scheduler
│
├── hpc/
│   ├── parallel_scenarios.py       ← MPI parallel scenario execution
│   └── analyze_scaling.py          ← speedup and efficiency analysis
│
├── dashboard/
│   └── dashboard.py                ← Plotly Dash interactive dashboard
│
└── data/
    ├── madrid_ev_stations.csv      ← Ayuntamiento de Madrid EV registry
    ├── madrid_municipal_ev.csv     ← Municipal EV charging data
    ├── ree_demand_madrid.csv       ← Red Eléctrica de España hourly demand
    └── real_data_analysis.py       ← calibration script
```

---

## Scenarios

| Scenario | EV Hubs | Data Centres | EV Base (MW) | DC Base (MW) | Surge Probability |
|---|---|---|---|---|---|
| baseline | 1 | 1 | 0.05 | 0.20 | 0% |
| low_stress | 3 | 1 | 0.08 | 0.30 | 8% |
| medium_stress | 5 | 2 | 0.15 | 0.80 | 15% |
| high_stress | 8 | 3 | 0.25 | 1.50 | 25% |
| extreme_stress | 12 | 4 | 0.40 | 2.50 | 35% |

All demand values are in MW and converted to kW before OpenDSS injection. Parameters are scaled to the operational limits of the 12.66 kV IEEE 33-bus feeder.

---

## Key Results

| Metric | Low Stress | Medium Stress | High Stress |
|---|---|---|---|
| Avg EV Bus Voltage | 0.928 pu | 0.853 pu | 0.709 pu |
| Min EV Bus Voltage | 0.815 pu | 0.688 pu | 0.550 pu |
| Total Violations | 186 | 541 | 768 |
| Timesteps with Violations | 67 / 96 | 95 / 96 | 96 / 96 |
| Optimiser Feasibility Rate | 100% | 100% | 100% |
| Avg Voltage Recovery | +0.050 pu | +0.059 pu | +0.076 pu |

**Main finding:** Even low-penetration high-density loads cause voltage violations across multiple buses simultaneously on a radial feeder — an effect that aggregate demand assessments completely miss.

---

## Reproducing Results

All random seeds are fixed at **42** (independently for both NumPy and Mesa). The same inputs always produce the same outputs.

```bash
# Reproduce the simulation CSV from scratch
python simulation/main.py

# Or run all three scenarios sequentially
mpirun -n 1 python hpc/parallel_scenarios.py
```

---

## Important Technical Notes

**Mesa 3.3.1 API changes:** Agents no longer receive a unique ID in their constructor. Use `self.agents.do("step")` not `self.schedule.step()`. Mesa and NumPy random states must be seeded independently.

**OpenDSS voltage base:** `Set VoltageBases` must be called before `CalcVoltageBases`. Without this, voltages return as raw magnitudes in the hundreds, not per-unit values near 1.0.

**Scenario parameter scaling:** Real-world MW figures from industry reports would immediately collapse the 12.66 kV feeder. All parameters are scaled down to match the feeder's operational limits.

**HPC superlinear speedup:** The 115.6% parallel efficiency at 2 processes is specific to the Kaggle cloud environment (reduced cache contention on shared cores). Do not generalise this result.

**IEEE 33-bus disclaimer:** Bus locations shown on the Madrid map are illustrative only. This is the standard Baran & Wu (1989) radial test network, not a real Madrid substation.

**Quantum layer:** The QUBO formulation for QAOA-based load scheduling is designed at the architectural level. No Qiskit implementation has been completed. It is planned as future work.

---

## Tech Stack

| Component | Version | Role |
|---|---|---|
| Python | 3.11 | Base environment |
| Mesa | 3.3.1 | Agent-based modelling |
| OpenDSSDirect.py | 0.9.4 | Power flow simulation |
| PuLP | 3.3.0 | Binary MILP optimisation |
| mpi4py | 4.1.1 | MPI parallel execution |
| Plotly Dash | 4.0.0 | Interactive dashboard |
| NumPy | 1.26.4 | Numerical operations |
| pandas | 2.2.2 | Data handling |

