# scenarios.py
# Defines all simulation scenarios used in evaluation.
# Scenario demand values are calibrated to the OpenDSS grid model
# to produce meaningful stress progression across four levels.

SCENARIOS = {

    "baseline": {
        "name": "Baseline",
        "description": "Near-zero load reference. Grid operates at nominal voltage.",
        "n_ev_hubs": 1,
        "n_data_centers": 1,
        "ev_base_mw": 0.05,
        "ev_surge_prob": 0.0,
        "ev_surge_mw": 0.0,
        "dc_base_mw": 0.2,
        "dc_step_rate": 0.0,
        "dc_step_mw": 0.0,
        "weather_multiplier": 1.0,
        "timesteps": 96,
        "seed": 42,
    },

    "low_stress": {
        "name": "Low Stress",
        "description": "Moderate high-density load. Grid operates safely near voltage limits.",
        "n_ev_hubs": 3,
        "n_data_centers": 1,
        "ev_base_mw": 0.08,
        "ev_surge_prob": 0.08,
        "ev_surge_mw": 0.05,
        "dc_base_mw": 0.3,
        "dc_step_rate": 0.02,
        "dc_step_mw": 0.05,
        "weather_multiplier": 1.0,
        "timesteps": 96,
        "seed": 42,
    },

    "medium_stress": {
        "name": "Medium Stress",
        "description": "High-density load growth with surges. Voltage violations expected.",
        "n_ev_hubs": 5,
        "n_data_centers": 2,
        "ev_base_mw": 0.15,
        "ev_surge_prob": 0.15,
        "ev_surge_mw": 0.10,
        "dc_base_mw": 0.8,
        "dc_step_rate": 0.05,
        "dc_step_mw": 0.15,
        "weather_multiplier": 1.1,
        "timesteps": 96,
        "seed": 42,
    },

    "high_stress": {
        "name": "High Stress",
        "description": "Peak load with frequent surges. Severe violations expected.",
        "n_ev_hubs": 8,
        "n_data_centers": 3,
        "ev_base_mw": 0.25,
        "ev_surge_prob": 0.25,
        "ev_surge_mw": 0.20,
        "dc_base_mw": 1.5,
        "dc_step_rate": 0.08,
        "dc_step_mw": 0.25,
        "weather_multiplier": 1.2,
        "timesteps": 96,
        "seed": 42,
    },

    "extreme_stress": {
        "name": "Extreme Stress",
        "description": "Maximum load conditions for threshold and sensitivity analysis.",
        "n_ev_hubs": 12,
        "n_data_centers": 4,
        "ev_base_mw": 0.40,
        "ev_surge_prob": 0.35,
        "ev_surge_mw": 0.30,
        "dc_base_mw": 2.5,
        "dc_step_rate": 0.10,
        "dc_step_mw": 0.40,
        "weather_multiplier": 1.3,
        "timesteps": 96,
        "seed": 42,
    },
}


def get_scenario(name):
    """Retrieve a scenario by name. Raises clear error if not found."""
    if name not in SCENARIOS:
        raise ValueError(
            f"Scenario '{name}' not found. "
            f"Available scenarios: {list(SCENARIOS.keys())}"
        )
    return SCENARIOS[name]


def list_scenarios():
    """Print a summary of all available scenarios."""
    print("\nAvailable Simulation Scenarios:")
    print("-" * 55)
    for key, s in SCENARIOS.items():
        print(f"  {key:<20} — {s['description']}")
    print()


if __name__ == "__main__":
    list_scenarios()

    print("Scenario parameter summary:")
    print("-" * 55)
    for key, s in SCENARIOS.items():
        total_base_mw = (s["n_ev_hubs"] * s["ev_base_mw"]) + \
                        (s["n_data_centers"] * s["dc_base_mw"])
        print(f"  {s['name']:<20} "
              f"EV hubs: {s['n_ev_hubs']}  "
              f"DCs: {s['n_data_centers']}  "
              f"Est. peak MW: ~{total_base_mw:.0f}")
