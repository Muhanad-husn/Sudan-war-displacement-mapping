"""Sudan war: violence x displacement — animated dashboard.

The project's primary interactive deliverable. A month slider (with a Play
button) scrubs both analytic layers in lockstep:

- **violence** — ACLED violent events / fatalities by Sudan admin-1 state,
  monthly, April 2023 – May 2025 (26 months).
- **displacement** — IOM DTM present-IDP stock by admin-1 state, monthly,
  August 2023 – May 2025 (22 months).

The two layers do not start in the same month (Decision 7 — the DTM
``(Overview)`` operation only begins Aug 2023), so the slider runs on the
violence layer's longer timeline and the displacement map shows an explicit
"no data" state for April–July 2023.

Run with::

    streamlit run app/streamlit_dashboard.py
"""

from __future__ import annotations

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from sudan_displacement import data, viz

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Sudan: violence & displacement",
    page_icon="🇸🇩",
    layout="wide",
)

PLAY_DELAY_S = 0.75  # seconds between auto-advanced months

VALUE_LABELS = {"n_events": "Violent events", "fatalities": "Fatalities"}


# --------------------------------------------------------------------------
# Cached data loaders
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading analytic layers…")
def load_layers() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """The three pinned analytic parquets — violence, displacement, O-D."""
    violence = data.read_processed("violence_admin1_monthly")
    displacement = data.read_processed("displacement_admin1_monthly")
    od = data.read_processed("displacement_od")
    return violence, displacement, od


@st.cache_data(show_spinner="Loading admin-1 boundaries…")
def load_base() -> tuple[dict, list[str], dict[str, str], dict[str, str]]:
    """Sudan admin-1 polygons co-registered to the crosswalk.

    Returns the GeoJSON (feature id = GADM ``GID_1``), the ordered GID list,
    a ``GID_1 -> canonical_pcode`` map, and a ``canonical_pcode -> state name``
    map. Geometry is kept out of Streamlit's hash by returning plain dicts.
    """
    gadm = data.load_gadm_admin1()
    sudan = gadm[gadm["GID_0"] == "SDN"].copy()

    xwalk = data.load_admin1_crosswalk()
    sudan_xwalk = xwalk[xwalk["iso3"] == "SDN"][["canonical_pcode", "gadm_gid1", "acled_admin1"]]
    sudan = sudan.merge(sudan_xwalk, left_on="GID_1", right_on="gadm_gid1")
    sudan = sudan.set_index("GID_1")

    geojson = sudan[["geometry"]].__geo_interface__
    gid_order = sudan.index.tolist()
    gid_to_pcode = dict(zip(sudan.index, sudan["canonical_pcode"], strict=True))
    pcode_to_name = dict(zip(sudan["canonical_pcode"], sudan["acled_admin1"], strict=True))
    return geojson, gid_order, gid_to_pcode, pcode_to_name


# --------------------------------------------------------------------------
# Figure builders
# --------------------------------------------------------------------------
def state_choropleth(
    geojson: dict,
    gid_order: list[str],
    values: list[float | None],
    *,
    colorscale: str,
    zmax: float,
    label: str,
    hovertext: list[str],
    title: str,
) -> go.Figure:
    """A single-month Sudan admin-1 choropleth.

    ``zmax`` is fixed to the layer's full-window maximum so colour is
    comparable as the user scrubs the slider.
    """
    fig = go.Figure(
        go.Choropleth(
            geojson=geojson,
            locations=gid_order,
            z=values,
            zmin=0,
            zmax=zmax,
            colorscale=colorscale,
            marker={"line": {"color": "white", "width": 0.6}},
            colorbar={"title": label, "thickness": 12},
            text=hovertext,
            hoverinfo="text",
        )
    )
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center", "font": {"size": 15}},
        height=430,
        margin={"l": 8, "r": 8, "t": 46, "b": 8},
    )
    return fig


def no_data_map(geojson: dict, gid_order: list[str], message: str) -> go.Figure:
    """Grey 'no data' placeholder map — used for displacement before Aug 2023."""
    fig = go.Figure(
        go.Choropleth(
            geojson=geojson,
            locations=gid_order,
            z=[0] * len(gid_order),
            colorscale=[[0, "#e9e9e9"], [1, "#e9e9e9"]],
            showscale=False,
            marker={"line": {"color": "white", "width": 0.6}},
            hoverinfo="skip",
        )
    )
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=message,
        showarrow=False,
        font={"size": 13, "color": "#666"},
        bgcolor="rgba(255,255,255,0.85)",
    )
    fig.update_layout(height=430, margin={"l": 8, "r": 8, "t": 46, "b": 8})
    return fig


