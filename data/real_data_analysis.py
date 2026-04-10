# data/real_data_analysis.py
# Empirical calibration using real Madrid and REE data
# Produces two validation figures for the capstone paper

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─────────────────────────────────────────
# LOAD REE DEMAND DATA
# ─────────────────────────────────────────
REE_PATH = os.path.join(os.path.dirname(__file__), "ree_demand_madrid.csv")

# Load the REE export file
ree_raw = pd.read_csv(
    os.path.join(
        os.path.dirname(__file__),
        "../data/ree_demand_madrid.csv"
        if os.path.exists(os.path.join(os.path.dirname(__file__), "../data/ree_demand_madrid.csv"))
        else "ree_demand_madrid.csv"
    ),
    sep=";"
)

ree_raw["datetime"] = pd.to_datetime(ree_raw["datetime"], utc=True)
ree_raw["hour"] = ree_raw["datetime"].dt.hour
ree_raw["minute"] = ree_raw["datetime"].dt.minute
ree_raw["timestep_15min"] = ree_raw["hour"] * 4 + ree_raw["minute"] // 15

# Average across all days in the file
ree_hourly = ree_raw.groupby("timestep_15min")["value"].mean().reset_index()
ree_hourly.columns = ["timestep", "demand_mw"]

# Normalize to 0-1 range for shape comparison
ree_min = ree_hourly["demand_mw"].min()
ree_max = ree_hourly["demand_mw"].max()
ree_hourly["demand_normalized"] = (
    (ree_hourly["demand_mw"] - ree_min) / (ree_max - ree_min)
)

# ─────────────────────────────────────────
# SYNTHETIC AGENT DEMAND CURVE
# ─────────────────────────────────────────
def ev_demand_curve(timestep):
    hour = (timestep % 96) / 4
    morning_peak = np.exp(-0.5 * ((hour - 8) / 1.5) ** 2)
    evening_peak = np.exp(-0.5 * ((hour - 18) / 2.0) ** 2)
    return float(np.clip(morning_peak + evening_peak, 0.05, 1.0))

timesteps = np.arange(96)
synthetic_curve = np.array([ev_demand_curve(t) for t in timesteps])
# Normalize
synthetic_normalized = (synthetic_curve - synthetic_curve.min()) / (
    synthetic_curve.max() - synthetic_curve.min()
)

# ─────────────────────────────────────────
# MADRID EV STATION DATA
# ─────────────────────────────────────────
# From datos.madrid.es - Estaciones de recarga rápida
# Parsed from downloaded dataset
madrid_ev_stats = {
    "public_fast_charge_locations":  99,
    "public_fast_charge_equipment":  195,
    "municipal_fleet_locations":     77,
    "municipal_fleet_connectors":    364,
    "total_charging_points":         559,
    "typical_station_power_kw":      50,
    "high_power_stations_kw":        150,
    "ultra_fast_stations_kw":        350,
}

# District distribution from the dataset
district_counts = {
    "Salamanca":          8,
    "Chamartín":          7,
    "Villa de Vallecas":  10,
    "Fuencarral-El Pardo":6,
    "Vicálvaro":          6,
    "Moncloa-Aravaca":    5,
    "Chamberí":           5,
    "Villaverde":         5,
    "Ciudad Lineal":      5,
    "San Blas-Canillejas":6,
    "Others":            36,
}

# ─────────────────────────────────────────
# SCENARIO CALIBRATION
# ─────────────────────────────────────────
# Each EV hub agent represents a cluster of fast charging stations
# Madrid has 195 fast charge equipment units at 50-150 kW each
# Grouping into hub-scale clusters (20-30 stations per hub)
# gives approximately 6-10 hubs for the city

stations_per_hub = 25  # representative cluster size
n_hubs_madrid = madrid_ev_stats["public_fast_charge_equipment"] // stations_per_hub

# Power per hub at peak (50 kW × 25 stations × 0.7 utilization)
power_per_hub_mw = (stations_per_hub * 50 * 0.7) / 1000

print("=" * 55)
print("MADRID EV INFRASTRUCTURE CALIBRATION")
print("=" * 55)
print(f"Total public fast charge equipment: "
      f"{madrid_ev_stats['public_fast_charge_equipment']}")
print(f"Total charging points (all types):  "
      f"{madrid_ev_stats['total_charging_points']}")
print(f"Modeled as hub clusters ({stations_per_hub} stations/hub): "
      f"{n_hubs_madrid} hubs")
print(f"Peak power per hub (70% utilization): "
      f"{power_per_hub_mw:.1f} MW")
print(f"")
print(f"Scenario calibration:")
print(f"  Low stress:    3 hubs  → ~{3*power_per_hub_mw:.0f} MW EV demand")
print(f"  Medium stress: 6 hubs  → ~{6*power_per_hub_mw:.0f} MW EV demand")
print(f"  High stress:   10 hubs → ~{10*power_per_hub_mw:.0f} MW EV demand")

# ─────────────────────────────────────────
# FIGURE 1: DEMAND CURVE VALIDATION
# ─────────────────────────────────────────
fig = plt.figure(figsize=(16, 6))
gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.35)

# Plot 1: Curve comparison
ax1 = fig.add_subplot(gs[0])
ax1.set_facecolor("#040c14")
fig.patch.set_facecolor("#040c14")

