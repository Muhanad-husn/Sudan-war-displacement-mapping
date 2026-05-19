# `data/raw/` — source file manifest & reproducibility contract

Raw source files are **gitignored** (only this README is tracked). A future
session — or a fresh clone — should be able to re-acquire every file below by
following its entry exactly: same source, same filters, same access date.

The canonical analytic inputs are the **pinned snapshots** in
`data/processed/`, not these raw files. Re-acquiring raw data is an explicit
step, never silent.

---

## ACLED — conflict events (Session 2)

| Field | Value |
|-------|-------|
| File | `acled_export_2026-05-19.csv` |
| Source | ACLED Data Export Tool — <https://acleddata.com/data-export-tool/> (login required) |
| Access date | 2026-05-19 |
| SHA256 | `721af34f61a4577a0f05223f9823fe3d720b3e61524de765e5c33f4929878efc` |
| Size | 18,394,575 bytes |
| Rows | 27,725 events |

**Why a manual download.** ACLED's OAuth2 API `/api/acled/read` endpoint is
gated behind the Research/Partner/Enterprise account tier and returns
`403 {"message":"Access denied"}` for standard registered accounts (the OAuth2
auth itself succeeds — see `src/sudan_displacement/data.py`). The Data Export
Tool is the manual fallback and is available to standard accounts.

**Re-acquisition steps.**

1. Log in to ACLED, open the Data Export Tool.
2. Filters:
   - Countries: **Sudan, Chad, South Sudan, Egypt, Ethiopia, Central African Republic**
   - Event date: from **2023-04-01** to the latest the tier allows (see embargo
     note below — roughly the access date minus 12 months).
   - Export type: **Dyadic** (default)
   - Format: **CSV**, all columns.
3. The tool saves the file as `ACLED Data_<YYYY-MM-DD>.csv`. **Rename it** to
   `acled_export_<access-date>.csv` so the loader's glob finds it
   (`load_acled_exports` in `data.py`).

**Analysis window — Apr 2023 → May 2025 (12-month tier embargo).** The account
tier imposes a rolling **12-month embargo**: the most recent ~12 months of
events are withheld from the export. An export pulled on access date 2026-05-19
therefore ends at **2025-05-19** — this is the genuine maximum available, not a
chosen cut-off. The resulting two-year window (2023-04-01 → 2025-05-19) happens
to align with the project's "two years into the Sudan war" framing
(`CLAUDE.md`). The pinned snapshot is the canonical input and is not silently
re-fetched. **Limitation:** the analysis cannot describe violence/displacement
after May 2025; this must be stated in the README limitations (Session 11).

Pinned snapshot: `data/processed/acled_snapshot_2026-05-19.parquet`.

---

## UNHCR — cross-border displacement (Session 3)

UNHCR data is fetched **live, no key required**, and HTTP-cached under `.cache/`
(`requests-cache`, 30-day expiry). Two complementary endpoints:

| | Refugee Statistics API | Operational Data Portal |
|--|------------------------|-------------------------|
| Host | `api.unhcr.org/population/v1/population/` | `data.unhcr.org/population/` |
| Granularity | **Annual**, per country of asylum | Situation-wide **daily/weekly** time series + per-country **snapshot** |
| Loader | `fetch_unhcr_statistics()` | `fetch_unhcr_situation_timeseries()`, `fetch_unhcr_situation_countries()` |
| Window | 2023–2025 (annual) | 2023-04-30 → access date |