def heatmap_with_marker(violence: pd.DataFrame, value: str, month_idx: int) -> go.Figure:
    """The full-window violence heatmap with the scrubbed month outlined."""
    fig = viz.violence_heatmap(violence, value=value)
    fig.add_vrect(
        x0=month_idx - 0.5,
        x1=month_idx + 0.5,
        line={"color": "#1f77b4", "width": 2},
        fillcolor="rgba(31,119,180,0.10)",
        layer="above",
    )
    fig.update_layout(height=560, width=None)
    return fig


def origin_breakdown(od: pd.DataFrame, destination: str) -> go.Figure:
    """Where the IDPs currently in ``destination`` came from (DTM O-D snapshot)."""
    rows = (
        od[(od["flow_type"] == "internal") & (od["destination"] == destination)]
        .sort_values("individuals")
        .copy()
    )
    rows["is_self"] = rows["origin"] == rows["destination"]
    rows["label"] = rows.apply(
        lambda r: f"{r['origin']} (within state)" if r["is_self"] else r["origin"],
        axis=1,
    )
    colours = ["#7a3b8f" if s else "#2166ac" for s in rows["is_self"]]
    fig = go.Figure(
        go.Bar(
            x=rows["individuals"],
            y=rows["label"],
            orientation="h",
            marker={"color": colours},
            hovertemplate="%{y}<br>%{x:,} IDPs<extra></extra>",
        )
    )
    total = int(rows["individuals"].sum())
    fig.update_layout(
        title={
            "text": (
                f"Origin of IDPs now in <b>{destination}</b><br>"
                f"<sup>{total:,} present IDPs · IOM DTM O-D snapshot, as of Feb 2026</sup>"
            ),
            "font": {"size": 14},
        },
        xaxis={"title": "Present IDPs"},
        yaxis={"title": None},
        height=max(280, 34 * len(rows) + 110),
        margin={"l": 10, "r": 20, "t": 70, "b": 40},
    )
    return fig


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------
violence, displacement, od = load_layers()
geojson, gid_order, gid_to_pcode, pcode_to_name = load_base()

months = sorted(violence["period"].unique())
labels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
label_to_month = dict(zip(labels, months, strict=True))
disp_start = displacement["period"].min()

# Fixed colour ceilings so the slider scrub is visually comparable month to month.
zmax_events = int(violence["n_events"].max())
zmax_fatal = int(violence["fatalities"].max())
zmax_idp = int(displacement["idp_present"].max())


# --------------------------------------------------------------------------
# Sidebar controls
# --------------------------------------------------------------------------
st.sidebar.title("🇸🇩 Sudan war")
st.sidebar.markdown(
    "**Violence × displacement, April 2023 – May 2025.** "
    "Drag the month slider — or press **Play** — to scrub both layers together."
)
metric = st.sidebar.radio(
    "Violence metric",
    options=["n_events", "fatalities"],
    format_func=lambda v: VALUE_LABELS[v],
)
st.sidebar.caption(
    "Violence: ACLED events (Battles, Explosions/Remote violence, Violence "
    "against civilians). Displacement: IOM DTM present-IDP stock — the "
    "`(Overview)` operation begins **August 2023**, so April–July 2023 show "
    "violence only.\n\nCross-border refugee totals are a current UNHCR portal "
    "snapshot and do not move with the slider."
)

# --------------------------------------------------------------------------
# Animation state — advance the slider before the widget is instantiated
# --------------------------------------------------------------------------
if "playing" not in st.session_state:
    st.session_state.playing = False

if st.session_state.playing:
    current = st.session_state.get("sel_month", labels[0])
    idx = labels.index(current)
    if idx >= len(labels) - 1:
        st.session_state.playing = False  # reached the end — stop
    else:
        st.session_state.sel_month = labels[idx + 1]

# --------------------------------------------------------------------------
# Header + transport controls
# --------------------------------------------------------------------------
st.title("Two years of war: violence and displacement across Sudan")

ctrl_play, ctrl_slider = st.columns([1, 6])
with ctrl_play:
    if st.session_state.playing:
        if st.button("⏸ Pause", width="stretch"):
            st.session_state.playing = False
            st.rerun()
    else:
        if st.button("▶ Play", width="stretch"):
            st.session_state.playing = True
            st.rerun()
with ctrl_slider:
    sel_label = st.select_slider("Month", options=labels, key="sel_month")

month = label_to_month[sel_label]
month_idx = labels.index(sel_label)

# --------------------------------------------------------------------------
# KPI row
# --------------------------------------------------------------------------
v_month = violence[violence["period"] == month]
d_month = displacement[displacement["period"] == month]

