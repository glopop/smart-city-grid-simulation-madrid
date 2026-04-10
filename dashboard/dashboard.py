# dashboard/dashboard.py
#

#
# PURPOSE:
#   Presents pre-computed simulation results through an interactive
#   operations-room interface designed for non-technical infrastructure
#   planners. Loads simulation_results.csv and allows scenario exploration
#   without any programming knowledge.
#
# DESIGN DECISIONS:
#   - Pre-computed results (not live simulation) keep the UI instant and
#     responsive regardless of scenario complexity. This is a deliberate
#     choice documented in Section 5.7 of the report.
#   - Timestep slider lets planners scrub through the 24-hour simulation
#     to see exactly when voltage problems emerge — the key planning insight.
#   - Download buttons on every chart support screenshot-free figure export
#     for reports and planning documents.
#   - Plain-English labels alongside technical values make every panel
#     readable by non-engineers (validated in usability survey, Section 6.5).

import os
os.environ["DASH_DEBUG"] = "false"
os.environ["JUPYTER_PLATFORM_DIRS"] = "0"

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# Simulation results are pre-computed by parallel_scenarios.py (MPI execution)
# and saved as a flat CSV. Each row is one 15-minute timestep for one scenario.
# ─────────────────────────────────────────────────────────────────────────────
DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "simulation_results.csv"
)
df = pd.read_csv(DATA_PATH)

# The three scenarios correspond to increasing EV hub and data centre counts.
# See Table 2 in the report for full parameter definitions.
SCENARIOS = {
    "low_stress":    "Low Stress  (3 EV hubs, 1 data centre)",
    "medium_stress": "Medium Stress  (5 EV hubs, 2 data centres)",
    "high_stress":   "High Stress  (8 EV hubs, 3 data centres)",
}

MAX_TIMESTEP = int(df["timestep"].max())   # 95 (0-indexed, 96 steps total)

# ─────────────────────────────────────────────────────────────────────────────
# DESIGN TOKENS
# Centralised palette so every chart and component stays visually consistent.
# Extended to 4-tier voltage health system (safe / borderline / warning / critical)
# after usability feedback asking for richer colour differentiation.
# ─────────────────────────────────────────────────────────────────────────────
C = {
    "bg":       "#020a10",
    "bg2":      "#040d16",
    "card":     "#060f1a",
    "card2":    "#071525",
    "cyan":     "#00d4ff",    # EV hub series colour
    "teal":     "#00ffc8",    # Post-optimisation / dist bus
    "blue":     "#1a8fff",    # Peak demand accent
    "purple":   "#9b6dff",    # Data centre series colour
    "green":    "#00e676",    # SAFE voltage status
    "amber":    "#ffab00",    # BORDERLINE voltage + optimizer markers
    "orange":   "#ff6d00",    # WARNING voltage + pre-optimisation series
    "red":      "#ff1744",    # CRITICAL voltage + violation bars
    "txt":      "#d0eaf8",
    "txt2":     "#5a9fbe",
    "txt3":     "#1e4a62",
    "txt4":     "#0e2535",
    "border":   "#0a1e2e",
    "border2":  "#153550",
    "border3":  "#1e4a6a",
    "grid":     "#060f1c",
}

FM  = "'IBM Plex Mono', 'Courier New', monospace"
FD  = "'Rajdhani', 'Orbitron', monospace"
FSS = "'Inter', 'Segoe UI', sans-serif"


