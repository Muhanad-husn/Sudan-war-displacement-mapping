# Sudan war displacement mapping — analytic report

*Two years into the Sudan war, how have violence and displacement co-evolved across the country and its neighbours?*

**Author:** Muhanad &nbsp;·&nbsp; **Window analysed:** 1 April 2023 – 19 May 2025 &nbsp;·&nbsp; **Snapshot date:** 19 May 2026
**Repository:** [github.com/Muhanad-husn/Sudan-war-displacement-mapping](https://github.com/Muhanad-husn/Sudan-war-displacement-mapping)

---

## Executive summary

Across Sudan's 18 admin-1 states, the rank of cumulative violent-event intensity (ACLED) and the rank of peak internal-displacement stock (IOM DTM) are statistically independent — Spearman ρ = **−0.055**. The places where Sudan's war was fought hardest are, with one regional exception, not the places hosting its displaced population. This is the project's headline finding, and it survives every robustness check the analysis throws at it: re-running under a narrow event-type filter, a broad one, a strict geocoding cut-off, weekly time bins, and fixed-cutoff bivariate classification, the per-state ranking holds at Spearman ρ ≥ 0.96 in every case. The map of Sudan's war is not the same as the map of Sudan's displacement.

Four numbers anchor the picture. Khartoum recorded **6,080** violent events — 3.6× the next-highest state — but carries the *lowest* peak IDP-present stock of any Sudan state at 151k; the capital produced displacement rather than hosted it. North Darfur recorded **11,793** fatalities, the most of any state, on a quarter of Khartoum's event count — the signature of mass-atrocity violence rather than block-by-block fighting. The internal-displacement stock rose from **7.1M** (Aug 2023) to a peak of **11.6M** (Jan 2025). And UNHCR records **3.6M+** Sudanese across seven asylum countries, led by Egypt (~1.5M), Chad (0.93M) and Libya (0.56M).

The project is a Python-based, two-layer descriptive analysis with a Plotly-powered Streamlit dashboard, pinned data snapshots, and a robustness notebook that re-runs the analysis under the rejected alternative for each major decision. Code, data and figures are reproducible offline from the committed snapshots.

---

## 1. The question, and what this project is not

In April 2023, fighting between the Sudanese Armed Forces and the Rapid Support Forces broke out in Khartoum and spread across the country. It became one of the largest displacement crises of the decade — and one of the least-covered. This project builds a **descriptive, geographic-temporal** picture of how violence and displacement co-evolved across Sudan's 18 states (and its five neighbours, as refugee destinations) from April 2023 onward.

It is cartographic by design: it describes *where* and *when*. It does not attempt to causally attribute displacement to specific events or actors — the data does not support that — and it is not a humanitarian needs assessment, which has its own established methodology. Each of those is a separate study; this analysis is the geographic and temporal substrate either could build on.

## 2. Data — three sources, two layers, one pinned snapshot

The analysis combines three datasets at admin-1 resolution, pinned to a single access date.

| Source | Role | Granularity | Window | Caveat |
|---|---|---|---|---|
| [ACLED](https://acleddata.com/) | Violence layer | Event-level (date, lat/lon, type) | Apr 2023 – May 2025 | Media-coded — well-covered areas over-represented |
| [IOM DTM](https://dtm.iom.int/sudan) | Internal-displacement layer | Admin-1 IDP stock | Aug 2023 – Feb 2026 | Field-assessed; three overlapping operations (D7) |
| [UNHCR](https://data.unhcr.org/en/situations/sudansituation) | Cross-border-displacement layer | Destination country | 2023 – 2026 | Two sources disagree by ~50× (D5) |
| GADM 4.1 | Polygon basemap | Admin-1 polygons | Current | Reconciled by hand to ACLED/DTM names (D6) |

**Access date pinned to 2026-05-19**, because ACLED revises historical records as new sourcing emerges. The canonical analytic input is `data/processed/acled_snapshot_2026-05-19.parquet` — 27,725 events across six countries, of which 16,569 are inside Sudan. The notebook reads the snapshot, never the live API; the same discipline holds for IOM DTM. UNHCR is pulled through an HTTP cache (small, key-free) and treated as a per-country snapshot rather than a tidy time series.

The window — April 2023 through 19 May 2025 — is the genuine maximum the account tier can return, not a chosen cut-off. ACLED's Research tier withholds the most recent ~12 months of events, so a snapshot taken on 2026-05-19 stops there. It happens to align with the "two years into the war" framing.

## 3. Method — two layers, six decisions, one bivariate map

The analysis runs in two co-registered layers joined on a common admin-1 grid. The **violence layer** is ACLED event records, filtered to three kinetic event types, aggregated to admin-1 by month. The **displacement layer** combines IOM DTM internal-IDP stocks (admin-1, Sudan) with UNHCR cross-border counts (origin Sudan, destination = neighbour country), kept as two complementary layers and never summed. The two layers feed three figures: a temporal heatmap of violence (events and fatalities), an origin-destination network of refugee flows, and the bivariate choropleth that crosses both onto a single polygon.

The discipline I imposed on this project is what I'd want a recruiter to see most clearly: **every meaningful data-processing decision was made diagnostic-first, choice-second**. Each of the six load-bearing decisions below was structured in five parts — *problem, diagnostic, options, decision and rationale, sensitivity* — and documented inline in `02_main.ipynb`. The table below is the at-a-glance summary; the full diagnostic for each one lives in the notebook.

| # | Decision | Chose | Why (diagnostic-anchored) | Sensitivity (ρ vs chosen) |
|---|---|---|---|---|
| 6 | Admin-1 reconciliation | Normalisation + OCHA pcode overrides | Exact-string match 4/18 in Sudan; normalised 17/18; pcodes resolve the last gaps | Sudan reconciles 18/18 — *exact* |
| 1 | Event-type filter | Battles + Explosions/Remote + VAC (3 kinetic) | These carry **99.9%** of fatalities (44,709 of 44,715) | narrow / broad: ρ = 0.98 / 0.96 |
| 2 | Geo-precision threshold | Keep all tiers | `admin1` populated at 100% of events at every tier | drop ≥ 3: ρ = 1.000 (0 rank changes) |
| 3 | Temporal bin | Monthly | Weekly buys no autocorrelation; leaves 35–83% bins empty in quiet states | weekly: ρ = 1.000 (sums bin-invariant) |
| 7 | DTM operation | `Armed Clashes in Sudan (Overview)` | Only series spanning the analytic window; the three operations report incompatible levels (Dec 2023: 5.9M vs 9.1M) | Geography invariant; level depends on choice |
| 5 | DTM × UNHCR reconciliation | Two complementary layers, never summed | Zero shared origin-destination pairs — they measure disjoint flows | The real disagreement is *within* UNHCR (Egypt: 31k vs 1.5M) |
| 4 | Bivariate cutoffs | 3×3 quantile bins | Violence skewed 3.6× by Khartoum; fixed thirds fill only 4 of 9 classes; quantile fills all 9 | finding ρ = −0.055 is rank-based, invariant to re-binning |

Two of these decisions earn extra attention because their diagnostics overturned the project's original framing, and I think that matters for how the work should be read.

**Decision 5 — DTM ↔ UNHCR reconciliation.** The brief anticipated a head-to-head reconciliation: "where IOM DTM and UNHCR both report the same Sudan → neighbour flow, choose one as primary." The diagnostic killed that framing. DTM and UNHCR share **zero** origin-destination pairs — DTM counts IDPs *inside* Sudan, UNHCR counts refugees who *left* it; summing them would be a category error. The genuine disagreement is *within* UNHCR. Its Statistics API reports ~**31,000** registered refugees in Egypt; its situation portal snapshot reports ~**1,500,000**. That is a 48× gap, and a 47.8× ratio per destination is exactly what the diagnostic table showed. Both numbers are real. They measure different things — legal registration versus government-informed total-presence estimate — and the project reports the gap as a finding rather than averaging it away. The headline cross-border picture uses the portal snapshot because it is the methodological twin of DTM's "present-IDP stock": a point-in-time presence count, not a legal-status count.

**Decision 1 — event-type filter.** ACLED's six `event_type` values are not all violence. Two of them — `Strategic developments` (negotiated agreements, non-violent territory transfers) and `Demonstrations` (protests, riots) — together carry **34 deaths across Sudan's full Apr 2023 – May 2025 window**, against 44,709 for the three kinetic types I kept (Battles, Explosions/Remote violence, Violence against civilians). Including the non-kinetic types would have lit up Port Sudan, the capital-in-exile and the site of ceasefire-adjacent diplomatic activity, as if it were a combat front. The narrow alternative — Battles plus Violence against civilians only — would have done the opposite, excluding the 3,930 air/drone strikes and shelling events in a war where remote violence is central. I kept the three kinetic types and verified in `03_robustness.ipynb` that both alternatives leave the per-state ranking near-identical.

The full diagnostic for every decision lives inline in `02_main.ipynb`; the brand note in the README is the right one — these are *educated* decisions, not conventions, and the data behind each is open for argument.

## 4. The violence layer — where the war was fought

The pinned violence layer is **468 rows = 18 states × 26 months**, **12,687 events, 44,709 fatalities**. The two heatmaps — events and fatalities — tell different halves of the story.

By **event count**, the war's centre of gravity is Khartoum: 6,080 events, an unbroken hot band from the April 2023 outbreak through early 2024, with Al Jazirah (1,571 events) lighting up sharply from December 2023 as fighting pushed south-east into the Gezira agricultural heartland. The eastern states (Kassala, Red Sea, Gedaref) stay near-cold throughout — the same quiet states that anchored the temporal-aggregation diagnostic.

![Violent events by Sudan admin-1 state, monthly heatmap](https://github.com/Muhanad-husn/Sudan-war-displacement-mapping/raw/main/figures/violence_events_heatmap.png)

*Monthly event count by state, states ordered by window total. Khartoum's August–November 2023 peak is the single darkest band on the figure (>450 events/month); Al Jazirah's late-2023 ignition is the secondary structure. Source: ACLED pinned snapshot, 2026-05-19.*

By **fatalities**, the geography shifts west and the temporal pattern reorganises. North Darfur carries the most deaths of any state (11,793) on a quarter of Khartoum's event count, with its heaviest months falling in **late 2024 and early 2025** rather than the war's opening year — a different war from the one Khartoum fought. West Darfur is the starkest single divergence: 303 events but **5,142 fatalities**, concentrated almost entirely in a **November 2023 spike** that reads on the heatmap as the highest single cell on the fatality axis. Al Jazirah shows a similar sharp pulse in October 2024. These are the signatures of concentrated mass-atrocity violence rather than sustained block-by-block fighting, and the fatality heatmap makes them visible in a way the event-count map structurally cannot.

![Fatalities by Sudan admin-1 state, monthly heatmap](https://github.com/Muhanad-husn/Sudan-war-displacement-mapping/raw/main/figures/violence_fatalities_heatmap.png)

*Monthly fatalities by state, states ordered by window total. Note the discrete high-fatality cells — West Darfur Nov 2023, Al Jazirah Oct 2024 — distinct from Khartoum's sustained band on the event-count map. Source: ACLED pinned snapshot, 2026-05-19.*

The state ranking by event count over the full window:

| Rank | State | Events | Fatalities |
|---|---|---|---|
| 1 | Khartoum | 6,080 | 11,264 |
| 2 | North Darfur | 1,582 | **11,793** |
| 3 | Al Jazirah | 1,571 | 4,983 |
| 4 | North Kordofan | 564 | 2,312 |
| 5 | South Darfur | 543 | 2,595 |
| 6 | South Kordofan | 495 | 1,992 |
| 7 | Sennar | 309 | 1,223 |
| 8 | West Darfur | 303 | **5,142** |
| … | … | … | … |
| 18 | Kassala | 32 | 8 |

Two divergences are worth flagging for the reader. North Darfur, which records fewer events than Al Jazirah, carries roughly 2.4× the deaths — the El Fasher siege and the wider Darfur atrocity pattern are the obvious explanation, though this analysis stops at the geographic description and does not attribute. And the fatality-to-event ratio in West Darfur (17.0 deaths per event) against Khartoum (1.85) reads as a methodological caution as much as an empirical finding: ACLED's media-coding floor will be very different in El Geneina than in the capital, and any single high-fatality event has outsized weight in the Darfur ratio.

## 5. The displacement layer — where it pushed people

The internal-displacement layer covers **396 rows = 18 states × 22 months** (Aug 2023 – May 2025). The national IDP-present stock rose from **7,071,674** in August 2023 to a peak of **11,585,384** in January 2025, easing to **10,136,005** by May 2025 as early returns began. Eight of the 22 months in this series carry no DTM assessment round and inherit the prior stock by forward-fill — because IDP-present is a *stock*, not a flow, missing months persist rather than zeroing out (the opposite discipline from the violence layer, where a missing month genuinely means zero recorded events).

By May 2025 the geography of internal displacement is dominated by the Darfur states and the refuge corridor north and east of the fighting:

| Rank | State (host) | Peak IDP-present (May 2025) |
|---|---|---|
| 1 | South Darfur | 1,842,508 |
| 2 | North Darfur | 1,793,938 |
| 3 | Central Darfur | 949,647 |
| 4 | East Darfur | 802,844 |
| 5 | River Nile | 619,654 |
| 6 | White Nile | 563,879 |
| 7 | Gedaref | 533,899 |
| 8 | Northern | 532,656 |
| … | … | … |
| 18 | Sennar | 99,119 |
| — | Khartoum | 150,987 *(15th)* |

The cross-border picture — Sudan-as-origin, neighbour countries as destination — is dominated by Egypt under the UNHCR portal snapshot. With a single origin, a chord diagram degenerates into a fan, so the honest form is a node-link network: Sudan at the centre, asylum countries placed on a roughly geographic bearing, edge width and node size scaled to refugee counts.

![Sudanese refugee flows to neighbouring countries — UNHCR situation portal snapshot](https://github.com/Muhanad-husn/Sudan-war-displacement-mapping/raw/main/figures/crossborder_network.png)

*Cross-border network, 3.6M+ Sudanese refugees across 7 destinations. Edge thickness and node size scale to recorded individuals. Source: UNHCR situation portal snapshot, per-country `as_of_date` ranging Jan 2025 – May 2026.*

| Rank | Destination | Individuals (portal) | As-of date |
|---|---|---|---|
| 1 | Egypt | 1,500,000 | 2025-01-31 |
| 2 | Chad | 926,963 | 2026-05-04 |
| 3 | Libya | 559,920 | 2026-04-20 |
| 4 | South Sudan | 448,219 | 2026-05-04 |
| 5 | Uganda | 89,924 | 2026-05-04 |
| 6 | Ethiopia | 55,826 | 2025-09-08 |
| 7 | Central African Republic | 36,342 | 2026-04-20 |

The flow geography tracks Sudan's land borders and the routes out of the worst-hit regions. Chad receives Darfuris fleeing the western front; South Sudan absorbs returns and new movement across the southern border; Egypt's 1.5M reflects both the Khartoum exodus and the onward movement of those with the means to reach it. Under the UNHCR Statistics API the ranking inverts — Egypt drops to last at ~31k registered refugees, a 48× gap that the analysis surfaces rather than reconciles. This is exactly the kind of measurement-system disagreement that, in my experience, separates honest descriptive work from descriptive work that quietly picks a number.

## 6. The hero finding — geography of violence ≠ geography of displacement

Cross the two layers onto a single polygon and the project's central finding falls out of the data. Across Sudan's 18 states the event-count rank and the peak-IDP-stock rank are **statistically independent**: Spearman ρ = **−0.055**. The 3×3 quantile bivariate grid fills with precisely **two states in every one of its nine cells** — exactly what independence looks like on a 6/6/6 binning.

![Sudan: violence × displacement, bivariate choropleth (April 2023 – May 2025)](https://github.com/Muhanad-husn/Sudan-war-displacement-mapping/raw/main/figures/hero.png)

*Bivariate choropleth, ColorBrewer PuOr 3×3 palette (color-blind-safe). Orange = high violence, purple = high displacement, dark = both, near-white = neither. From `figures/hero.png`.*

Three regions carry the entire structural story.

**Darfur — the one exception.** North and South Darfur sit alone in the high-violence / high-displacement corner. North Darfur pairs the second-highest event count (1,582) with a 1.79M peak IDP stock; South Darfur carries the largest IDP stock of any state (1.84M). Darfur is the only place where intense violence and mass internal displacement geographically coincide on this grid.

**Khartoum — violence epicentre, displacement source.** The capital is the war's event epicentre (6,080 events, 3.6× the next-highest) yet carries the *lowest* peak IDP-present stock of any Sudan state at 151k. This is not a contradiction; it is a definitional point about what the IDP series measures. The DTM layer counts IDPs *sheltering in* a state, not those *originating* from it. Khartoum did not host the displaced — it produced them, and it emptied out.

**River Nile and Gedaref — refuge states.** Two near-quiet states (48–92 events over the entire 26-month window) each absorbed over 1M IDPs at peak. These are the refuge corridors north and east of the fighting — the geographic destination of internal displacement, not its origin.

What makes the bivariate form load-bearing here is precisely that a univariate violence map and a univariate displacement map would each look "correct" and would quietly invite the reader to assume they describe the same geography. Crossed onto one polygon, they visibly do not, and *that gap is the story*. The people displaced by this war are, in large part, not where the war is.

To be clear about what this does not mean: the decoupling is not a claim that violence and displacement are causally unrelated. It is a claim that the *geography* of present-IDP stock and the *geography* of recorded violent events do not overlap state-for-state at admin-1 resolution. People who flee Khartoum show up as IDPs in River Nile; people who flee Darfur show up as IDPs in adjacent Darfur states or as refugees in Chad. The ρ = −0.055 is descriptive of where the two systems' stocks sit, not a causal independence result.

## 7. Robustness — what survives the alternative

The robustness notebook re-runs the analysis under the alternative that the main notebook rejected for each of the four classification decisions, then asks the only question that matters: does the headline geographic finding change?

| Check | Decision | Alternative | Effect on counts | Effect on finding |
|---|---|---|---|---|
| 1 | Event-type filter | narrow (Battles + VAC) / broad (all 6 types) | −31.0% / +30.6% events | ρ = 0.98 / 0.96 — top-5 states unchanged |
| 2 | Geo-precision | drop `geo_precision ≥ 3` | −1.19% events (151) | ρ = 1.000 — zero rank changes |
| 3 | Temporal bin | weekly instead of monthly | empty cells 16.0% → 41.7% | ρ = 1.000 (sums bin-invariant) |
| 4 | Bivariate cutoffs | fixed equal-width thirds | 9/9 → 4/9 classes filled | ρ = −0.055 unchanged (rank-based) |

The pattern is one-directional. Every consequential choice was made for legibility or coverage — the violence skew that forces quantile binning, the assessment-cadence irregularity that forces forward-fill, the media-coding bias that forces honest limitations — and none of them is load-bearing for the conclusion that violence intensity and displacement magnitude rank independently across Sudan's 18 states. The headline ρ = −0.055 is computed on raw per-state values and is invariant to any monotone re-binning. That is the strongest statement the data can support, and it is what the project commits to.

## 8. Limitations — what I would not claim from this

Three things the analysis genuinely cannot do, and one bias to keep visible.

**Coverage stops at 19 May 2025.** The ACLED account tier withholds the most recent ~12 months of events. Nothing after that date is in the analysis, and the final monthly bin (May 2025) is partial — it runs only to the 19th. The Streamlit dashboard exposes this explicitly.

**The displacement layer starts four months late.** The IOM DTM `(Overview)` series begins August 2023, so the internal-displacement picture misses the war's opening months (April–July 2023), which the violence layer *does* cover. Co-registered figures (the dashboard, the bivariate hero map) handle the offset explicitly rather than papering over it.

**Two data systems, two coverage footprints.** ACLED is media-coded, so events in well-covered areas are over-represented relative to remote ones. IOM DTM relies on field assessments whose frequency varies with access. Any co-movement between the two layers is partly a correlation between two coverage footprints, not purely between violence and displacement. The decoupling finding (ρ = −0.055) is, if anything, conservative against this bias — the coverage footprints would tend to *correlate* the two layers (more access in the same places), not decouple them.

**The admin-1 grid masks within-region heterogeneity, and the analysis is descriptive.** Co-movement is not causation. The project does not attribute displacement to specific events or actors, and it does not forecast.

A final note on the neighbour layer: Egypt's 27 governorates and four of Ethiopia's ACLED regions could not be matched to GADM 4.1 polygons (different romanisation conventions; GADM predates Ethiopia's 2020–2023 regional reorganisation). Neighbours enter the analysis at country level — as refugee destinations — only. Sub-national detail for neighbours is a deliverable a future iteration of this project, with a hand-built crosswalk and a more recent GADM release, could pick up.

## 9. Engineering & reproducibility

The project ships as a Python package (`src/sudan_displacement/`) with three modules: `data.py` (ACLED, IOM DTM, UNHCR and GADM loaders, plus the analytic-layer builders), `viz.py` (heatmap, network and bivariate-choropleth helpers, all Plotly), and `diagnostics.py` (the comparison helpers each decision-block diagnostic uses). The main analysis notebook `notebooks/02_main.ipynb` reads top-to-bottom as a short paper, with each load-bearing decision documented in five parts inline. The robustness notebook `03_robustness.ipynb` quantifies every Sensitivity claim. A Streamlit dashboard (`app/streamlit_dashboard.py`) renders the animated date-slider view with hover state and click-through.

Reproducibility is offline-first by design. The committed parquet snapshots in `data/processed/` (ACLED, IOM DTM, the derived analytic layers) make the main notebook reproducible top-to-bottom without credentials or network access. `02_main.ipynb` runs in well under a minute on a laptop. Re-acquiring the raw sources from scratch is a separate, documented step: ACLED needs a registered account (its API is tier-gated, so the snapshot was built from a manual Data Export Tool download), and IOM DTM needs a free API subscription key. Both are documented with file names and SHA256 checksums in `data/raw/README.md`; credentials go in a gitignored `secrets.toml`. The 96.5% Jupyter / 3.5% Python language split reflects this design — the package is small and the notebooks carry the analytical narrative.

```bash
git clone https://github.com/Muhanad-husn/Sudan-war-displacement-mapping
cd Sudan-war-displacement-mapping
pip install -e ".[viz,geo]"
jupyter lab notebooks/02_main.ipynb        # the analysis
streamlit run app/streamlit_dashboard.py   # the dashboard
```

## 10. Where this leads

The project is what I'd call a *cartographic substrate*. It is descriptive on purpose, and the strongest claim it makes — that violence-intensity rank and displacement-magnitude rank are independent across Sudan's 18 states — is exactly the kind of statement a downstream causal or humanitarian study would want as its starting point. A natural next step would be to lift the unit of analysis below admin-1 (the geography is doing real work at admin-2 in Darfur and Kordofan, where state borders obscure within-state heterogeneity), and to bring in displacement-flow data with a directional origin field rather than a present-stock destination one — DTM does publish movement-tracking matrices that would support an arrival-flow rather than IDP-stock view. The deliverable as it stands, though, is the thing it set out to be: an honest, decision-disciplined map of two co-evolving data systems, with the disagreements between them surfaced rather than averaged away.

---

*Report compiled from the public repository on 19 May 2026. All numbers in the report are read directly from `notebooks/02_main.ipynb` and `notebooks/03_robustness.ipynb`; no claim in the report extends beyond what those notebooks show.*
