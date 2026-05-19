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
    cb = od[od["flow_type"] == "cross_border"].sort_values("individuals", ascending=False).copy()
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
            text=[f"{d}<br>{i / 1e6:.2f}M" for d, i in zip(cb["destination"], cb["individuals"])],
            textposition="bottom center",
            textfont={"size": 11},
            hovertext=[
                f"<b>{d}</b><br>{i:,} refugees<br>as of {a}"
                for d, i, a in zip(cb["destination"], cb["individuals"], cb["as_of_date"])
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


# ---------------------------------------------------------------------------
# Bivariate choropleth — the hero figure (violence x displacement)
# ---------------------------------------------------------------------------

# Corner colours of the 3x3 bivariate palette, as RGB triples. The two single-
# axis corners are the strong ends of ColorBrewer's **PuOr** diverging scheme —
# a scheme explicitly designed to be colour-vision-deficiency safe (orange and
# purple stay well separated under deuteranopia/protanopia, unlike red-green).
# The 9 cells are produced by bilinear interpolation between the four corners,
# which guarantees a perceptually monotone ramp along each axis (move along
# "violence" with displacement fixed -> a clean orange ramp, and vice versa).
_BIV_CORNERS = {
    "low_low": (243, 243, 243),  # low violence,  low displacement  — near white
    "high_v": (179, 88, 6),  # high violence, low displacement  — PuOr orange
    "high_d": (84, 39, 136),  # low violence,  high displacement — PuOr purple
    "high_high": (40, 20, 50),  # high violence, high displacement — dark
}


def bivariate_palette() -> list[list[str]]:
    """3x3 bivariate palette, ``grid[displacement_bin][violence_bin]`` -> hex.

    Bilinearly interpolated between the four :data:`_BIV_CORNERS`. Row 0 is the
    low-displacement row, column 0 the low-violence column.
    """
    c00 = _BIV_CORNERS["low_low"]
    c10 = _BIV_CORNERS["high_v"]
    c01 = _BIV_CORNERS["high_d"]
    c11 = _BIV_CORNERS["high_high"]
    grid = []
    for j in (0.0, 0.5, 1.0):  # displacement fraction (row)
        row = []
        for i in (0.0, 0.5, 1.0):  # violence fraction (column)
            rgb = tuple(
                round(
                    c00[k] * (1 - i) * (1 - j)
                    + c10[k] * i * (1 - j)
                    + c01[k] * (1 - i) * j
                    + c11[k] * i * j
                )
                for k in range(3)
            )
            row.append("#{:02x}{:02x}{:02x}".format(*rgb))
        grid.append(row)
    return grid


def _bin3(s: pd.Series, scheme: str) -> pd.Series:
    """Classify a series into 3 ordinal bins (0/1/2).

    ``scheme="quantile"`` -> tertiles (equal count); ``scheme="fixed"`` ->
    equal-width thirds of the observed range.
    """
    if scheme == "quantile":
        return pd.qcut(s, 3, labels=[0, 1, 2]).astype(int)
    if scheme == "fixed":
        lo, hi = float(s.min()), float(s.max())
        edges = [lo, lo + (hi - lo) / 3, lo + 2 * (hi - lo) / 3, hi]
        return pd.cut(s, edges, labels=[0, 1, 2], include_lowest=True).astype(int)
    raise ValueError(f"unknown scheme {scheme!r}")


def bivariate_layer(
    violence: pd.DataFrame,
    displacement: pd.DataFrame,
    gadm,
    crosswalk: pd.DataFrame,
    scheme: str = "quantile",
):
    """Co-register the two layers on GADM polygons, 3x3 bivariate-classified.

    Violence is the **full-window event total** per state; displacement is the
    **peak in-window IDP stock** per state (chosen in Decision 4 — robust to the
    violence/displacement window offset). Returns a GeoDataFrame with one row
    per Sudan admin-1 polygon and columns ``violence``, ``displacement``,
    ``v_bin``, ``d_bin``, ``bi_class`` (0-8 = ``d_bin * 3 + v_bin``).
    """
    v = violence.groupby("canonical_pcode")["n_events"].sum().rename("violence")
    d = displacement.groupby("canonical_pcode")["idp_present"].max().rename("displacement")
    df = pd.concat([v, d], axis=1).reset_index()
    df["v_bin"] = _bin3(df["violence"], scheme)
    df["d_bin"] = _bin3(df["displacement"], scheme)
    df["bi_class"] = df["d_bin"] * 3 + df["v_bin"]

    key = crosswalk[["canonical_pcode", "gadm_gid1", "acled_admin1"]]
    df = df.merge(key, on="canonical_pcode")
    gdf = gadm.merge(df, left_on="GID_1", right_on="gadm_gid1")
    return gdf


def _add_bivariate_legend(fig, palette: list[list[str]]) -> None:
    """Draw the 3x3 legend (paper coords, bottom-left) onto a bivariate map."""
    x0, y0, cell = 0.060, 0.110, 0.052
    for r in range(3):  # displacement, bottom -> top
        for c in range(3):  # violence, left -> right
            fig.add_shape(
                type="rect",
                xref="paper",
                yref="paper",
                x0=x0 + c * cell,
                x1=x0 + (c + 1) * cell,
                y0=y0 + r * cell,
                y1=y0 + (r + 1) * cell,
                fillcolor=palette[r][c],
                line={"color": "white", "width": 1},
            )
    mid = x0 + 1.5 * cell
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=mid,
        y=y0 - 0.022,
        text="Violence →",
        showarrow=False,
        font={"size": 13},
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=x0 - 0.022,
        y=y0 + 1.5 * cell,
        text="Displacement →",
        showarrow=False,
        font={"size": 13},
        textangle=-90,
    )


def bivariate_choropleth(
    gdf,
    palette: list[list[str]] | None = None,
    title: str = "Sudan: violence and displacement, April 2023 – May 2025",
) -> go.Figure:
    """Hero bivariate choropleth — each state shaded by violence *and* displacement.

    ``gdf`` is the output of :func:`bivariate_layer`. Polygons are filled from
    the 3x3 :func:`bivariate_palette`; an inset 3x3 legend keyed to the same
    palette sits bottom-left.
    """
    palette = palette or bivariate_palette()
    flat = [palette[r][c] for r in range(3) for c in range(3)]  # bi_class order

    gdf = gdf.set_index("GID_1")
    # Discrete 9-step colorscale; z = bi_class + 0.5 lands mid-step.
    colorscale = []
    for k, hexcol in enumerate(flat):
        colorscale += [[k / 9, hexcol], [(k + 1) / 9, hexcol]]

    fig = go.Figure(
        go.Choropleth(
            geojson=gdf.__geo_interface__,
            locations=gdf.index,
            z=gdf["bi_class"] + 0.5,
            zmin=0,
            zmax=9,
            colorscale=colorscale,
            showscale=False,
            marker={"line": {"color": "white", "width": 0.6}},
            customdata=gdf[["acled_admin1", "violence", "displacement"]].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Violent events: %{customdata[1]:,}<br>"
                "Peak IDP stock: %{customdata[2]:,}<extra></extra>"
            ),
        )
    )
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.update_layout(
        title={
            "text": (
                f"{title}<br><sup>Violent events (ACLED) × peak internal "
                "displacement (IOM DTM), by admin-1 state</sup>"
            ),
            "x": 0.5,
            "xanchor": "center",
        },
        height=800,
        width=800,
        margin={"l": 10, "r": 10, "t": 90, "b": 10},
    )
    _add_bivariate_legend(fig, palette)
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
