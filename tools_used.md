# Smart City Grid Simulation — Technical Stack Reference
# Gloria Paraschivoiu · IE University · April 2026
# Corrected to match simulation_results.csv and report Table 2/Table 3

---

## Python Environment

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.11 | Anaconda distribution |
| Anaconda | base environment | Package manager |

---

## Core Simulation Libraries

| Library | Version | Role | Install |
|---------|---------|------|---------|
| Mesa | 3.3.1 | ABM framework — agent lifecycle, scheduling, stepping | `pip install mesa` |
| OpenDSSDirect.py | 0.9.4 | Python interface to OpenDSS — load injection, power flow, voltage extraction | `pip install opendssdirect.py` |
| dss-python | 0.15.7 | Backend C-API for OpenDSSDirect.py | Auto-installed |
| NumPy | 1.26.4 | Vectorised demand aggregation, preprocessing, random seeding | `pip install numpy` |
| PuLP | 3.3.0 | Binary MILP load scheduling — CBC solver backend | `pip install pulp` |
| pandas | 2.0.0 | CSV I/O, simulation results handling, data calibration | `pip install pandas` |
| Plotly Dash | 4.0.0 | Interactive dashboard framework | `pip install dash` |
| dash-bootstrap-components | 1.5.0 | Dashboard UI components | `pip install dash-bootstrap-components` |
| mpi4py | 4.1.1 | MPI-based parallel scenario execution | `pip install mpi4py` |
| Open MPI | 4.1.2 | Underlying MPI implementation | System install |

---

## OpenDSS Grid Configuration

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Test feeder | IEEE 33-bus radial | Standard benchmark (Baran & Wu 1989) |
| Base voltage | 12.66 kV | Published feeder specification |
| Source voltage | 1.05 pu | Standard practice to compensate feeder voltage drop |
| Voltage bases | Set explicitly before CalcVoltageBases | Required for correct per-unit readings |
| Solution mode | Snapshot | Quasi-static time series appropriate for planning timescale |
| Timestep resolution | 15 minutes (96 steps = 24 hours) | Urban planning decision timescale |

---

## Stability Thresholds

| Metric | Threshold | Standard |
|--------|-----------|----------|
| Voltage minimum | 0.95 pu | IEEE 1547 / EN 50160 |
| Voltage maximum | 1.05 pu | IEEE 1547 / EN 50160 |
| Transformer loading | 100% rated capacity | IEC 60076 |
| THD limit | 8% | IEEE 519 |

---

## Scenario Definitions
# Corrected from tools_used.md v1 — matches report Table 2 and simulation_results.csv

| Scenario | EV Hubs | Data Centres | EV Base MW | DC Base MW | Surge Prob | Weather | Seed |
|----------|---------|--------------|------------|------------|------------|---------|------|
| baseline | 1 | 1 | 0.05 | 0.20 | 0.00 | 1.0 | 42 |
| low_stress | 3 | 1 | 0.08 | 0.30 | 0.08 | 1.0 | 42 |
| medium_stress | 5 | 2 | 0.15 | 0.80 | 0.15 | 1.1 | 42 |
| high_stress | 8 | 3 | 0.25 | 1.50 | 0.25 | 1.2 | 42 |
| extreme_stress | 12 | 4 | 0.40 | 2.50 | 0.35 | 1.3 | 42 |

NOTE: Agent demand values are specified in MW but converted to kW before
OpenDSS injection. Parameters scaled to sub-MW values to match the 12.66 kV
IEEE 33-bus feeder capacity (practical load limits ~2-5 MW before widespread
voltage violations).

---

## Optimisation Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Solver | PuLP CBC | Open-source MILP solver |
| Problem type | Binary LP | Each agent is active (1) or deferred (0) |
| Objective | Minimise deferred load | Keep as many loads active as possible |
| EV minimum active | 30% of agents | Service continuity constraint |
| DC minimum active | 50% of agents | Critical infrastructure constraint |
| Trigger condition | n_violations > 0 | Any bus outside 0.95–1.05 pu range |
| Reduction — mild | 15% | Voltage 0.90–0.95 pu |
| Reduction — moderate | 20% | Voltage 0.85–0.90 pu |
| Reduction — severe | 30% | Voltage below 0.85 pu |

---

## HPC Configuration

| Parameter | Value |
|-----------|-------|
| Platform | Kaggle cloud computing environment |
| Physical CPU cores | 2 |
| MPI processes tested | 1, 2, 3 |
| Timesteps per scenario (HPC) | 960 (10-day horizon) |
| Timesteps per scenario (results) | 96 (24-hour horizon) |
| Parallelisation strategy | Scenario-parallel (no inter-process communication) |
| Seed | 42 (fixed across all runs) |

