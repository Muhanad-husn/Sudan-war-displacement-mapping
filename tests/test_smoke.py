"""Smoke tests — verify the package, the pinned analytic artifacts, and the
key data/viz helpers.

These tests run **offline**: they read the pinned snapshots and processed
parquets committed in ``data/processed/`` rather than re-fetching from the
ACLED / UNHCR / IOM-DTM APIs. The one exception is the GADM polygon set, which
``load_gadm_admin1`` downloads on first use and caches under ``data/raw/gadm/``;
the bivariate tests skip if those files are not present and no network is
available.
"""

import pytest


# ---------------------------------------------------------------------------
# Package / scaffold
# ---------------------------------------------------------------------------
def test_module_imports():
    """The project module imports without error."""
    import sudan_displacement  # noqa: F401


def test_data_dirs_exist():
    """The data directories exist (auto-created on import of data.py)."""
    from sudan_displacement.data import EXTERNAL_DIR, PROCESSED_DIR, RAW_DIR

    assert RAW_DIR.exists()
    assert PROCESSED_DIR.exists()
    assert EXTERNAL_DIR.exists()


def test_diagnostics_import():
    """The diagnostics helpers import."""
    from sudan_displacement.diagnostics import (  # noqa: F401
        before_after,
        compare_alternatives,
        distribution_compare,
        distribution_summary,
        missingness_pattern,
        missingness_summary,
    )


# ---------------------------------------------------------------------------
# Crosswalk (Session 4 — Decision 6)
# ---------------------------------------------------------------------------
def test_crosswalk_loads():
    """The admin-1 crosswalk loads with one row per GADM polygon."""
    from sudan_displacement.data import load_admin1_crosswalk

    xw = load_admin1_crosswalk()
    assert len(xw) == 106  # GADM 4.1 admin-1 units, Sudan + 5 neighbours
    expected = {
        "country",
        "iso3",
        "gadm_gid1",
        "gadm_name1",
        "canonical_pcode",
        "acled_admin1",
        "dtm_pcode",
    }
    assert expected <= set(xw.columns)


def test_crosswalk_sudan_reconciles_18():
    """Sudan reconciles 18/18 states, each with a pcode and an ACLED name."""
    from sudan_displacement.data import load_admin1_crosswalk

    sd = load_admin1_crosswalk().query("iso3 == 'SDN'")
    assert len(sd) == 18
    assert sd["canonical_pcode"].notna().all()
    assert sd["acled_admin1"].notna().all()
    assert sorted(sd["canonical_pcode"]) == [f"SD{n:02d}" for n in range(1, 19)]


# ---------------------------------------------------------------------------
# Pinned analytic layers (Sessions 2, 3, 5, 6)
# ---------------------------------------------------------------------------
def test_acled_snapshot_pinned():
    """The pinned ACLED snapshot exists and covers the Apr 2023 – May 2025 window."""
    import pandas as pd

    from sudan_displacement.data import _latest_snapshot

    acled = pd.read_parquet(_latest_snapshot("acled_snapshot"))
    assert len(acled) > 20_000
    dates = pd.to_datetime(acled["event_date"])
    assert dates.min() >= pd.Timestamp("2023-04-01")
    assert dates.max() <= pd.Timestamp("2025-05-31")


def test_violence_layer_pinned():
    """The violence layer is grid-complete: 18 states x 26 months = 468 rows."""
    from sudan_displacement.data import read_processed

    v = read_processed("violence_admin1_monthly")
    assert len(v) == 18 * 26
    assert {"canonical_pcode", "admin1", "period", "n_events", "fatalities"} <= set(v.columns)
    assert (v["n_events"] >= 0).all()
    assert v["n_events"].sum() == 12_687  # Decision 1 + 2 + 3 totals (S5 handoff)


def test_displacement_layer_pinned():
    """The displacement layer covers 18 states x 22 months = 396 rows."""
    from sudan_displacement.data import read_processed

    d = read_processed("displacement_admin1_monthly")
    assert len(d) == 18 * 22
    assert {"canonical_pcode", "admin1", "period", "idp_present"} <= set(d.columns)
    assert (d["idp_present"] >= 0).all()


