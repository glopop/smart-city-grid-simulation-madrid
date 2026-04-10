# Smart City Grid Simulation

**HPC-Accelerated Agent-Based Models for Urban Grid Stability Under High-Density Loads**

*Gloria Paraschivoiu · BCSAI, IE University · Supervised by Prof. Oscar Diez · April 2026*

---

## What This Is

A simulation tool that answers one practical question: **what happens to a city's electricity grid if new EV charging hubs and AI data centres are approved?**

Results are explored through an interactive browser dashboard — no code required to use it.

---

## Running the Dashboard

Follow these steps exactly in order.

---

### Step 1 — Clone the repository

Use SSH if you already have GitHub SSH set up:

```bash
git clone git@github.com:glopop/smart-city-grid-simulation-madrid.git
cd smart-city-grid-simulation-madrid
```

Or use HTTPS:

```bash
git clone https://github.com/glopop/smart-city-grid-simulation-madrid.git
cd smart-city-grid-simulation-madrid
```

---

### Step 2 — Check your Python version

```bash
python --version
```

If `python` is not found on your machine, try:

```bash
python3 --version
```

You need **Python 3.11 or 3.12**. If you are on an earlier version, install 3.11 using pyenv:

```bash
# Install pyenv if you don't have it (macOS)
brew install pyenv

# Install Python 3.11
pyenv install 3.11.9

# Set it as the local version for this project
pyenv local 3.11.9

# Confirm it worked
python --version   # should now say Python 3.11.9
```

---

### Step 3 — Create a virtual environment

A virtual environment keeps this project's dependencies separate from everything else on your machine. You only do this once.

If `python --version` works:

```bash
python -m venv venv
```

If you use `python3` instead of `python`:

```bash
python3 -m venv venv
```

---

### Step 4 — Activate the virtual environment

```bash
# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

You will see `(venv)` appear at the start of your terminal line. This means it is active.

> **Important:** every time you open a new terminal window you need to run this activate command again before running anything. If the dashboard gives an import error, this is almost always why.

---

### Step 5 — Install dependencies

```bash
pip install numpy==1.26.4
pip install -r requirements.txt
```

numpy is installed first separately to avoid version conflicts. This will take 2-3 minutes.

---

### Step 6 — Run the dashboard

```bash
python dashboard/dashboard.py
```

Then open your browser and go to:

**http://127.0.0.1:8050**

Use the dropdown on the left to switch between Low, Medium, and High Stress scenarios. All results load instantly from the pre-computed file included in the repo — nothing else needs to run.

---

## Running the Simulation (optional)

The dashboard already includes pre-computed results. Only do this if you want to regenerate them from scratch.

**Single scenario:**

```bash
python simulation/main.py
```

Runs the medium stress scenario by default. To change which scenario runs, edit the scenario name at the bottom of `simulation/main.py`.

**All scenarios in parallel (requires Open MPI):**

If installation failed earlier on `mpi4py`, install Open MPI first, then reinstall dependencies:

macOS:
```bash
brew install open-mpi
```

Ubuntu / Debian:
```bash
sudo apt-get install openmpi-bin libopenmpi-dev
```

Then rerun:
```bash
pip install -r requirements.txt
```

Then run the parallel scenarios:
```bash
mpirun -n 2 python hpc/parallel_scenarios.py   # recommended — best efficiency
mpirun -n 1 python hpc/parallel_scenarios.py   # sequential baseline
mpirun -n 3 python hpc/parallel_scenarios.py   # 3 processes (lower efficiency due to load imbalance)
```

> **Important:** MPI runs use **960 timesteps** (10-day horizon). The dashboard uses **96 timesteps** (24-hour simulation). Do not use MPI output to feed the dashboard — they are separate result sets.

> The scaling results reported in the paper (16.6s baseline, 2.31× speedup at 2 processes) were produced on Kaggle's cloud environment with 2 physical CPU cores. Running locally will produce different runtimes but identical simulation outputs. The Kaggle runner script is at `hpc/kaggle_hpc_runner.py`.

---

## Troubleshooting

**`(venv)` is not showing in my terminal**
Run `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows) from inside the project folder. This must be done every new terminal session.

**Installation fails or stops midway**
Make sure you ran `pip install numpy==1.26.4` first before `pip install -r requirements.txt`, and that your virtual environment is activated.

**Wrong Python version**
Run `python --version` inside your activated venv. If it is below 3.11, follow Step 2 again to install the correct version.

**`pyenv local` worked but `python` is still the wrong version**
Your shell may not be picking up pyenv correctly. As a fallback, create the virtual environment directly with the Python 3.11 interpreter:

```bash
~/.pyenv/versions/3.11.9/bin/python -m venv venv
```

Then use the venv directly:

```bash
venv/bin/pip install numpy==1.26.4
venv/bin/pip install -r requirements.txt
venv/bin/python dashboard/dashboard.py
```

**Dashboard opens but is blank**
`simulation_results.csv` must be in the project root folder. It is included in the repo. If it is missing, run `python simulation/main.py` first to generate it.

**Port 8050 is already in use**
Something else is running on that port. Change the port at the bottom of `dashboard/dashboard.py`:

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
│   ├── agents.py                ← EVHubAgent and DataCenterAgent (Mesa 3.3.1)
│   ├── scenarios.py             ← scenario parameters
│   └── main.py                  ← single-scenario runner (medium stress by default)
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
│   ├── parallel_scenarios.py    ← MPI parallel execution (960 timesteps, 10-day horizon)
│   ├── analyze_scaling.py       ← speedup and efficiency analysis
│   └── kaggle_hpc_runner.py     ← script used to produce scaling results on Kaggle
│
├── dashboard/
│   └── dashboard.py             ← Plotly Dash interactive dashboard
│
└── data/
    ├── madrid_ev_stations.csv   ← Ayuntamiento de Madrid EV registry (195 units)
    ├── madrid_municipal_ev.csv  ← Municipal EV charging data
    ├── ree_demand_madrid.csv    ← Red Eléctrica de España hourly demand
    └── real_data_analysis.py    ← calibration script (Pearson r = 0.554)
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

All demand values are in MW and converted to kW before OpenDSS injection. Parameters are scaled to the operational limits of the 12.66 kV IEEE 33-bus feeder.

---

## Tech Stack

| Component | Version |
|---|---|
| Python | 3.11 or 3.12 |
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
