# grid/grid_model.py
#
# this file loads the ieee 33-bus radial distribution test feeder into opendss
# and defines which buses we monitor for voltage problems during the simulation
#
# the ieee 33-bus feeder comes from baran and wu (1989) and is the most widely
# used standard test network in distribution system research. i used it because
# it represents a typical radial urban distribution grid and gives results that
# can be compared to published studies. i created the dss file from the
# published network data since no stable opendss-formatted version exists publicly
#
# bus18 and bus33 are chosen as injection points because they are at the ends
# of feeder branches — the furthest from the substation and therefore the
# weakest voltage points in the network. placing ev hubs and data centres here
# produces the worst-case voltage stress, which is exactly what we want to test

import opendssdirect as dss
import os

# bus assignments for the two high-density load types
# bus18 is at the end of the main feeder — used for ev charging hubs
# bus33 is at the end of a lateral branch — used for ai data centres
# bus6 is mid-feeder and used as a general distribution monitoring point
EV_BUS   = "bus18"
AI_BUS   = "bus33"
DIST_BUS = "bus6"

# the 11 buses we monitor for voltage violations at every timestep
# spread across the feeder to capture how stress propagates spatially
MONITOR_BUSES = [
    "bus1", "bus6", "bus9", "bus12",
    "bus15", "bus18", "bus22", "bus25",
    "bus28", "bus30", "bus33"
]

# path to the opendss feeder definition file
# built from baran and wu 1989 published impedance and load data
DSS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ieee33bus", "ieee33.dss"
)


def create_grid():
    """
    loads the ieee 33-bus feeder into opendss and runs an initial solve
    to confirm it converges before the simulation starts.

    one important thing i learned: opendss requires set voltagebases to be
    called before calcvoltagebases, otherwise it returns raw voltage magnitudes
    in the hundreds instead of per-unit values near 1.0. the dss file handles
    this but it is worth knowing if modifying the feeder setup.

    returns the dss object ready for power flow calls in powerflow.py
    """
    dss.Basic.Start(0)
    dss.Command("Clear")
    dss.Command("Redirect " + DSS_FILE)

    # check the feeder loaded and solved correctly before starting simulation
    if not dss.Solution.Converged():
        raise RuntimeError(
            "ieee 33-bus feeder failed to converge on initial load. "
            "check dss file at: " + DSS_FILE
        )

    print("ieee 33-bus feeder loaded successfully")
    print("  buses: 33  |  lines: 32  |  base kv: 12.66")
    print("  ev hub bus: " + EV_BUS + "  |  data centre bus: " + AI_BUS)
    return dss


# quick test — run this file directly to verify the grid loads and base voltages look correct
if __name__ == "__main__":
    grid = create_grid()
    dss.Command("Solve")
    print("\nbase case voltage profile:")
    print("-" * 40)
    for bus in MONITOR_BUSES:
        dss.Circuit.SetActiveBus(bus)
        pu     = dss.Bus.puVmagAngle()[0]
        status = "ok" if pu >= 0.95 else "violation"
        print("  " + bus.ljust(8) + str(round(pu, 4)).ljust(10) + status)