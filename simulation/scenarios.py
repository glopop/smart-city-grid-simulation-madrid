# simulation/scenarios.py
#
# this file defines all the simulation scenarios used in the evaluation
# each scenario is a dictionary of parameters that controls how many agents
# are created, how much demand they generate, and how volatile that demand is
#
# scenario parameters are scaled to sub-mw values to match the 12.66 kv
# ieee 33-bus feeder capacity. real-world mw values from industry reports
# would immediately collapse the feeder, so i scaled down to values where
# the stress progression from low to high is meaningful and measurable


# the calibration against real madrid data is in data/real_data_analysis.py
# which shows the agent demand curve matches the temporal shape of the
# red electrica de espana hourly demand data (pearson r = 0.554)
#
# all scenarios use seed 42 so results are exactly reproducible across runs
# see section 5.9 of the report for full scenario parameter justification

SCENARIOS = {

    # baseline: near-zero load reference
    # grid operates at nominal voltage with no meaningful stress
    # used to verify the feeder loads correctly before adding high-density loads
    "baseline": {
        "name":               "Baseline",
        "description":        "near-zero load reference. grid operates at nominal voltage",
        "n_ev_hubs":          1,
        "n_data_centers":     1,
        "ev_base_mw":         0.05,
        "ev_surge_prob":      0.0,
        "ev_surge_mw":        0.0,
        "dc_base_mw":         0.2,
        "dc_step_rate":       0.0,
        "dc_step_mw":         0.0,
        "weather_multiplier": 1.0,
        "timesteps":          96,
        "seed":               42,
    },

    # low stress: 3 ev hubs and 1 data centre
    # represents 38% coverage of the current madrid ev network
    # calibrated against the ayuntamiento de madrid ev station registry
    # produces measurable violations even at this low penetration level
    "low_stress": {
        "name":               "Low Stress",
        "description":        "moderate high-density load. grid near voltage limits",
        "n_ev_hubs":          3,
        "n_data_centers":     1,
        "ev_base_mw":         0.08,
        "ev_surge_prob":      0.08,
        "ev_surge_mw":        0.05,
        "dc_base_mw":         0.3,
        "dc_step_rate":       0.02,
        "dc_step_mw":         0.05,
        "weather_multiplier": 1.0,
        "timesteps":          96,
        "seed":               42,
    },

    # medium stress: 5 ev hubs and 2 data centres
    # represents 64% coverage of the current madrid ev network
    # weather multiplier of 1.1 reflects summer demand increase
    # produces near-continuous violations — 95 of 96 timesteps
    "medium_stress": {
        "name":               "Medium Stress",
        "description":        "high-density load with surges. voltage violations expected",
        "n_ev_hubs":          5,
        "n_data_centers":     2,
        "ev_base_mw":         0.15,
        "ev_surge_prob":      0.15,
        "ev_surge_mw":        0.10,
        "dc_base_mw":         0.8,
        "dc_step_rate":       0.05,
        "dc_step_mw":         0.15,
        "weather_multiplier": 1.1,
        "timesteps":          96,
        "seed":               42,
    },

    # high stress: 8 ev hubs and 3 data centres
    # worst-case deployment scenario for planning purposes
    # weather multiplier of 1.2 reflects peak summer conditions
    # produces violations at every single timestep — continuous collapse
    "high_stress": {
        "name":               "High Stress",
        "description":        "peak load with frequent surges. severe violations expected",
        "n_ev_hubs":          8,
        "n_data_centers":     3,
        "ev_base_mw":         0.25,
        "ev_surge_prob":      0.25,
        "ev_surge_mw":        0.20,
        "dc_base_mw":         1.5,
        "dc_step_rate":       0.08,
        "dc_step_mw":         0.25,
        "weather_multiplier": 1.2,
        "timesteps":          96,
        "seed":               42,
    },

    # extreme stress: 12 ev hubs and 4 data centres
    # designed for threshold and sensitivity analysis only
    # not used in the main evaluation — included for future work
    "extreme_stress": {
        "name":               "Extreme Stress",
        "description":        "maximum load conditions for sensitivity analysis",
        "n_ev_hubs":          12,
        "n_data_centers":     4,
        "ev_base_mw":         0.40,
        "ev_surge_prob":      0.35,
        "ev_surge_mw":        0.30,
        "dc_base_mw":         2.5,
        "dc_step_rate":       0.10,
        "dc_step_mw":         0.40,
        "weather_multiplier": 1.3,
        "timesteps":          96,
        "seed":               42,
    },
}


def get_scenario(name):
    """
    retrieves a scenario dictionary by name.
    raises a clear error if the name does not match any defined scenario
    so debugging is easier than a silent keyerror
    """
    if name not in SCENARIOS:
        raise ValueError(
            f"scenario '{name}' not found. "
            f"available scenarios: {list(SCENARIOS.keys())}"
        )
    return SCENARIOS[name]


def list_scenarios():
    """prints a summary of all available scenarios with their descriptions."""
    print("\navailable simulation scenarios:")
    print("-" * 55)
    for key, s in SCENARIOS.items():
        print(f"  {key:<20} — {s['description']}")
    print()


# quick test — run this file directly to check all scenarios load correctly
# and that the parameter values look reasonable
if __name__ == "__main__":
    list_scenarios()

    print("scenario parameter summary:")
    print("-" * 55)
    for key, s in SCENARIOS.items():
        # rough estimate of peak demand for sanity checking
        total_base_mw = (
            s["n_ev_hubs"]      * s["ev_base_mw"] +
            s["n_data_centers"] * s["dc_base_mw"]
        )
        print(f"  {s['name']:<20} "
              f"ev hubs: {s['n_ev_hubs']}  "
              f"dcs: {s['n_data_centers']}  "
              f"est base mw: ~{total_base_mw:.2f}")
