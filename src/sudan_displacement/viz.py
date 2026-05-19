"""Visualization helpers.

This project uses **Plotly** — the headline deliverable is an animated dashboard
with a date slider, so hover state, click-through, and the slider control all
depend on Plotly's interactivity. A static thumbnail of the hero bivariate map
is exported via ``save_figure`` (kaleido) for the GitHub README.

Heatmap, chord/network, and bivariate-choropleth helpers are added in the
visualization sessions; this module currently provides the shared style + save.
"""

from __future__ import annotations

from pathlib import Path

import plotly.io as pio

ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = ROOT / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

# Project-wide Plotly default.
pio.templates.default = "plotly_white"


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