# REE curve - only plot up to 96 timesteps (one day)
ree_plot = ree_hourly[ree_hourly["timestep"] < 96]
ax1.plot(ree_plot["timestep"], ree_plot["demand_normalized"],
         color="#00d4ff", linewidth=2.5, label="REE Spain Demand (normalized)",
         zorder=3)
ax1.plot(timesteps, synthetic_normalized,
         color="#00ffc8", linewidth=2, linestyle="--",
         label="Synthetic EV Agent Curve (normalized)", zorder=3)

# Shade the overlap
ax1.fill_between(timesteps,
                 np.minimum(synthetic_normalized,
                            ree_plot["demand_normalized"].values[:96]
                            if len(ree_plot) >= 96
                            else synthetic_normalized),
                 alpha=0.15, color="#00d4ff", label="Shape overlap region")

# Peak annotations
ax1.axvline(x=32, color="#ffaa00", linewidth=1, linestyle=":",
            alpha=0.7)
ax1.axvline(x=72, color="#ffaa00", linewidth=1, linestyle=":",
            alpha=0.7)
ax1.annotate("Morning\npeak\n(8am)", xy=(32, 0.9),
             fontsize=8, color="#ffaa00",
             fontfamily="monospace", ha="center")
ax1.annotate("Evening\npeak\n(6pm)", xy=(72, 0.9),
             fontsize=8, color="#ffaa00",
             fontfamily="monospace", ha="center")

ax1.set_xlabel("Timestep (15-min intervals, 0 = midnight)",
               color="#4a8fa8", fontfamily="monospace", fontsize=10)
ax1.set_ylabel("Normalized Demand (0-1)",
               color="#4a8fa8", fontfamily="monospace", fontsize=10)
ax1.set_title("Synthetic Agent Demand Curve vs.\nREE Spain Real Demand Profile",
              color="#cce8f0", fontfamily="monospace", fontsize=11,
              fontweight="bold")
ax1.legend(fontsize=8, facecolor="#071220",
           edgecolor="#1a4060", labelcolor="#cce8f0",
           prop={"family": "monospace"})
ax1.tick_params(colors="#4a8fa8")
ax1.spines[:].set_color("#0d2535")
ax1.grid(True, color="#071828", linewidth=0.5, alpha=0.8)
ax1.set_xlim(0, 95)
ax1.set_ylim(-0.05, 1.15)

# Add correlation annotation
from numpy import corrcoef
if len(ree_plot) >= 96:
    corr = corrcoef(synthetic_normalized,
                    ree_plot["demand_normalized"].values[:96])[0, 1]
    ax1.text(0.02, 0.08,
             f"Pearson r = {corr:.3f}",
             transform=ax1.transAxes,
             fontsize=9, color="#00ffc8",
             fontfamily="monospace",
             bbox=dict(boxstyle="round,pad=0.3",
                       facecolor="#071220",
                       edgecolor="#1a4060"))

# ─────────────────────────────────────────
# FIGURE 2: MADRID EV INFRASTRUCTURE
# ─────────────────────────────────────────
ax2 = fig.add_subplot(gs[1])
ax2.set_facecolor("#040c14")

# District distribution bar chart
districts = list(district_counts.keys())
counts = list(district_counts.values())
colors_bar = ["#00d4ff" if c >= 8
              else "#00ffc8" if c >= 6
              else "#4a8fa8"
              for c in counts]

bars = ax2.barh(districts, counts, color=colors_bar,
                alpha=0.85, edgecolor="#0d2535", linewidth=0.5)

# Add count labels
for bar, count in zip(bars, counts):
    ax2.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
             str(count), va="center", ha="left",
             color="#cce8f0", fontsize=8,
             fontfamily="monospace")

ax2.set_xlabel("Number of Fast Charging Locations",
               color="#4a8fa8", fontfamily="monospace", fontsize=10)
ax2.set_title(
    f"Madrid Fast EV Charging Infrastructure\n"
    f"by District (Total: {sum(counts)} locations, "
    f"{madrid_ev_stats['public_fast_charge_equipment']} units)",
    color="#cce8f0", fontfamily="monospace", fontsize=11,
    fontweight="bold")
ax2.tick_params(colors="#4a8fa8", labelsize=8)
ax2.spines[:].set_color("#0d2535")
ax2.grid(True, color="#071828", linewidth=0.5,
         alpha=0.8, axis="x")
ax2.set_facecolor("#040c14")

# Add scenario annotation
ax2.axvline(x=n_hubs_madrid, color="#ffaa00",
            linewidth=1.5, linestyle="--", alpha=0.8)
ax2.text(n_hubs_madrid + 0.1, 1,
         f"~{n_hubs_madrid} modeled\nhubs",
         fontsize=7, color="#ffaa00",
         fontfamily="monospace")

plt.suptitle(
    "Empirical Calibration: Madrid Real-World Data vs. Simulation Parameters\n"
    "Sources: Red Eléctrica de España (REE) · Ayuntamiento de Madrid Open Data",
    color="#cce8f0", fontfamily="monospace",
    fontsize=11, fontweight="bold", y=1.02
)

plt.tight_layout()
output_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "empirical_calibration.png"
)
plt.savefig(output_path, dpi=150, bbox_inches="tight",
            facecolor="#040c14")
print(f"\nFigure saved to: {output_path}")
plt.show()


