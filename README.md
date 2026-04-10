# Smart City Grid Simulation

**HPC-Accelerated Agent-Based Models for Urban Grid Stability Under High-Density Loads**

*Gloria Paraschivoiu · BCSAI, IE University · Supervised by Prof. Oscar Diez · April 2026*

---

## What This Is

A simulation tool that answers one practical question: **what happens to a city's electricity grid if new EV charging hubs and AI data centres are approved?**

Results are explored through an interactive browser dashboard — no code required to use it.

---

## Running the Dashboard

### Step 1 — Clone the repository

```bash
git clone https://github.com/glopop/smart-city-grid-simulation-madrid.git
cd smart-city-grid-simulation-madrid
```

---

### Step 2 — Create a virtual environment

```bash
python -m venv venv
```

---

### Step 3 — Activate the virtual environment

```bash
# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

You will see `(venv)` appear at the start of your terminal line. This means it is active.

> Every time you open a new terminal you need to run this activate command again before running anything.

---

### Step 4 — Install dependencies

```bash
pip install numpy==1.26.4
pip install -r requirements.txt
```

This will take 2-3 minutes.

---

### Step 5 — Run the dashboard

```bash
python dashboard/dashboard.py
```

Then open your browser and go to (if the 8050 port is occupied, the link will be modified for your port, refer to the Troubleshooting section below):

**http://127.0.0.1:8050**

Use the dropdown on the left to switch between Low, Medium, and High Stress scenarios. All results load instantly — nothing else needs to run.

---

## Running the Simulation (optional)

The dashboard already includes pre-computed results. Only do this if you want to regenerate them from scratch.

**Single scenario:**
```bash
python simulation/main.py
```
Runs medium stress by default. To change it, edit the scenario name at the bottom of `main.py`.

**All scenarios in parallel (requires Open MPI):**

Install Open MPI first:
```bash
# macOS
brew install open-mpi

# Ubuntu / Debian
sudo apt-get install openmpi-bin libopenmpi-dev
```

Then:
```bash
mpirun -n 2 python hpc/parallel_scenarios.py
```

> MPI runs use 960 timesteps (10-day horizon). The dashboard uses 96 timesteps (1 day). Do not mix the two.


> The HPC scaling results reported in the paper (16.6s baseline, 2.31× speedup 
> at 2 processes) were produced on Kaggle's cloud environment with 2 physical 
> CPU cores. Running locally will produce different runtimes but the same 
> simulation outputs.
---

## Troubleshooting

**`(venv)` is not showing in my terminal**
Run `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows) from inside the project folder. This must be done every new terminal session.

**Installation fails or stops midway**
Make sure `pip install numpy==1.26.4` ran successfully before `pip install -r requirements.txt`, and that your venv is activated.

**Dashboard opens but is blank**
`simulation_results.csv` must be in the project root. It is included in the repo. If missing, run `python simulation/main.py` to regenerate it.

**Port 8050 already in use**
Change the port at the bottom of `dashboard/dashboard.py`:
```python
app.run(debug=True, port=8051)
```
Then go to **http://127.0.0.1:8051**.

---

## Project Structure

```
smart-city-grid-simulation-madrid/
├── README.md
├── requirements.txt             ← all dependencies
├── simulation_results.csv       ← pre-computed results, loaded by the dashboard
│
├── simulation/
│   ├── agents.py                ← EVHubAgent and DataCenterAgent
│   ├── scenarios.py             ← scenario parameters
│   └── main.py                  ← single-scenario runner
│
├── grid/
│   ├── grid_model.py            ← IEEE 33-bus feeder definition
│   ├── powerflow.py             ← power flow and voltage extraction
│   └── ieee33bus/ieee33.dss     ← OpenDSS feeder file (Baran & Wu 1989)
│
├── optimization/
│   └── scheduler.py             ← PuLP binary MILP load scheduler
│
├── hpc/
│   ├── parallel_scenarios.py    ← MPI parallel execution
│   └── analyze_scaling.py       ← speedup and efficiency analysis
│
├── dashboard/
│   └── dashboard.py             ← Plotly Dash dashboard
│
└── data/
    ├── madrid_ev_stations.csv   ← Ayuntamiento de Madrid EV registry
    ├── madrid_municipal_ev.csv  ← Municipal EV charging data
    ├── ree_demand_madrid.csv    ← Red Eléctrica de España demand data
    └── real_data_analysis.py    ← calibration script
```

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

---

## Scenarios

| Scenario | EV Hubs | Data Centres | EV Base (MW) | DC Base (MW) | Surge Probability |
|---|---|---|---|---|---|
| baseline | 1 | 1 | 0.05 | 0.20 | 0% |
| low_stress | 3 | 1 | 0.08 | 0.30 | 8% |
| medium_stress | 5 | 2 | 0.15 | 0.80 | 15% |
| high_stress | 8 | 3 | 0.25 | 1.50 | 25% |
| extreme_stress | 12 | 4 | 0.40 | 2.50 | 35% |

---

## Tech Stack

| Component | Version |
|---|---|
| Python | 3.11+ |
| Mesa | 3.3.1 |
| OpenDSSDirect.py | 0.9.4 |
| PuLP | 3.3.0 |
| mpi4py | 4.1.1 |
| Plotly Dash | 2.18.1 |
| NumPy | 1.26.4 |
| pandas | 2.2.2 |
| scipy | 1.13.1 |

---

**Supervisor:** Prof. Oscar Diez | **Programme:** BCSAI, IE University | **April 2026**