---

## Simulation Results CSV Columns

| Column | Description |
|--------|-------------|
| timestep | 15-min interval index (0–95) |
| scenario | low_stress / medium_stress / high_stress |
| ev_mw | Aggregate EV hub demand in MW |
| dc_mw | Aggregate data centre demand in MW |
| total_mw | Combined demand in MW |
| ev_bus_voltage_pu | Per-unit voltage at Bus18 (EV hub injection point) |
| ai_bus_voltage_pu | Per-unit voltage at Bus33 (data centre injection point) |
| dist_bus_voltage_pu | Per-unit voltage at distribution bus |
| transformer_loading_pct | Transformer loading % — always 0.0 in current runs |
| n_violations_pre | Buses outside 0.95–1.05 pu before optimisation |
| n_violations_post | Buses outside 0.95–1.05 pu after optimisation |
| optimization_triggered | 1 if optimiser ran this timestep, 0 otherwise |
| optimization_feasible | 1 if PuLP found optimal solution |
| opt_runtime_sec | Seconds taken to solve scheduling problem |
| demand_reduction_mw | MW deferred by optimiser |
| optimized_total_mw | Total demand after optimisation |
| post_opt_ev_voltage | EV bus voltage after load reintegration |
| post_opt_ai_voltage | Data centre bus voltage after reintegration |

NOTE: transformer_loading_pct is always 0.0 — transformer overload results
must not be reported in the results section of the paper.

---

## Project File Structure

```
capstoneproject/
├── simulation/
│   ├── agents.py          # EVHubAgent, DataCenterAgent, GridDemandModel (Mesa 3.3.1)
│   ├── scenarios.py       # Scenario parameter definitions (Table 2 in report)
│   └── main.py            # Single-scenario simulation runner
├── grid/
│   ├── grid_model.py      # IEEE 33-bus OpenDSS feeder definition
│   ├── powerflow.py       # Power flow execution and voltage extraction
│   └── ieee33bus/         # OpenDSS feeder definition files
├── optimization/
│   └── scheduler.py       # PuLP binary MILP load scheduler
├── hpc/
│   ├── parallel_scenarios.py  # MPI parallel scenario execution
│   └── analyze_scaling.py     # Speedup and efficiency analysis
├── dashboard/
│   ├── __init__.py
│   └── dashboard.py       # Plotly Dash interactive dashboard
├── data/
│   ├── madrid_ev_stations.csv      # Ayuntamiento de Madrid EV registry
│   ├── madrid_municipal_ev.csv     # Municipal EV data
│   ├── ree_demand_madrid.csv       # Red Eléctrica de España hourly demand
│   ├── real_data_analysis.py       # Calibration against real Madrid data
│   └── [figures].png               # Static analysis figures
├── notebooks/                      # Exploratory analysis
├── simulation_results.csv          # Pre-computed results (288 rows, 3 scenarios)
├── requirements.txt
└── tools_used.md
```

---

## Key Design Decisions

**Mesa over custom ABM:**
Mesa 3.3.1 provides standardised agent scheduling, reproducible random state
management, and a clean API that integrates directly with NumPy and OpenDSS.
Both NumPy and Mesa random states seeded independently at value 42.

**OpenDSS over pandapower:**
OpenDSS is the industry-standard distribution system simulator used by
utilities worldwide. Provides physically validated power flow at distribution
level. The IEEE 33-bus feeder file was constructed from Baran & Wu 1989
published data as no stable OpenDSS-formatted version exists publicly.

**PuLP over Gurobi:**
PuLP with CBC is open-source and sufficient for this problem size
(up to 8 binary EV variables and 3 binary DC variables in high stress).
Gurobi is a drop-in replacement via PuLP's solver interface for larger problems.

**Quasi-static over transient simulation:**
15-minute timesteps are appropriate for urban planning timescales and
computationally feasible for parallel execution. Transient simulation
requires sub-second timesteps and is outside distribution-level planning scope.

**Scenario-parallel MPI over spatial decomposition:**
The three scenarios share no state and require no inter-process communication,
making scenario-parallel execution the natural and efficient strategy.
Spatial decomposition of the IEEE 33-bus feeder would require significant
restructuring of the OpenDSS integration without meaningful benefit at this scale.

**Quantum layer — designed only, not implemented:**
The QUBO formulation is designed at the architectural level for future
QAOA-based benchmarking against the PuLP classical baseline.
No Qiskit code has been written. All quantum language in the report
uses: designed, exploratory, planned, or pending.
