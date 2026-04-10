# simulation/agents.py
#
# this file defines the two types of agents used in the simulation:
# ev charging hubs and ai data centres. each agent decides how much
# electricity it needs at every 15-minute timestep based on simple
# behavioural rules. the mesa library manages all the agents and steps
# them forward in time togetherr
#
# i used mesa 3.3.1 which changed a few things from older versions and 
# agents no longer get a unique id in the constructor, and stepping
# uses self.agents.do("step") instead of self.schedule.step().
# both the mesa and numpy random states need to be seeded separately
# to guarantee the same results every run, this was also discused within the report directly

import mesa
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# helper function: ev demand curve
# returns a multiplier between 0 and 1 based on time of day 
# i modelled two daily peaks one being int he morning when people leave for work and plug in their cars
# before work, and one in the evening when they come home
# this matches real ev charging behaviour from the lit review done previously 
# ─────────────────────────────────────────────────────────────────────────────
def ev_demand_curve(timestep):
    """
    calculates a base demand multiplier (0 to 1) for the current time of day.
    timestep 0 = midnight, 96 timesteps = full 24 hours at 15-min intervals.
    morning peak at timestep 32 (8am), evening peak at timestep 72 (6pm).
    uses gaussian curves so demand rises and falls smoothly around each peak.
    """
    # convert timestep index to hour of day (0 to 24)
    hour = (timestep % 96) / 4

    # gaussian curve centred at 8am with width 1.5 hours
    morning_peak = np.exp(-0.5 * ((hour - 8) / 1.5) ** 2)

    # gaussian curve centred at 6pm with width 2 hours
    # wider than morning peak because evening charging is more spread out
    evening_peak = np.exp(-0.5 * ((hour - 18) / 2.0) ** 2)

    # clip to minimum 0.05 so there is always some baseline demand overnight
    return float(np.clip(morning_peak + evening_peak, 0.05, 1.0))


# ─────────────────────────────────────────────────────────────────────────────
# agent 1: ev charging hub
# ─────────────────────────────────────────────────────────────────────────────
class EVHubAgent(mesa.Agent):
    """
    represents a large ev charging hub in the city.
    demand follows the daily double-peak curve above, with random surge
    events layered on top to model what happens when many vehicles arrive
    at the same time. this volatility is what makes ev hubs hard for the
    grid to handle — the demand is unpredictable and clustered.
    """

    def __init__(self, model, base_mw=10.0, surge_prob=0.15, surge_mw=15.0):
        super().__init__(model)

        # base_mw is the peak demand for this hub — scaled by the daily curve
        self.base_mw = base_mw

        # surge_prob is the chance of a sudden demand spike each timestep
        self.surge_prob = surge_prob

        # surge_mw is how much extra demand a surge adds
        self.surge_mw = surge_mw

        # tracks how many more timesteps a current surge will last
        self.surge_remaining = 0

        # these store the output used by the grid model each timestep
        self.current_demand_mw = 0.0
        self.current_demand_mvar = 0.0

    def step(self):
        # get the time-of-day multiplier for this timestep
        curve_factor = ev_demand_curve(self.model.timestep)
        base = self.base_mw * curve_factor

        # check if a surge is already running from a previous timestep
        if self.surge_remaining > 0:
            surge = self.surge_mw
            self.surge_remaining -= 1

        # otherwise randomly decide if a new surge starts this timestep
        elif self.random.random() < self.surge_prob:
            surge = self.surge_mw
            # surge lasts between 1 and 3 timesteps (15 to 45 minutes)
            self.surge_remaining = self.random.randint(1, 3)

        else:
            surge = 0.0

        # add small gaussian noise to make demand realistic rather than smooth
        noise = self.random.gauss(0, 0.5)

        # total demand cannot go negative
        self.current_demand_mw = max(0.0, base + surge + noise)

        # reactive power assumed at 0.15 lag power factor ratio
        # this is consistent with ev charging equipment characteristics
        self.current_demand_mvar = self.current_demand_mw * 0.15