**Re-acquisition.** No download — call the loaders in `data.py`. They pin
`coo=SDN` (origin Sudan) and the portal `situation_view_id=63` ("Sudan
situation"). Portal population groups: `5550` newly-arrived refugees, `5551`
returnees, `5552` IDPs in Sudan, `5583` self-relocated. To force-refresh the
cache, clear `.cache/http_cache.sqlite`.

**Caveats (for the S6 reconciliation, Decision 5).**

- The two UNHCR sources *disagree*: e.g. Egypt shows ~31k registered refugees
  in the Statistics API vs ~1.5M Sudanese arrivals in the portal snapshot
  (government estimate vs UNHCR registration). This gap is itself a finding.
- The portal per-country snapshot reports each destination **as of a different
  date** (e.g. Egypt frozen at 2025-01-31, Chad current) — `as_of_date` is kept
  as a column; do not treat the snapshot as a single-date cross-section.
- The Statistics API returns no Sudan→CAR refugee rows; CAR cross-border
  figures come only from the portal snapshot.

## IOM DTM — internal displacement (Session 3)

IOM's Displacement Tracking Matrix exposes a public v3 API for non-sensitive
IDP figures at country / admin-1 / admin-2 level. It needs a **free**
subscription key — there is no anonymous access and no bulk file download for
the admin-1 series.

| Field | Value |
|-------|-------|
| Endpoint | `https://dtmapi.iom.int/v3/displacement/admin1` |
| Auth | `Ocp-Apim-Subscription-Key` header (free key) |
| Filters | `CountryName=Sudan`, `FromReportingDate=2023-04-01`, `ToReportingDate=<access date>` |
| Loader | `fetch_dtm_admin1()` / `snapshot_dtm()` |
| Pinned snapshot | `data/processed/dtm_admin1_snapshot_2026-05-19.parquet` |

**Pinned snapshot (access date 2026-05-19).** 9,043 rows × 17 columns, 18
Sudan admin-1 regions, 85 reporting dates / 46 assessment rounds, IDP figures
spanning **2023-04-28 → 2026-02-28**. Note this extends ~9 months past the
ACLED window (D2, ends 2025-05-19) — the displacement layer is clipped to the
common window for co-registered figures (S6).
SHA256 `f9f7cad909173334aced7681b2da7dee686ee64ae4442be445d97d0d3a2edc7f`.

**Re-acquisition steps.**

1. Register at the DTM API portal: <https://dtm-apim-portal.iom.int/>.
2. Subscribe to the DTM API product; copy the subscription key.
3. Add it to `secrets.toml` (one level above the project root) as:
   ```toml
   [dtm]
   subscription_key = "..."
   ```
   (or export it as the `DTM_SUBSCRIPTION_KEY` environment variable).
4. Call `snapshot_dtm()` in `data.py` to rewrite the pinned snapshot.

**Gotcha — Azure WAF blocks the default User-Agent.** The DTM API sits behind
a Microsoft Azure Application Gateway that returns an HTML `403 Forbidden` to
the default `python-requests` User-Agent *before* the request reaches the API
key check. `data.py` sends a browser-style `User-Agent` on DTM calls to get
through — do not remove it.

## GADM 4.1 — admin-1 boundaries (Session 3)

Admin-1 (state/province) polygons for Sudan + 5 neighbours, auto-downloaded as
per-country zipped GeoJSON to `data/raw/gadm/` by `download_gadm_admin1()`.
Source: UC Davis GADM mirror, `https://geodata.ucdavis.edu/gadm/gadm4.1/json/`.
Access date: **2026-05-19**. Combined: 106 admin-1 polygons, CRS EPSG:4326.

| File | ISO3 | Admin-1 count | Size (bytes) | SHA256 |
|------|------|---------------|--------------|--------|
| `gadm41_SDN_1.json.zip` | SDN | 18 | 37,346 | `30445d474623cb1826f4ccd461265031bd71d47d0ee9d5d87484b0f3fd2b76bc` |
| `gadm41_TCD_1.json.zip` | TCD | 23 | 25,699 | `2809b408e9967665cc91b91a6b739e98525b9875769e365157a6affe29cb30d5` |
| `gadm41_SSD_1.json.zip` | SSD | 10 | 19,279 | `09087f8536555dddb27e91f945fa8da82d937abf64482f565718be9d2f8341db` |
| `gadm41_EGY_1.json.zip` | EGY | 27 | 37,103 | `ed2bc5682ddccd23d09eecf0638bd523a6fe54fb7136299a8dec2abd09eabf69` |
| `gadm41_ETH_1.json.zip` | ETH | 11 | 49,690 | `e6310c7c79c748eca766f8950e19b7a8c65a68909dfa284500eed8ac039ff3c8` |
| `gadm41_CAF_1.json.zip` | CAF | 17 | 53,989 | `2c1e6f3f18bd68977de018ee98f825dc07ea33d9c8f3df9b4cddb72dbc3a6397` |

**Re-acquisition.** Call `download_gadm_admin1()` (or `load_gadm_admin1()`,
which downloads then reads). To re-download, pass `force=True`.

**Note for S4 crosswalk.** GADM's `COUNTRY` column has no spaces
(`SouthSudan`, `CentralAfricanRepublic`) and will not join cleanly to ACLED's
`country` strings — join on the ISO3 code (`GID_0`) instead.