events_now = int(v_month["n_events"].sum())
fatal_now = int(v_month["fatalities"].sum())
idp_now = int(d_month["idp_present"].sum()) if not d_month.empty else None

if month_idx > 0:
    prev_month = months[month_idx - 1]
    v_prev = violence[violence["period"] == prev_month]
    d_prev = displacement[displacement["period"] == prev_month]
    d_events = events_now - int(v_prev["n_events"].sum())
    d_fatal = fatal_now - int(v_prev["fatalities"].sum())
    d_idp = (
        idp_now - int(d_prev["idp_present"].sum())
        if idp_now is not None and not d_prev.empty
        else None
    )
else:
    d_events = d_fatal = d_idp = None

k1, k2, k3, k4 = st.columns(4)
k1.metric("Month", sel_label)
k2.metric("Violent events", f"{events_now:,}", delta=d_events)
k3.metric("Fatalities", f"{fatal_now:,}", delta=d_fatal)
if idp_now is None:
    k4.metric("IDPs present", "—", help="IOM DTM data begins August 2023")
else:
    k4.metric("IDPs present", f"{idp_now / 1e6:.2f}M", delta=d_idp)

# --------------------------------------------------------------------------
# Twin choropleths — violence | displacement, for the scrubbed month
# --------------------------------------------------------------------------
map_v, map_d = st.columns(2)

with map_v:
    v_by_pcode = v_month.set_index("canonical_pcode")[metric]
    z_v = [int(v_by_pcode.get(gid_to_pcode[g], 0)) for g in gid_order]
    hov_v = [
        f"<b>{pcode_to_name[gid_to_pcode[g]]}</b><br>{VALUE_LABELS[metric]}: {z:,}"
        for g, z in zip(gid_order, z_v, strict=True)
    ]
    fig_v = state_choropleth(
        geojson,
        gid_order,
        z_v,
        colorscale="Reds",
        zmax=zmax_events if metric == "n_events" else zmax_fatal,
        label=VALUE_LABELS[metric],
        hovertext=hov_v,
        title=f"Violence — {VALUE_LABELS[metric]}, {sel_label}",
    )
    st.plotly_chart(fig_v, width="stretch")

with map_d:
    if d_month.empty:
        fig_d = no_data_map(
            geojson,
            gid_order,
            "IOM DTM displacement data<br>begins August 2023",
        )
        fig_d.update_layout(
            title={
                "text": f"Internal displacement — {sel_label}",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 15},
            }
        )
        st.plotly_chart(fig_d, width="stretch")
    else:
        d_by_pcode = d_month.set_index("canonical_pcode")["idp_present"]
        z_d = [int(d_by_pcode.get(gid_to_pcode[g], 0)) for g in gid_order]
        hov_d = [
            f"<b>{pcode_to_name[gid_to_pcode[g]]}</b><br>IDPs present: {z:,}"
            for g, z in zip(gid_order, z_d, strict=True)
        ]
        fig_d = state_choropleth(
            geojson,
            gid_order,
            z_d,
            colorscale="Purples",
            zmax=zmax_idp,
            label="IDPs present",
            hovertext=hov_d,
            title=f"Internal displacement — IDPs present, {sel_label}",
        )
        st.plotly_chart(fig_d, width="stretch")

# --------------------------------------------------------------------------
# Context heatmap — full window, scrubbed month outlined
# --------------------------------------------------------------------------
st.subheader("Violence over the full window")
st.plotly_chart(
    heatmap_with_marker(violence, metric, month_idx),
    width="stretch",
)

# --------------------------------------------------------------------------
# Cross-border network + internal origin explorer
# --------------------------------------------------------------------------
st.subheader("Where the displaced went")
net_col, flow_col = st.columns([3, 2])

with net_col:
    st.plotly_chart(viz.crossborder_network(od), width="stretch")

with flow_col:
    dest_states = sorted(od[od["flow_type"] == "internal"]["destination"].dropna().unique())
    default_dest = "Khartoum" if "Khartoum" in dest_states else dest_states[0]
    chosen = st.selectbox(
        "Internal displacement — pick a host state",
        options=dest_states,
        index=dest_states.index(default_dest),
    )
    st.plotly_chart(origin_breakdown(od, chosen), width="stretch")

st.caption(
    "Sources: ACLED (violence), IOM DTM (internal displacement), UNHCR "
    "situation portal (cross-border refugees). Analysis window April 2023 – "
    "May 2025; the May 2025 bin is partial (ACLED snapshot ends 19 May 2025)."
)

# --------------------------------------------------------------------------
# Drive the animation — advance one month per rerun while playing
# --------------------------------------------------------------------------
if st.session_state.playing:
    time.sleep(PLAY_DELAY_S)
    st.rerun()