def rgba(hex_color, alpha):
    """Convert hex colour to rgba string for use in CSS and Plotly fills."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ─────────────────────────────────────────────────────────────────────────────
# VOLTAGE STATUS HELPERS
# Per IEEE 1547 and EN 50160, safe operating range is 0.95–1.05 pu.
# Four-tier classification added after usability survey requested richer
# colour differentiation beyond simple green/amber/red.
# ─────────────────────────────────────────────────────────────────────────────
def voltage_color(v):
    if v >= 0.95: return C["green"]
    if v >= 0.90: return C["amber"]
    if v >= 0.85: return C["orange"]
    return C["red"]

def voltage_label(v):
    if v >= 0.95: return "SAFE"
    if v >= 0.90: return "BORDERLINE"
    if v >= 0.85: return "WARNING"
    return "CRITICAL"

def voltage_bar_pct(v):
    """Map voltage to 0–100% for the sidebar gauge bars. 0.5 pu → 0%, 1.05 pu → 100%."""
    return max(0, min(100, (v - 0.5) / 0.55 * 100))


# ─────────────────────────────────────────────────────────────────────────────
# MADRID MAP — IEEE 33-BUS NETWORK OVERLAY
# Four key buses are mapped to Madrid districts for spatial illustration.
# Bus18 (EV hub) and Bus33 (data centre) are the injection points in OpenDSS.
# NOTE: This is an illustrative mapping — the IEEE 33-bus feeder is a standard
# test network (Baran & Wu 1989), not a real Madrid substation topology.
# ─────────────────────────────────────────────────────────────────────────────
BUS_LOCATIONS = {
    "Source":  {"lat": 40.4168, "lon": -3.7038, "label": "⚡ SUBSTATION",  "name": "Puerta del Sol"},
    "DistBus": {"lat": 40.4090, "lon": -3.6920, "label": "◈ DIST BUS",    "name": "Retiro"},
    "EVBus":   {"lat": 40.3990, "lon": -3.6800, "label": "🔌 EV HUB",     "name": "Vallecas · Bus18"},
    "AIBus":   {"lat": 40.4250, "lon": -3.6750, "label": "🖥 DATA CTR",   "name": "Hortaleza · Bus33"},
}
BUS_CONNECTIONS = [("Source", "DistBus"), ("DistBus", "EVBus"), ("DistBus", "AIBus")]


def make_city_map(ev_v, ai_v, dist_v):
    """
    Build the Madrid map figure with colour-coded bus nodes and power lines.
    Called on every scenario change and timestep slider update so the map
    always reflects the voltage state at the selected simulation moment.
    """
    voltages = {"Source": 1.0, "DistBus": dist_v, "EVBus": ev_v, "AIBus": ai_v}
    fig = go.Figure()

    # Power lines — coloured by the weaker of the two connected buses
    for a, b in BUS_CONNECTIONS:
        la, loa = BUS_LOCATIONS[a]["lat"], BUS_LOCATIONS[a]["lon"]
        lb, lob = BUS_LOCATIONS[b]["lat"], BUS_LOCATIONS[b]["lon"]
        fig.add_trace(go.Scattermapbox(
            lat=[la, lb], lon=[loa, lob], mode="lines",
            line=dict(width=3, color=voltage_color(min(voltages[a], voltages[b]))),
            showlegend=False, hoverinfo="skip",
        ))

    # Bus nodes — size reflects importance, colour reflects voltage health
    for bus, info in BUS_LOCATIONS.items():
        v   = voltages[bus]
        col = voltage_color(v)
        fig.add_trace(go.Scattermapbox(
            lat=[info["lat"]], lon=[info["lon"]],
            mode="markers+text",
            marker=dict(size=22, color=col, opacity=0.92),
            text=[info["label"]],
            textposition="top center",
            textfont=dict(family=FM, size=9, color=col),
            hovertext=(
                f"<b>{info['label']}</b><br>"
                f"📍 {info['name']}<br>"
                f"Voltage: <b>{v:.4f} pu</b><br>"
                f"Status: <b>{voltage_label(v)}</b><br>"
                f"<i>Safe range: 0.95–1.05 pu</i>"
            ),
            hoverinfo="text", showlegend=False,
        ))

    fig.update_layout(
        mapbox=dict(style="carto-darkmatter",
                    center=dict(lat=40.410, lon=-3.690), zoom=11.5),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        hoverlabel=dict(bgcolor=C["card2"], bordercolor=C["border3"],
                        font=dict(family=FM, size=11, color=C["txt"])),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# REUSABLE UI COMPONENTS
# ─────────────────────────────────────────────────────────────────────────────

def metric_card(icon, title, value, unit, subtitle, color, description=None):
    """
    Summary metric card shown across the top of the dashboard.
    Each card shows a large technical value plus a plain-English description
    so non-engineer planners understand what the number means in practice.
    """
    return html.Div([
        html.Div([
            html.Span(icon, style={"fontSize": "13px", "marginRight": "6px"}),
            html.Span(title, style={
                "fontFamily": FM, "fontSize": "8.5px",
                "color": C["txt3"], "letterSpacing": "1.5px",
                "textTransform": "uppercase",
            }),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "10px"}),
        html.Div([
            html.Span(value, style={
                "fontFamily": FD, "fontSize": "28px", "fontWeight": "700",
                "color": color, "textShadow": f"0 0 18px {color}55", "lineHeight": "1",
            }),
            html.Span(f" {unit}", style={
                "fontFamily": FM, "fontSize": "10px", "color": C["txt2"],
            }),
        ], style={"marginBottom": "7px"}),
        html.Div(subtitle, style={
            "fontFamily": FM, "fontSize": "8px", "color": C["txt2"], "marginBottom": "5px",
        }),
        *([ html.Div(description, style={
            "fontFamily": FSS, "fontSize": "9.5px", "color": C["txt3"],
            "lineHeight": "1.45", "borderTop": f"1px solid {C['border']}",
            "paddingTop": "6px", "marginTop": "3px",
        })] if description else []),
    ], style={
        "background": f"linear-gradient(145deg, {C['card2']} 0%, {C['card']} 100%)",
        "border": f"1px solid {C['border2']}",
        "borderTop": f"2px solid {color}",
        "borderRadius": "4px",
        "padding": "13px 15px",
        "flex": "1", "minWidth": "140px",
        "boxShadow": f"0 6px 22px rgba(0,0,0,0.55), inset 0 1px 0 {color}15",
    })


def gauge_row(label, v, color):
    """Horizontal bar gauge for sidebar voltage readings."""
    return html.Div([
        html.Div([
            html.Span(label, style={"fontFamily": FM, "fontSize": "8px",
                                    "color": C["txt3"], "width": "68px",
                                    "display": "inline-block", "letterSpacing": "1px"}),
            html.Span(f"{v:.3f} pu", style={"fontFamily": FM, "fontSize": "11px",
                                              "color": color, "fontWeight": "500"}),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "3px"}),
        html.Div(html.Div(style={
            "width": f"{voltage_bar_pct(v)}%", "height": "4px",
            "background": f"linear-gradient(90deg, {rgba(color, 0.35)}, {color})",
            "borderRadius": "2px",
        }), style={"background": C["bg"], "borderRadius": "2px", "height": "4px",
                   "marginBottom": "8px", "border": f"1px solid {C['border']}"}),
    ])


def alert_item(voltage, severity, timestep):
    """Single alert row for the sidebar alerts list."""
    colors  = {"CRITICAL": C["red"], "HIGH": C["orange"], "MEDIUM": C["amber"]}
    labels  = {"CRITICAL": "Voltage collapsed below 0.85 pu",
               "HIGH":     "Voltage very low (0.85–0.90 pu)",
               "MEDIUM":   "Borderline voltage (0.90–0.95 pu)"}
    color   = colors.get(severity, C["amber"])
    return html.Div([
        html.Div([
            html.Span(severity, style={
                "background": rgba(color, 0.18), "border": f"1px solid {color}",
                "color": color, "fontFamily": FM, "fontSize": "7.5px",
                "letterSpacing": "1px", "padding": "2px 5px", "borderRadius": "2px",
            }),
            html.Span(f"  t={timestep}", style={"fontFamily": FM, "fontSize": "9px",
                                                 "color": C["txt2"], "marginLeft": "6px"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "3px"}),
        html.Div(f"EV Hub: {voltage:.3f} pu", style={"fontFamily": FM, "fontSize": "9.5px",
                                                      "color": C["txt"]}),
        html.Div(labels.get(severity, ""), style={"fontFamily": FSS, "fontSize": "8.5px",
                                                   "color": C["txt3"], "marginTop": "2px"}),
    ], style={
        "background": rgba(color, 0.05), "border": f"1px solid {rgba(color, 0.18)}",
        "borderLeft": f"3px solid {color}", "borderRadius": "3px",
        "padding": "7px 9px", "marginBottom": "5px",
    })


# ─────────────────────────────────────────────────────────────────────────────
# APP INITIALISATION
# External fonts: IBM Plex Mono (monospace data values), Rajdhani/Orbitron
# (display headers), Inter (plain-English descriptions for non-engineers).
# ─────────────────────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700"
        "&family=IBM+Plex+Mono:wght@300;400;500"
        "&family=Orbitron:wght@700;900"
        "&family=Inter:wght@300;400;500&display=swap",
    ],
    title="Smart City Grid · Madrid",
)

# Shared style constants
SEC = {   # section label style
    "fontFamily": FM, "fontSize": "8px", "letterSpacing": "3px",
    "textTransform": "uppercase", "color": C["txt3"],
    "marginBottom": "10px", "paddingBottom": "6px",
    "borderBottom": f"1px solid {C['border']}",
}
CARD = {  # chart card container style
    "background": C["card"], "border": f"1px solid {C['border2']}",
    "borderRadius": "5px", "padding": "13px 15px",
}

# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT
# Three zones: sticky header, left sidebar (scenario + status + alerts),
# main content area (metric cards + charts).
# ─────────────────────────────────────────────────────────────────────────────
app.layout = html.Div([

    # ── HEADER ───────────────────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.Div("◈", style={"color": C["cyan"], "fontSize": "20px",
                                  "textShadow": f"0 0 18px {C['cyan']}",
                                  "marginRight": "12px"}),
            html.Div([
                html.Div("SMART CITY GRID SIMULATION", style={
                    "fontFamily": FD, "fontSize": "14px", "fontWeight": "700",
                    "color": C["txt"], "letterSpacing": "4px",
                }),
                html.Div("Madrid  ·  IEEE 33-Bus Distribution Feeder  ·  MPI Parallel  ·  Agent-Based",
                         style={"fontFamily": FM, "fontSize": "8px",
                                "color": C["txt3"], "letterSpacing": "2px", "marginTop": "2px"}),
            ]),
        ], style={"display": "flex", "alignItems": "center"}),

        html.Div([
            html.Div(id="clock", style={"fontFamily": FM, "fontSize": "12px",
                                         "color": C["teal"],
                                         "textShadow": f"0 0 10px {C['teal']}77",
                                         "textAlign": "right"}),
            html.Div("CAPSTONE · IE UNIVERSITY · APRIL 2026",
                     style={"fontFamily": FM, "fontSize": "7px", "color": C["txt4"],
                            "letterSpacing": "2px", "textAlign": "right", "marginTop": "2px"}),
        ]),
    ], style={
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "9px 22px",
        "background": f"linear-gradient(90deg, {C['bg2']} 0%, {C['bg']} 60%, {C['bg2']} 100%)",
        "borderBottom": f"1px solid {C['border2']}",
        "boxShadow": f"0 2px 36px rgba(0,0,0,0.8), 0 1px 0 {C['border3']}",
        "position": "sticky", "top": "0", "zIndex": "100",
    }),

    dcc.Interval(id="clock-tick", interval=1000),

    # ── BODY ─────────────────────────────────────────────────────────────────
    html.Div([

        # ── SIDEBAR ──────────────────────────────────────────────────────────
        html.Div([

            # Scenario selector
            html.Div("/ SCENARIO", style=SEC),
            html.Div([
                html.Div("Select a demand level to explore:", style={
                    "fontFamily": FSS, "fontSize": "9.5px",
                    "color": C["txt3"], "marginBottom": "7px",
                }),
                dcc.Dropdown(
                    id="scenario-sel",
                    options=[{"label": v, "value": k} for k, v in SCENARIOS.items()],
                    value="medium_stress", clearable=False,
                    style={"background": C["card2"], "color": C["txt"],
                           "border": f"1px solid {C['border2']}", "borderRadius": "3px",
                           "fontFamily": FM, "fontSize": "10px"},
                ),
            ], style={"marginBottom": "20px"}),

            # Timestep slider
            # Key interactivity feature: planners can scrub through the 24-hour
            # simulation to see exactly when voltage problems emerge and when
            # the optimiser fires. Each step = 15 minutes of simulated time.
            html.Div("/ SIMULATION TIME", style=SEC),
            html.Div([
                html.Div(id="slider-readout", style={
                    "fontFamily": FM, "fontSize": "10px", "color": C["cyan"],
                    "marginBottom": "6px",
                }),
                dcc.Slider(
                    id="timestep-slider",
                    min=0, max=MAX_TIMESTEP, step=1, value=MAX_TIMESTEP,
                    marks={0: {"label": "00:00", "style": {"color": C["txt3"], "fontSize": "8px"}},
                           24: {"label": "06:00", "style": {"color": C["txt3"], "fontSize": "8px"}},
                           48: {"label": "12:00", "style": {"color": C["txt3"], "fontSize": "8px"}},
                           72: {"label": "18:00", "style": {"color": C["txt3"], "fontSize": "8px"}},
                           95: {"label": "23:45", "style": {"color": C["txt3"], "fontSize": "8px"}}},
                    tooltip={"always_visible": False, "placement": "bottom"},
                    updatemode="drag",
                ),
                html.Div("Drag to scrub through the 24-hour day", style={
                    "fontFamily": FSS, "fontSize": "8.5px", "color": C["txt4"],
                    "marginTop": "4px",
                }),
            ], style={"marginBottom": "20px"}),

            # Live voltage gauges
            html.Div("/ VOLTAGE AT SELECTED TIME", style=SEC),
            html.Div(id="voltage-gauges", style={"marginBottom": "20px"}),

            # Grid status
            html.Div("/ GRID STATUS", style=SEC),
            html.Div(id="grid-status", style={"marginBottom": "20px"}),

            # Alerts
            html.Div("/ RECENT ALERTS", style=SEC),
            html.Div(id="alerts", style={"marginBottom": "20px"}),

            # Voltage colour key
            html.Div([
                html.Div("VOLTAGE COLOUR KEY", style={
                    "fontFamily": FM, "fontSize": "7.5px", "letterSpacing": "2px",
                    "color": C["txt4"], "marginBottom": "8px",
                }),
                *[html.Div([
                    html.Span("●", style={"color": col, "marginRight": "6px", "fontSize": "10px"}),
                    html.Span(lbl, style={"color": col, "fontFamily": FM, "fontSize": "8.5px"}),
                    html.Span(f"  {rng}", style={"color": C["txt4"], "fontFamily": FSS,
                                                   "fontSize": "8px"}),
                ], style={"marginBottom": "4px"})
                for col, lbl, rng in [
                    (C["green"],  "SAFE",       "≥ 0.95 pu"),
                    (C["amber"],  "BORDERLINE", "0.90–0.95 pu"),
                    (C["orange"], "WARNING",    "0.85–0.90 pu"),
                    (C["red"],    "CRITICAL",   "< 0.85 pu"),
                ]],
            ], style={"background": C["bg"], "border": f"1px solid {C['border']}",
                      "borderRadius": "3px", "padding": "10px"}),

        ], style={
            "width": "245px", "minWidth": "245px", "padding": "16px 13px",
            "background": C["bg2"], "borderRight": f"1px solid {C['border']}",
            "height": "calc(100vh - 46px)", "overflowY": "auto", "boxSizing": "border-box",
        }),

        # ── MAIN CONTENT ─────────────────────────────────────────────────────
        html.Div([

            # Metric cards row
            html.Div(id="cards", style={
                "display": "flex", "gap": "9px",
                "marginBottom": "11px", "flexWrap": "wrap",
            }),

            # Row 1: Map + Voltage chart
            html.Div([
                # Map — larger and more prominent than previous version
                html.Div([
                    html.Div([
                        html.Span("/ MADRID DISTRIBUTION GRID", style={
                            **SEC, "marginBottom": "0", "borderBottom": "none",
                            "display": "inline",
                        }),
                        html.Span("  Hover any node for voltage details  ·  Updates with slider",
                                  style={"fontFamily": FSS, "fontSize": "8.5px",
                                         "color": C["txt4"]}),
                    ], style={"marginBottom": "9px", "borderBottom": f"1px solid {C['border']}",
                               "paddingBottom": "8px"}),
                    dcc.Graph(
                        id="city-map",
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
                                "toImageButtonOptions": {"format": "png", "filename": "madrid_grid_map",
                                                         "scale": 2}},
                        style={"height": "330px"},
                    ),
                    html.Div(
                        "⚠ Bus locations mapped to Madrid districts for illustration only. "
                        "The IEEE 33-bus feeder (Baran & Wu 1989) is a standard test network, "
                        "not a specific Madrid substation.",
                        style={"fontFamily": FSS, "fontSize": "7.5px", "color": C["txt4"],
                               "marginTop": "6px", "fontStyle": "italic", "lineHeight": "1.5"},
                    ),
                ], style={**CARD, "flex": "1.4", "marginRight": "10px"}),

                # Voltage profile chart
                html.Div([
                    html.Div([
                        html.Span("/ VOLTAGE OVER TIME", style={
                            **SEC, "marginBottom": "0", "borderBottom": "none", "display": "inline",
                        }),
                    ], style={"marginBottom": "5px", "borderBottom": f"1px solid {C['border']}",
                               "paddingBottom": "7px"}),
                    html.Div(
                        "How stable is grid voltage across 24 hours? "
                        "Values below the red line (0.95 pu) mean voltage is dangerously low. "
                        "The vertical marker shows your selected time.",
                        style={"fontFamily": FSS, "fontSize": "8.5px", "color": C["txt3"],
                               "marginBottom": "6px", "lineHeight": "1.4"},
                    ),
                    dcc.Graph(
                        id="voltage-chart",
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
                                "toImageButtonOptions": {"format": "png", "scale": 2,
                                                         "filename": "voltage_profile"}},
                        style={"height": "280px"},
                    ),
                ], style={**CARD, "flex": "1"}),

            ], style={"display": "flex", "marginBottom": "9px"}),

            # Row 2: Demand · Violations · Optimizer
            html.Div([

                html.Div([
                    html.Div("/ ELECTRICITY DEMAND", style=SEC),
                    html.Div("EV charging hubs (cyan) vs AI data centres (purple) over 24 hours. "
                             "The staircase pattern shows data centre capacity expanding.",
                             style={"fontFamily": FSS, "fontSize": "8.5px",
                                    "color": C["txt3"], "marginBottom": "6px"}),
                    dcc.Graph(
                        id="demand-chart",
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
                                "toImageButtonOptions": {"format": "png", "scale": 2,
                                                         "filename": "demand_profile"}},
                        style={"height": "195px"},
                    ),
                ], style={**CARD, "flex": "1", "marginRight": "9px"}),

                html.Div([
                    html.Div("/ VOLTAGE VIOLATIONS", style=SEC),
                    html.Div("How many grid connection points had unsafe voltage at each moment. "
                             "▼ markers show when the optimizer stepped in.",
                             style={"fontFamily": FSS, "fontSize": "8.5px",
                                    "color": C["txt3"], "marginBottom": "6px"}),
                    dcc.Graph(
                        id="violations-chart",
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
                                "toImageButtonOptions": {"format": "png", "scale": 2,
                                                         "filename": "violations"}},
                        style={"height": "195px"},
                    ),
                ], style={**CARD, "flex": "1", "marginRight": "9px"}),

                html.Div([
                    html.Div("/ OPTIMIZER EFFECT", style=SEC),
                    html.Div("Voltage before (orange) vs after (teal) load rescheduling. "
                             "Points above the red line = safe. Gaps show where even rescheduling wasn't enough.",
                             style={"fontFamily": FSS, "fontSize": "8.5px",
                                    "color": C["txt3"], "marginBottom": "6px"}),
                    dcc.Graph(
                        id="opt-chart",
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
                                "toImageButtonOptions": {"format": "png", "scale": 2,
                                                         "filename": "optimizer_effect"}},
                        style={"height": "195px"},
                    ),
                ], style={**CARD, "flex": "1"}),

            ], style={"display": "flex"}),

        ], style={
            "flex": "1", "padding": "13px 15px",
            "overflowY": "auto", "height": "calc(100vh - 46px)",
            "boxSizing": "border-box",
        }),

    ], style={"display": "flex", "height": "calc(100vh - 46px)"}),

], style={"background": C["bg"], "minHeight": "100vh",
          "overflow": "hidden", "color": C["txt"]})


# ─────────────────────────────────────────────────────────────────────────────
# PLOTLY CHART BASE LAYOUT
# Applied to every chart to maintain visual consistency across all panels.
# ─────────────────────────────────────────────────────────────────────────────
def plot_base(y_title=None, x_title=None, y_range=None):
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=C["bg"],
        font=dict(family=FM, color=C["txt2"], size=9),
        xaxis=dict(gridcolor=C["grid"], linecolor=C["border2"], tickcolor=C["txt3"],
                   zerolinecolor=C["border"],
                   title=dict(text=x_title or "", font=dict(size=9))),
        yaxis=dict(gridcolor=C["grid"], linecolor=C["border2"], tickcolor=C["txt3"],
                   zerolinecolor=C["border"],
                   title=dict(text=y_title or "", font=dict(size=9))),
        legend=dict(bgcolor="rgba(2,10,16,0.88)", bordercolor=C["border2"],
                    borderwidth=1, font=dict(size=9, family=FM)),
        margin=dict(l=42, r=12, t=6, b=34),
        hoverlabel=dict(bgcolor=C["card2"], bordercolor=C["border3"],
                        font=dict(family=FM, size=10, color=C["txt"])),
    )
    if y_range:
        layout["yaxis"]["range"] = y_range
    return layout


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(Output("clock", "children"), Input("clock-tick", "n_intervals"))
def tick(_):
    return datetime.now().strftime("%H:%M:%S  ·  %d %b %Y")


@app.callback(
    Output("slider-readout", "children"),
    [Input("timestep-slider", "value"), Input("scenario-sel", "value")]
)
def update_slider_readout(t, scenario):
    """Show human-readable time for the selected timestep."""
    # Each step = 15 minutes; timestep 0 = 00:00
    hours   = (t * 15) // 60
    minutes = (t * 15) % 60
    d = df[(df["scenario"] == scenario) & (df["timestep"] == t)]
    if d.empty:
        return f"t={t}  ({hours:02d}:{minutes:02d})"
    ev_v    = d.iloc[0]["ev_bus_voltage_pu"]
    col     = voltage_color(ev_v)
    return html.Span([
        html.Span(f"{hours:02d}:{minutes:02d} ", style={"color": C["cyan"]}),
        html.Span(f"(t={t})  ", style={"color": C["txt3"]}),
        html.Span(f"EV: {ev_v:.3f} pu", style={"color": col}),
    ])


@app.callback(
    [
        Output("cards",           "children"),
        Output("voltage-gauges",  "children"),
        Output("grid-status",     "children"),
        Output("alerts",          "children"),
        Output("city-map",        "figure"),
        Output("voltage-chart",   "figure"),
        Output("demand-chart",    "figure"),
        Output("violations-chart","figure"),
        Output("opt-chart",       "figure"),
    ],
    [Input("scenario-sel", "value"), Input("timestep-slider", "value")],
)
def update(scenario, t):
    """
    Main callback — fires on scenario change or timestep slider move.
    All eight dashboard components update simultaneously so every panel
    always reflects the same simulation moment and scenario.
    """
    d    = df[df["scenario"] == scenario].copy()
    # Slice up to the selected timestep for cumulative metrics
    d_up_to_t = d[d["timestep"] <= t]
    # Row at exactly the selected timestep for point-in-time values
    row  = d[d["timestep"] == t].iloc[0] if len(d[d["timestep"] == t]) > 0 else d.iloc[-1]

    # Summary statistics (over the whole scenario, not just up to t)
    avg_v   = d["ev_bus_voltage_pu"].mean()
    min_v   = d["ev_bus_voltage_pu"].min()
    total_v = int(d["n_violations_pre"].sum())
    opt_n   = int(d["optimization_triggered"].sum())
    avg_r   = d["demand_reduction_mw"].mean()
    peak_mw = d["total_mw"].max()
    feas    = (d["optimization_feasible"].sum() / opt_n * 100) if opt_n > 0 else 100.0

    vc_avg  = voltage_color(avg_v)
    ev_v    = row["ev_bus_voltage_pu"]
    ai_v    = row["ai_bus_voltage_pu"]
    dt_v    = row["dist_bus_voltage_pu"]

    # ── METRIC CARDS ─────────────────────────────────────────────────────────
    cards = [
        metric_card("⚡", "Avg Voltage (full day)",
                    f"{avg_v:.3f}", "pu",
                    f"Min observed: {min_v:.3f} pu  |  Safe: 0.95–1.05 pu",
                    vc_avg,
                    "How healthy is average grid voltage? Below 0.95 is a real problem."),
        metric_card("⚠", "Total Violations",
                    str(total_v), "events",
                    "Times any bus dropped below safe voltage",
                    C["red"] if total_v > 200 else C["orange"] if total_v > 50 else C["amber"],
                    "Each event means a part of the grid had dangerously low voltage."),
        metric_card("🔌", "Peak Demand",
                    f"{peak_mw:.1f}", "MW",
                    "Highest combined load across all agents",
                    C["blue"],
                    "The maximum electricity pulled from the grid at any single moment."),
        metric_card("🤖", "Optimizer Runs",
                    str(opt_n), "cycles",
                    f"Valid schedule found: {feas:.0f}% of the time",
                    C["teal"],
                    "Times the system rescheduled loads to prevent voltage collapse."),
        metric_card("📉", "Avg Load Deferred",
                    f"{avg_r:.1f}", "MW",
                    "Per optimizer cycle",
                    C["purple"],
                    "How much electricity was shifted to off-peak hours per optimizer run."),
    ]

    # ── VOLTAGE GAUGES ───────────────────────────────────────────────────────
    gauges = html.Div([
        html.Div(f"At selected time (t={t}):", style={
            "fontFamily": FSS, "fontSize": "9px", "color": C["txt4"], "marginBottom": "9px",
        }),
        gauge_row("EV HUB",   ev_v, voltage_color(ev_v)),
        gauge_row("DATA CTR", ai_v, voltage_color(ai_v)),
        gauge_row("DIST BUS", dt_v, voltage_color(dt_v)),
    ], style={"background": rgba(C["card2"], 0.6), "border": f"1px solid {C['border']}",
               "borderRadius": "3px", "padding": "10px"})

    # ── GRID STATUS ──────────────────────────────────────────────────────────
    sc  = voltage_color(ev_v)
    st  = voltage_label(ev_v)
    plain = {
        "SAFE":       "Operating normally. All key buses within safe voltage range.",
        "BORDERLINE": "Voltage is borderline. The optimiser may be needed soon.",
        "WARNING":    "Voltage is low. The optimiser is actively rescheduling loads.",
        "CRITICAL":   "Voltage has collapsed. Load scheduling alone cannot fix this — "
                      "physical grid reinforcement is needed.",
    }
    grid_status = html.Div([
        html.Div(st, style={"fontFamily": FD, "fontSize": "19px", "fontWeight": "700",
                             "color": sc, "textShadow": f"0 0 14px {sc}77",
                             "marginBottom": "7px", "letterSpacing": "2px"}),
        html.Div(plain.get(st, ""), style={"fontFamily": FSS, "fontSize": "9px",
                                            "color": C["txt2"], "lineHeight": "1.5"}),
    ], style={"background": rgba(sc, 0.06), "border": f"1px solid {rgba(sc, 0.2)}",
               "borderRadius": "3px", "padding": "11px"})

    # ── ALERTS ───────────────────────────────────────────────────────────────
    # Show the 5 most recent timesteps where violations were detected,
    # giving planners a quick summary of where problems are concentrated.
    recent = d[d["n_violations_pre"] > 0].tail(5)
    alert_list = []
    for _, r in recent.iterrows():
        v   = r["ev_bus_voltage_pu"]
        sev = "CRITICAL" if v < 0.85 else "HIGH" if v < 0.90 else "MEDIUM"
        alert_list.append(alert_item(v, sev, int(r["timestep"])))
    alerts = html.Div(alert_list) if alert_list else html.Div(
        "✓  No violations detected",
        style={"fontFamily": FSS, "fontSize": "10px", "color": C["green"]},
    )

    # ── CITY MAP ─────────────────────────────────────────────────────────────
    city_fig = make_city_map(ev_v, ai_v, dt_v)

    # ── VOLTAGE CHART — with vertical timestep marker ─────────────────────
    # The vertical line moves with the slider so planners can see what
    # voltage conditions look like at any specific point in the day.
    vfig = go.Figure()
    vfig.add_hrect(y0=0, y1=0.95, fillcolor=rgba(C["red"], 0.04), line_width=0)
    vfig.add_trace(go.Scatter(
        x=d["timestep"], y=d["ev_bus_voltage_pu"], name="EV Hub (Bus18)",
        line=dict(color=C["cyan"], width=2),
        fill="tozeroy", fillcolor=rgba(C["cyan"], 0.06),
        hovertemplate="t=%{x}  %{y:.4f} pu<extra>EV Hub</extra>",
    ))
    vfig.add_trace(go.Scatter(
        x=d["timestep"], y=d["ai_bus_voltage_pu"], name="Data Centre (Bus33)",
        line=dict(color=C["purple"], width=1.5, dash="dot"),
        hovertemplate="t=%{x}  %{y:.4f} pu<extra>Data Centre</extra>",
    ))
    vfig.add_trace(go.Scatter(
        x=d["timestep"], y=d["dist_bus_voltage_pu"], name="Distribution Bus",
        line=dict(color=C["txt3"], width=1, dash="dash"),
        hovertemplate="t=%{x}  %{y:.4f} pu<extra>Dist Bus</extra>",
    ))
    vfig.add_hline(y=0.95, line=dict(color=C["red"], width=1, dash="dot"),
                   annotation_text="Min safe (0.95)",
                   annotation_font=dict(color=C["red"], size=8))
    vfig.add_hline(y=1.05, line=dict(color=C["amber"], width=1, dash="dot"),
                   annotation_text="Max safe (1.05)",
                   annotation_font=dict(color=C["amber"], size=8))
    # Vertical slider marker — shows selected timestep across the chart
    vfig.add_vline(x=t, line=dict(color=C["cyan"], width=1.5, dash="dot"),
                   annotation_text=f"t={t}",
                   annotation_font=dict(color=C["cyan"], size=8))
    vfig.update_layout(**plot_base("Voltage (pu)", "15-min Interval", [0.0, 1.15]))

    # ── DEMAND CHART ─────────────────────────────────────────────────────────
    dfig = go.Figure()
    dfig.add_trace(go.Scatter(
        x=d["timestep"], y=d["ev_mw"], name="EV Charging Hubs",
        line=dict(color=C["cyan"], width=2),
        stackgroup="one", fillcolor=rgba(C["cyan"], 0.2),
        hovertemplate="t=%{x}  %{y:.2f} MW<extra>EV Hubs</extra>",
    ))
    dfig.add_trace(go.Scatter(
        x=d["timestep"], y=d["dc_mw"], name="AI Data Centres",
        line=dict(color=C["purple"], width=2),
        stackgroup="one", fillcolor=rgba(C["purple"], 0.2),
        hovertemplate="t=%{x}  %{y:.2f} MW<extra>Data Centres</extra>",
    ))
    dfig.add_vline(x=t, line=dict(color=C["cyan"], width=1.5, dash="dot"))
    dfig.update_layout(**plot_base("Demand (MW)", "15-min Interval"))

    # ── VIOLATIONS CHART ─────────────────────────────────────────────────────
    viol_colors = [C["red"] if v > 0 else C["green"] for v in d["n_violations_pre"]]
    viol_fig = go.Figure()
    viol_fig.add_trace(go.Bar(
        x=d["timestep"], y=d["n_violations_pre"], name="Buses in violation",
        marker=dict(color=viol_colors, opacity=0.85),
        hovertemplate="t=%{x}  %{y} buses in violation<extra></extra>",
    ))
    opt_ts = d[d["optimization_triggered"] == 1]
    if len(opt_ts) > 0:
        viol_fig.add_trace(go.Scatter(
            x=opt_ts["timestep"],
            y=[d["n_violations_pre"].max() * 0.88] * len(opt_ts),
            mode="markers", name="Optimizer triggered",
            marker=dict(symbol="triangle-down", size=6, color=C["amber"], opacity=0.9),
            hovertemplate="t=%{x}  Optimizer ran<extra></extra>",
        ))
    viol_fig.add_vline(x=t, line=dict(color=C["cyan"], width=1.5, dash="dot"))
    vl = plot_base("Buses Outside Safe Range", "15-min Interval")
    vl["bargap"] = 0.08
    viol_fig.update_layout(**vl)

    # ── OPTIMIZER COMPARISON CHART ────────────────────────────────────────────
    opt_d = d[(d["optimization_triggered"] == 1) & (d["post_opt_ev_voltage"].notna())]
    ofig  = go.Figure()
    if len(opt_d) > 0:
        ofig.add_trace(go.Scatter(
            x=opt_d["timestep"], y=opt_d["ev_bus_voltage_pu"],
            name="Before rescheduling", mode="markers",
            marker=dict(color=C["orange"], size=5, opacity=0.75),
            hovertemplate="t=%{x}  Before: %{y:.4f} pu<extra></extra>",
        ))
        ofig.add_trace(go.Scatter(
            x=opt_d["timestep"], y=opt_d["post_opt_ev_voltage"],
            name="After rescheduling", mode="markers",
            marker=dict(color=C["teal"], size=5, opacity=0.75, symbol="triangle-up"),
            hovertemplate="t=%{x}  After: %{y:.4f} pu<extra></extra>",
        ))
        ofig.add_hline(y=0.95, line=dict(color=C["red"], width=1, dash="dot"),
                       annotation_text="Safe threshold",
                       annotation_font=dict(color=C["red"], size=8))
    ofig.update_layout(**plot_base("EV Hub Voltage (pu)", "15-min Interval"))

    return (cards, gauges, grid_status, alerts,
            city_fig, vfig, dfig, viol_fig, ofig)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 58)
    print("  Smart City Grid · Madrid — Simulation Dashboard")
    print("  http://127.0.0.1:8050")
    print("  Use the scenario dropdown and time slider to explore.")
    print("=" * 58 + "\n")
    app.run(debug=True, port=8050)