def test_displacement_od_pinned():
    """The origin-destination dataset splits into internal + cross-border flows."""
    from sudan_displacement.data import read_processed

    od = read_processed("displacement_od")
    assert {"flow_type", "origin", "destination", "individuals"} <= set(od.columns)
    kinds = set(od["flow_type"].unique())
    assert kinds == {"internal", "cross_border"}
    # Cross-border flows: Sudan -> neighbour countries (UNHCR portal snapshot).
    cb = od[od["flow_type"] == "cross_border"]
    assert (cb["origin"] == "Sudan").all()
    assert len(cb) >= 5


# ---------------------------------------------------------------------------
# Data builders run offline from the pinned snapshots
# ---------------------------------------------------------------------------
def test_build_violence_layer_offline():
    """build_violence_layer rebuilds from the pinned ACLED snapshot, no network."""
    from sudan_displacement.data import build_violence_layer

    v = build_violence_layer(write=False)
    assert len(v) == 18 * 26
    assert v["n_events"].sum() == 12_687


def test_build_displacement_layer_offline():
    """build_displacement_layer rebuilds from the pinned DTM snapshot, no network."""
    from sudan_displacement.data import build_displacement_layer

    d = build_displacement_layer(write=False)
    assert len(d) == 18 * 22
    assert (d["idp_present"] >= 0).all()


# ---------------------------------------------------------------------------
# Visualization helpers (Sessions 7, 8)
# ---------------------------------------------------------------------------
def test_violence_heatmap():
    """violence_heatmap returns a Plotly figure with a single Heatmap trace."""
    import plotly.graph_objects as go

    from sudan_displacement.data import read_processed
    from sudan_displacement.viz import violence_heatmap

    fig = violence_heatmap(read_processed("violence_admin1_monthly"))
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].type == "heatmap"
    # Both value columns are supported.
    assert isinstance(
        violence_heatmap(read_processed("violence_admin1_monthly"), value="fatalities"),
        go.Figure,
    )


def test_crossborder_network():
    """crossborder_network returns a Plotly figure for the cross-border flows."""
    import plotly.graph_objects as go

    from sudan_displacement.data import read_processed
    from sudan_displacement.viz import crossborder_network

    fig = crossborder_network(read_processed("displacement_od"))
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_bivariate_palette():
    """bivariate_palette is a 3x3 grid of hex colours."""
    from sudan_displacement.viz import bivariate_palette

    pal = bivariate_palette()
    assert len(pal) == 3
    assert all(len(row) == 3 for row in pal)
    for row in pal:
        for hexcol in row:
            assert hexcol.startswith("#") and len(hexcol) == 7


@pytest.fixture(scope="module")
def gadm():
    """GADM admin-1 polygons; skip the bivariate tests if unavailable offline."""
    try:
        from sudan_displacement.data import load_gadm_admin1

        return load_gadm_admin1()
    except Exception as exc:  # noqa: BLE001 — network/file failure -> skip, not fail
        pytest.skip(f"GADM polygons unavailable offline: {exc}")


def test_bivariate_layer(gadm):
    """bivariate_layer co-registers both layers into a 3x3-classified GeoDataFrame."""
    from sudan_displacement.data import load_admin1_crosswalk, read_processed
    from sudan_displacement.viz import bivariate_layer

    gdf = bivariate_layer(
        read_processed("violence_admin1_monthly"),
        read_processed("displacement_admin1_monthly"),
        gadm,
        load_admin1_crosswalk(),
    )
    assert len(gdf) == 18  # one row per Sudan admin-1 polygon
    assert {"v_bin", "d_bin", "bi_class"} <= set(gdf.columns)
    assert gdf["bi_class"].between(0, 8).all()


def test_bivariate_choropleth(gadm):
    """bivariate_choropleth renders the hero figure as a Plotly figure."""
    import plotly.graph_objects as go

    from sudan_displacement.data import load_admin1_crosswalk, read_processed
    from sudan_displacement.viz import bivariate_choropleth, bivariate_layer

    gdf = bivariate_layer(
        read_processed("violence_admin1_monthly"),
        read_processed("displacement_admin1_monthly"),
        gadm,
        load_admin1_crosswalk(),
    )
    fig = bivariate_choropleth(gdf)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0
