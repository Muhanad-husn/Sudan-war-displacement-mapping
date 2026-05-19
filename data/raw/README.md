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
   - Event date: **2023-04-01 → 2025-05-19**
   - Export type: **Dyadic** (default)
   - Format: **CSV**, all columns.
3. The tool saves the file as `ACLED Data_<YYYY-MM-DD>.csv`. **Rename it** to
   `acled_export_<access-date>.csv` so the loader's glob finds it
   (`load_acled_exports` in `data.py`).

**Analysis window — fixed two-year window (decision, 2026-05-19).** The export
covers 2023-04-01 → 2025-05-19. The Sudan war began April 2023; this is a clean
two-year window matching the project's "two years into the Sudan war" framing
(`CLAUDE.md`). The window is fixed, not "April 2023 → latest" — the pinned
snapshot is the canonical input and is not silently re-fetched.

Pinned snapshot: `data/processed/acled_snapshot_2026-05-19.parquet`.

---

## UNHCR / IOM DTM / GADM

_Added in Session 3._
