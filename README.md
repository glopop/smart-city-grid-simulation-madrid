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

```bash
git clone https://github.com/YOUR_USERNAME/capstoneproject.git
cd capstoneproject
```

---

### Step 2 — Check your Python version

```bash
python --version
```

You need **Python 3.11**. If you see 3.12 or anything else, install 3.11 using pyenv:

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

```bash
python -m venv venv
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

Runs medium stress by default. To change scenario, edit the name at the bottom of `main.py`.

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

---

## Troubleshooting

**`(venv)` is not showing in my terminal**
You need to activate the virtual environment. Run `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows) from inside the project folder.

**Installation fails or stops midway**
Make sure you ran `pip install numpy==1.26.4` first before `pip install -r requirements.txt`. Also make sure your virtual environment is activated.

**Wrong Python version**
Run `python --version` inside your activated venv. If it is not 3.11, follow Step 2 again and make sure you ran `pyenv local 3.11.9` inside the project folder.

**Dashboard opens but is blank**
Make sure `simulation_results.csv` is present in the root of the project folder. It should be included in the repo — if it is missing, run `python simulation/main.py` first to generate it.

**Port 8050 already in use**
Something else is running on that port. Either close it, or change the port at the bottom of `dashboard/dashboard.py`:
```python
app.run(debug=True, port=8051)
```
Then go to http://127.0.0.1:8051 instead.

---

## Project Structure

```
capstoneproject/
├── README.md
├── requirements.txt
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
| Python | 3.11 |
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