# ─────────────────────────────────────────────────────────────────────────────
# agent 2: ai data centre
# ─────────────────────────────────────────────────────────────────────────────
class DataCenterAgent(mesa.Agent):
    """
    represents a hyperscale ai data centre.
    unlike the ev hub which follows a daily cycle, a data centre runs at
    high continuous load and occasionally gets permanent demand increases
    when new server racks are deployed. these increases never reverse within
    the simulation — which is exactly what makes data centres so challenging
    for grid planning. the demand floor just keeps rising.
    """

    def __init__(self, model, base_mw=50.0, step_rate=0.05, step_mw=20.0):
        super().__init__(model)

        # continuous baseline demand regardless of time of day
        self.base_mw = base_mw

        # probability of a new server deployment event each timestep
        self.step_rate = step_rate

        # how much demand each deployment event adds in mw
        self.step_mw = step_mw

        # running total of all deployment events so far — never resets
        self.accumulated_steps = 0.0

        # output used by the grid model each timestep
        self.current_demand_mw = 0.0
        self.current_demand_mvar = 0.0

    def step(self):
        # randomly check if a new deployment event happens this timestep
        if self.random.random() < self.step_rate:
            # add between 80% and 120% of step_mw to model realistic variation
            # in deployment sizes
            added = self.random.uniform(
                self.step_mw * 0.8,
                self.step_mw * 1.2
            )
            # this is permanent — accumulated_steps only ever increases
            self.accumulated_steps += added

        # small gaussian noise around the total accumulated demand
        noise = self.random.gauss(0, 1.0)

        self.current_demand_mw = max(0.0, self.base_mw + self.accumulated_steps + noise)

        # data centres have better power factor than ev hubs (0.10 vs 0.15)
        # because they use more controlled power conversion equipment
        self.current_demand_mvar = self.current_demand_mw * 0.10


# ─────────────────────────────────────────────────────────────────────────────
# mesa model: urban grid demand model
# this is the container that holds all agents and steps them forward together
# ─────────────────────────────────────────────────────────────────────────────
class GridDemandModel(mesa.Model):
    """
    manages all ev hub and data centre agents for one simulation scenario.
    accepts a scenario dictionary so the same model class works for all
    three scenarios without any code changes — just different parameters.
    seeding both mesa and numpy separately is necessary because mesa 3.3.1
    maintains its own internal random state separate from numpy's global state.
    """

    def __init__(self, scenario: dict, seed=None):
        super().__init__()
        self.timestep = 0

        # use provided seed or fall back to the scenario's default
        actual_seed = seed if seed is not None else scenario["seed"]

        # seed both random systems independently for full reproducibility
        self.random.seed(actual_seed)
        np.random.seed(actual_seed)

        self.demand_history = []

        # weather multiplier scales all demand up slightly on hotter days
        # 1.0 = normal, 1.1 = medium stress, 1.2 = high stress
        self.weather_multiplier = scenario.get("weather_multiplier", 1.0)

        # in mesa 3.x agents are automatically added to self.agents
        # when instantiated with model=self — no need to add them manually

        # create ev hub agents with slight demand variation per agent
        # uniform variation between 0.9 and 1.1 makes each hub slightly different
        for _ in range(scenario["n_ev_hubs"]):
            EVHubAgent(
                model=self,
                base_mw=scenario["ev_base_mw"] * np.random.uniform(0.9, 1.1),
                surge_prob=scenario["ev_surge_prob"],
                surge_mw=scenario["ev_surge_mw"]
            )

        # create data centre agents the same way
        for _ in range(scenario["n_data_centers"]):
            DataCenterAgent(
                model=self,
                base_mw=scenario["dc_base_mw"] * np.random.uniform(0.9, 1.1),
                step_rate=scenario["dc_step_rate"],
                step_mw=scenario["dc_step_mw"]
            )

    def step(self):
        # mesa 3.x uses self.agents.do("step") instead of self.schedule.step()
        # this steps every agent forward by one 15-minute timestep
        self.agents.do("step")

        # aggregate demand across all agents and apply weather multiplier
        total_mw = sum(
            a.current_demand_mw for a in self.agents
        ) * self.weather_multiplier

        total_mvar = sum(
            a.current_demand_mvar for a in self.agents
        ) * self.weather_multiplier

        # record this timestep for later analysis
        self.demand_history.append({
            "timestep":   self.timestep,
            "total_mw":   round(total_mw, 3),
            "total_mvar": round(total_mvar, 3)
        })

        self.timestep += 1

    def run(self, steps=96):
        """run the model for the specified number of timesteps and return history."""
        for _ in range(steps):
            self.step()
        return self.demand_history


# ─────────────────────────────────────────────────────────────────────────────
# quick test — run this file directly to verify the agent layer works
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from simulation.scenarios import get_scenario

    print("running agent test with medium_stress scenario...")
    scenario = get_scenario("medium_stress")
    model    = GridDemandModel(scenario=scenario)
    history  = model.run(steps=scenario["timesteps"])

    print(f"\nfirst 5 timesteps:")
    for record in history[:5]:
        print(f"  t={record['timestep']:02d} | "
              f"total mw: {record['total_mw']:7.2f} | "
              f"total mvar: {record['total_mvar']:6.2f}")

    peak = max(history, key=lambda x: x["total_mw"])
    print(f"\npeak demand: {peak['total_mw']} mw at timestep {peak['timestep']}")
    print("\nagent layer working correctly.")