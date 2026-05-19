"""Visualization helpers.

This project uses **Plotly** — the headline deliverable is an animated dashboard
with a date slider, so hover state, click-through, and the slider control all
depend on Plotly's interactivity. A static thumbnail of the hero bivariate map
is exported via ``save_figure`` (kaleido) for the GitHub README.

Heatmap, chord/network, and bivariate-choropleth helpers are added in the
visualization sessions; this module currently provides the shared style + save.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = ROOT / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

# Project-wide Plotly default.
pio.templates.default = "plotly_white"

# Human-readable labels for the violence-layer value columns.
_VALUE_LABELS = {"n_events": "Violent events", "fatalities": "Fatalities"}


def violence_heatmap(
    violence: pd.DataFrame,
    value: str = "n_events",
    colorscale: str = "Reds",
) -> go.Figure:
    """Temporal heatmap of the violence layer — admin-1 state x month.

    ``violence`` is the pinned ``violence_admin1_monthly`` frame (one row per
    ``canonical_pcode`` x ``period``). Rows are ordered by window total so the
    most-affected states sit at the top. ``value`` is ``n_events`` or
    ``fatalities``.
    """
    label = _VALUE_LABELS.get(value, value)
    pivot = violence.pivot(index="admin1", columns="period", values=value)
    order = pivot.sum(axis=1).sort_values(ascending=False).index
    pivot = pivot.loc[order]

    x = [p.strftime("%b %Y") for p in pivot.columns]
    fig = go.Figure(
        go.Heatmap(
            z=pivot.to_numpy(),
            x=x,
            y=pivot.index.tolist(),
            colorscale=colorscale,
            colorbar={"title": label, "thickness": 14},
            hovertemplate="%{y}<br>%{x}<br>" + label + ": %{z:,}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{label} by Sudan admin-1 state, monthly (Apr 2023 – May 2025)",
        xaxis={"tickangle": -45, "title": None},
        yaxis={"autorange": "reversed", "title": None},
        height=620,
        width=1000,
        margin={"l": 130, "r": 40, "t": 70, "b": 90},
    )
    return fig


# Quasi-geographic bearings (degrees, 0 = north, clockwise) placing each asylum
# country roughly where it sits relative to Sudan — so the network reads as a map.
_DEST_BEARING = {
    "Egypt": 0,
    "Libya": 320,
    "Chad": 265,
    "Central African Republic": 220,
    "South Sudan": 180,
    "Uganda": 158,
    "Ethiopia": 95,
}


def crossborder_network(
    od: pd.DataFrame,
    title: str = "Sudanese refugee flows to neighbouring countries",
) -> go.Figure:
    """Origin-destination network of cross-border refugee flows.

    ``od`` is the pinned ``displacement_od`` frame; only ``flow_type ==
    'cross_border'`` rows are drawn. Sudan sits at the centre; each destination
    is placed on a quasi-geographic bearing, with edge width and node size
    scaled to the refugee count (UNHCR portal snapshot, Decision 5).
    """
    cb = (
        od[od["flow_type"] == "cross_border"]
        .sort_values("individuals", ascending=False)
        .copy()
    )
    total = int(cb["individuals"].sum())
    vmax = int(cb["individuals"].max())

    pos = {}
    for dest in cb["destination"]:
        b = math.radians(_DEST_BEARING.get(dest, 0.0))
        pos[dest] = (math.sin(b), math.cos(b))

    fig = go.Figure()

    # Edges — one trace each so the line width can carry the flow magnitude.
    for _, r in cb.iterrows():
        x1, y1 = pos[r["destination"]]
        width = 3 + 24 * (r["individuals"] / vmax)
        fig.add_trace(
            go.Scatter(
                x=[0, x1],
                y=[0, y1],
                mode="lines",
                line={"width": width, "color": "rgba(178,24,43,0.45)"},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Destination nodes — area ~ refugee count (sqrt-scaled marker size).
    dx = [pos[d][0] for d in cb["destination"]]
    dy = [pos[d][1] for d in cb["destination"]]
    sizes = 20 + 46 * (cb["individuals"] / vmax) ** 0.5
    fig.add_trace(
        go.Scatter(
            x=dx,
            y=dy,
            mode="markers+text",
            marker={
                "size": sizes,
                "color": "#2166ac",
                "line": {"width": 1.5, "color": "white"},
            },
            text=[
                f"{d}<br>{i / 1e6:.2f}M"
                for d, i in zip(cb["destination"], cb["individuals"])
            ],
            textposition="bottom center",
            textfont={"size": 11},
            hovertext=[
                f"<b>{d}</b><br>{i:,} refugees<br>as of {a}"
                for d, i, a in zip(
                    cb["destination"], cb["individuals"], cb["as_of_date"]
                )
            ],
            hoverinfo="text",
            showlegend=False,
        )
    )

    # Origin node — Sudan at the centre.
    fig.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers+text",
            marker={
                "size": 52,
                "color": "#b2182b",
                "line": {"width": 2, "color": "white"},
            },
            text=["Sudan"],
            textposition="middle center",
            textfont={"size": 12, "color": "white"},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.update_layout(
        title=(
            f"{title}<br>"
            f"<sup>{total / 1e6:.1f}M refugees recorded across 7 countries · "
            f"UNHCR situation portal snapshot</sup>"
        ),
        xaxis={"visible": False, "range": [-1.7, 1.7]},
        yaxis={"visible": False, "range": [-1.7, 1.7], "scaleanchor": "x"},
        height=720,
        width=780,
        showlegend=False,
        margin={"l": 20, "r": 20, "t": 80, "b": 20},
    )
    return fig


def save_figure(fig, name: str, dpi: int = 200) -> Path:
    """Save a figure to ``figures/<name>.png``.

    Auto-detects Plotly, plotnine, and matplotlib figures.
    """
    path = FIGURES_DIR / f"{name}.png"

    if hasattr(fig, "write_image"):
        # Plotly Figure
        fig.write_image(str(path), scale=2)
    elif hasattr(fig, "save"):
        # plotnine ggplot
        fig.save(str(path), dpi=dpi, verbose=False)
    elif hasattr(fig, "savefig"):
        # matplotlib Figure
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
    else:
        raise TypeError(f"Don't know how to save figure of type {type(fig)!r}")

    return path
