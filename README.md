# Sudan war displacement mapping

> Two years into the Sudan war, how have violence and displacement co-evolved across the country and its neighbors?

![Hero figure](figures/hero.png)

## The question

The war that broke out in Sudan in April 2023 has produced one of the largest displacement crises of the decade — millions internally displaced, and millions more crossing into Chad, South Sudan, Egypt, Ethiopia, and the Central African Republic. This project maps how *violence intensity* and *displacement flows* have co-evolved geographically and over time. We are **not** attempting to causally attribute displacement to specific events or actors — the data does not support that — and we are **not** producing a humanitarian needs assessment, which has its own established methodology. The deliverable is a geographic and temporal description of the conflict's footprint that could serve as input to either of those richer studies.

## Data

| Source | Granularity | Time coverage | Access |
|--------|-------------|---------------|--------|
| [ACLED conflict events](https://acleddata.com/) | Event-level (lat/lon, date, event type, actors) | April 2023 – latest | **Registered (free for non-commercial); API key required** |
| [UNHCR Sudan situation portal](https://data.unhcr.org/en/situations/sudansituation) | Country-of-asylum aggregates + some admin-1 | April 2023 – latest | Public (some series via API, some download-only) |
| [IOM DTM Sudan](https://dtm.iom.int/sudan) | Admin-1 / locality displacement counts | April 2023 – latest | **Some files require manual download** from the DTM portal |
| [GADM 4.1 administrative boundaries](https://gadm.org/) | Admin-1 polygons for Sudan + neighbors | Current | Public |

Access date: planned 2026-05-XX (to be filled when ingestion notebook is first run). ACLED snapshots are version-stamped — pin the access date and parquet a snapshot, because ACLED revises historical records as new sourcing emerges.

## Method

The analysis runs in two co-registered layers. The **violence layer** uses ACLED event records — geocoded to lat/lon and classified by event type — aggregated to admin-1 by time window. The **displacement layer** combines IOM DTM internal-displacement counts (admin-1, Sudan) with UNHCR cross-border-flow counts (origin Sudan, destination = neighbor country) into a single origin-destination dataset. The two layers are joined on a common admin-1 grid for Sudan and its neighbors, producing temporal heatmaps, an origin-destination chord/network diagram, and the hero bivariate choropleth (violence intensity × displacement magnitude). The strongest critique of this approach is that ACLED and IOM/UNHCR are produced by very different processes — ACLED is a media-coded event database with known geographic bias toward areas with media coverage, while IOM DTM relies on field assessments whose frequency varies by access. The correlation we describe is therefore partly a correlation between two data systems' coverage footprints, not purely between violence and displacement. The methodological-decisions table below addresses this directly.

## Methodological decisions

Each major data-processing decision was made by **diagnostic first, choice second**. The table below is an at-a-glance summary; the full five-part rationale (problem / diagnostic / options / decision + rationale / sensitivity) lives inline in `notebooks/02_main.ipynb`.

| Decision | Chose | Why (anchored in diagnostic) | Sensitivity |
|----------|-------|------------------------------|-------------|
| ACLED event-type filtering (which `event_type` / `sub_event_type` count as "violence" for this analysis) | *to be filled during implementation* | *anchored in diagnostic — see notebook §3* | *to be filled* |
| Geocoding precision threshold (drop events below ACLED `geo_precision` X) | *to be filled during implementation* | *anchored in diagnostic — see notebook §3* | *to be filled* |
| Temporal aggregation (weekly vs. monthly bins for the heatmap and animation) | *to be filled during implementation* | *anchored in diagnostic — see notebook §4* | *to be filled* |
| Bivariate classification thresholds for the violence × displacement choropleth (3×3 quantile vs. fixed cutoffs) | *to be filled during implementation* | *anchored in diagnostic — see notebook §6* | *to be filled* |
| Reconciliation of IOM DTM vs. UNHCR records where both report on the same flow (e.g. Sudan → Chad) | *to be filled during implementation* | *anchored in diagnostic — see notebook §4* | *to be filled* |
| Admin-1 boundary reconciliation (GADM vs. ACLED `admin1` strings vs. IOM/UNHCR admin codes) | *to be filled during implementation* | *anchored in diagnostic — see notebook §4* | *to be filled* |

> Brand note: every choice above is an *educated* decision, not a convention. If you'd defend it differently, the diagnostic data is in the notebook — read it and tell me where I'm wrong.

## Findings

*To be filled during implementation. Each finding will be a falsifiable statement anchored in a specific number from the analysis.*

## Limitations

*To be filled during implementation. Expected categories: ACLED's media-coverage bias (events in well-covered areas are over-represented relative to remote areas), IOM DTM field-access variation (assessments are denser where access is safer), UNHCR cross-border counts lag actual flows, the chosen admin-1 grid masks within-region heterogeneity, and the analysis is descriptive — co-movement is not causation.*

## Visual style

This project uses **Plotly** because the headline deliverable is an animated Streamlit dashboard with a date slider, an interactive origin-destination chord diagram, and a drill-down bivariate map — all of which depend on hover state, click-through, and animation that Plotly handles natively. Static thumbnail-quality export of the hero bivariate map is generated alongside (via `plotly.io.write_image`) so the GitHub README and social-media share previews still get a clean static image.

## How to reproduce

```bash
git clone <url>
cd 03-sudan-displacement

# Install with the geo + interactive viz extras
pip install -e ".[viz,geo]"

# Set your ACLED credentials (required for the ingestion notebook)
export ACLED_API_KEY=...
export ACLED_EMAIL=...

# Run the main notebook
jupyter lab notebooks/02_main.ipynb

# Or launch the dashboard
streamlit run app/streamlit_dashboard.py
```

Full run time: ~X minutes (most data is cached after first run via `requests-cache`; some IOM DTM files require manual download — see `data/raw/README.md`).

## Files

- `notebooks/02_main.ipynb` — the analysis (start here)
- `notebooks/03_robustness.ipynb` — sensitivity checks for event-type filter, geocoding precision threshold, and bivariate cutoffs
- `src/sudan_displacement/data.py` — ACLED + UNHCR + IOM DTM + GADM loaders with caching
- `src/sudan_displacement/viz.py` — heatmap, chord, bivariate-choropleth helpers (Plotly)
- `src/sudan_displacement/diagnostics.py` — diagnostic helpers used in decision blocks
- `data/raw/` — fetched source files (gitignored if large); IOM DTM manual downloads documented here
- `data/processed/` — derived analytic dataset (parquet, committed)
- `figures/` — saved figures, including `hero.png` static export of the bivariate map (committed)
- `app/streamlit_dashboard.py` — animated dashboard with date slider (primary interactive deliverable)
- `tests/test_smoke.py` — minimal smoke tests

## Author

Muhanad — [LinkedIn](URL) · [Twitter](URL)
