# grid/powerflow.py
#
# this file injects agent demand into the opendss ieee 33-bus feeder
# and runs a snapshot power flow solve at each simulation timestep
#
# the main function run_powerflow() takes the aggregate mw and mvar demand
# from the mesa agents, converts them to kw for opendss, updates the two
# load objects (evload and aiload), solves, and returns per-unit voltages
# and violation counts for every monitored bus
#
# i also included a helper to read transformer loading, though in the current
# simulation runs the transformer never overloads — the voltage violations
# always appear first at the end-of-feeder buses

import opendssdirect as dss
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from grid.grid_model import EV_BUS, AI_BUS, DIST_BUS, MONITOR_BUSES

# voltage thresholds per ieee 1547 and en 50160
# any bus outside this range counts as a violation
V_MIN       = 0.95
V_MAX       = 1.05
TRAFO_LIMIT = 100.0   # transformer loading limit in percent per iec 60076


def get_bus_voltage(bus_name):
    """
    reads the average per-unit voltage magnitude at a named bus.
    opendss returns alternating magnitude and angle values in puVmagAngle
    so we step through every other index to get just the magnitudes
    and average them across phases
    """
    dss.Circuit.SetActiveBus(bus_name)
    pu_vals    = dss.Bus.puVmagAngle()
    magnitudes = [pu_vals[i] for i in range(0, len(pu_vals), 2)]
    return round(sum(magnitudes) / len(magnitudes), 4)


def get_transformer_loading():
    """
    reads the maximum loading percentage across all transformers in the feeder
    uses apparent power (kva) compared to rated kva to get the loading percentage
    note: in the current simulation runs this always returns 0.0 because
    voltage violations appear at end-of-feeder buses before the transformer
    ever reaches its thermal limit
    """
    max_loading = 0.0
    for name in dss.Transformers.AllNames():
        dss.Transformers.Name(name)
        kva_rated = dss.Transformers.kVA()
        if kva_rated <= 0:
            continue
        dss.Circuit.SetActiveElement("Transformer." + name)
        powers    = dss.CktElement.Powers()
        if len(powers) >= 2:
            kw_total   = sum(powers[i] for i in range(0, min(6, len(powers)), 2))
            kvar_total = sum(powers[i] for i in range(1, min(7, len(powers)), 2))
            kva_actual = (kw_total**2 + kvar_total**2) ** 0.5
            loading    = abs(kva_actual / kva_rated * 100)
            max_loading = max(max_loading, loading)
    return round(max_loading, 2)


def run_powerflow(ev_mw, ev_mvar, dc_mw, dc_mvar):
    """
    injects agent demand into the ieee 33-bus feeder and runs a power flow solve.
    ev load goes to bus18 (evload), data centre load goes to bus33 (aiload).
    demand values from the agents are in mw but opendss needs kw so we multiply by 1000.

    parameters:
        ev_mw   : total ev hub demand in mw
        ev_mvar : total ev hub reactive demand in mvar
        dc_mw   : total data centre demand in mw
        dc_mvar : total data centre reactive demand in mvar

    returns a dict with voltages, violation count, and stability flags
    for this timestep — used by main.py and parallel_scenarios.py
    """
    # update ev hub load at bus18 — convert mw to kw for opendss
    dss.Command(
        "Edit Load.EVLoad kW="   + str(round(ev_mw * 1000, 2)) +
        " kvar=" + str(round(ev_mvar * 1000, 2))
    )

    # update data centre load at bus33
    dss.Command(
        "Edit Load.AILoad kW="   + str(round(dc_mw * 1000, 2)) +
        " kvar=" + str(round(dc_mvar * 1000, 2))
    )

    # run snapshot power flow solve
    dss.Command("Solve")
    converged = dss.Solution.Converged()

    # if the solver does not converge, return a failure record
    # this is treated as a violation so the optimiser triggers
    if not converged:
        return {
            "converged":              False,
            "ev_bus_voltage_pu":      None,
            "ai_bus_voltage_pu":      None,
            "dist_bus_voltage_pu":    None,
            "transformer_loading_pct": None,
            "voltage_violation":       True,
            "transformer_overload":    True,
            "violations":              ["power_flow_did_not_converge"],
            "n_violations":            1,
            "ev_mw":                   ev_mw,
            "dc_mw":                   dc_mw,
            "total_mw":                ev_mw + dc_mw,
        }

    # read voltages at the three primary monitoring buses
    ev_voltage   = get_bus_voltage(EV_BUS)
    ai_voltage   = get_bus_voltage(AI_BUS)
    dist_voltage = get_bus_voltage(DIST_BUS)

    # read voltages at all 11 monitored buses to count total violations
    all_voltages = {bus: get_bus_voltage(bus) for bus in MONITOR_BUSES}

    # transformer loading — included for completeness but always 0.0 in these runs
    trafo_loading = get_transformer_loading()

    # count every bus that is outside the 0.95 to 1.05 pu safe range
    violations = []
    for bus, v in all_voltages.items():
        if v < V_MIN:
            violations.append("undervoltage_" + bus + ":" + str(v) + "_pu")
        elif v > V_MAX:
            violations.append("overvoltage_" + bus + ":" + str(v) + "_pu")
    if trafo_loading > TRAFO_LIMIT:
        violations.append("transformer_overload:" + str(trafo_loading) + "%")

    return {
        "converged":               converged,
        "ev_bus_voltage_pu":       ev_voltage,
        "ai_bus_voltage_pu":       ai_voltage,
        "dist_bus_voltage_pu":     dist_voltage,
        "transformer_loading_pct": trafo_loading,
        "all_bus_voltages":        all_voltages,
        "voltage_violation":       any("voltage" in v for v in violations),
        "transformer_overload":    any("transformer" in v for v in violations),
        "violations":              violations,
        "n_violations":            len(violations),
        "ev_mw":                   round(ev_mw, 3),
        "dc_mw":                   round(dc_mw, 3),
        "total_mw":                round(ev_mw + dc_mw, 3),
    }


# with different demand levels and that voltages look physically reasonable
if __name__ == "__main__":
    from grid.grid_model import create_grid
    create_grid()

    print("\ntesting power flow on ieee 33-bus feeder...")
    print("-" * 65)

    # test cases ranging from near-zero to high stress demand
    test_cases = [
        ("near zero",  0.1,  0.015, 0.5,  0.05),
        ("low stress", 0.5,  0.075, 2.0,  0.20),
        ("medium",     2.0,  0.300, 8.0,  0.80),
        ("high",       5.0,  0.750, 15.0, 1.50),
    ]

    for label, ev_mw, ev_mvar, dc_mw, dc_mvar in test_cases:
        result = run_powerflow(ev_mw, ev_mvar, dc_mw, dc_mvar)
        print(label.ljust(12),
              "ev bus18:", str(result["ev_bus_voltage_pu"]).ljust(8),
              "ai bus33:", str(result["ai_bus_voltage_pu"]).ljust(8),
              "violations:", result["n_violations"])