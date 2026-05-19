"""Data loading utilities with HTTP caching.

All API calls go through a memoized session so notebooks re-run fast.
Paths are resolved relative to the project root (the folder containing pyproject.toml).

Source-specific loaders (UNHCR, IOM DTM, GADM) are added in later sessions;
this module currently provides the shared cache + path scaffolding and the
ACLED loader (Session 2).
"""

from __future__ import annotations

import json
import re
import tomllib
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import requests_cache

# This file lives at src/sudan_displacement/data.py
# parents[0] = src/sudan_displacement/
# parents[1] = src/
# parents[2] = project root
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXTERNAL_DIR = DATA_DIR / "external"
FIGURES_DIR = ROOT / "figures"
CACHE_DIR = ROOT / ".cache"

for _d in (RAW_DIR, PROCESSED_DIR, EXTERNAL_DIR, FIGURES_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Shared HTTP cache for the project (gitignored).
# Expires after 30 days by default — override per-call if needed.
session = requests_cache.CachedSession(
    cache_name=str(CACHE_DIR / "http_cache"),
    backend="sqlite",
    expire_after=60 * 60 * 24 * 30,
    allowable_methods=("GET", "HEAD"),
)


def download_file(url: str, dest: str | Path, force: bool = False) -> Path:
    """Download a file to ``dest``, using the cached session.

    Parameters
    ----------
    url
        Source URL.
    dest
        Destination path. Relative paths are resolved against ``RAW_DIR``.
    force
        If True, re-download even if the local file exists.

    Returns
    -------
    Path
        Absolute path to the downloaded file.
    """
    dest = Path(dest)
    if not dest.is_absolute():
        dest = RAW_DIR / dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        return dest

    resp = session.get(url, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return dest


def read_processed(name: str) -> pd.DataFrame:
    """Read a parquet from ``data/processed/<name>.parquet``."""
    return pd.read_parquet(PROCESSED_DIR / f"{name}.parquet")


def write_processed(df: pd.DataFrame, name: str) -> Path:
    """Write a DataFrame to ``data/processed/<name>.parquet``."""
    path = PROCESSED_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False)
    return path


# ===========================================================================
# ACLED ingestion (Session 2)
# ===========================================================================
#
# ACLED moved to OAuth2 password-grant auth. The two endpoints and the fixed
# public client_id are protocol facts (see IMPLEMENTATION_PLAN.md "ACLED
# protocol facts"). Credentials live in the [acled] block of secrets.toml,
# which sits one level above the project root and is never committed.

ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_READ_URL = "https://acleddata.com/api/acled/read"
# ACLED's OAuth2 server rejects the password/refresh grant unless this fixed
# public client_id is in the POST body (hint: "Check the 'client_id' parameter").
ACLED_CLIENT_ID = "acled"

# secrets.toml is shared across the portfolio monorepo — one level up from root.
SECRETS_PATH = ROOT.parent / "secrets.toml"
# Token cache: gitignored (see .gitignore "tokens.json"). Never committed.
TOKENS_PATH = ROOT / "tokens.json"

# Refresh the access token early if it expires within this window.
_PROACTIVE_REFRESH = timedelta(minutes=10)

# The analytic geography: Sudan + the five contiguous neighbours that receive
# its cross-border flows. Names match ACLED's `country` field exactly.
ACLED_COUNTRIES = (
    "Sudan",
    "Chad",
    "South Sudan",
    "Egypt",
    "Ethiopia",
    "Central African Republic",
)

# War onset; the analysis window opens here and runs to the access date.
ACLED_START_DATE = "2023-04-01"


def _read_acled_credentials() -> tuple[str, str]:
    """Return ``(username, password)`` from the [acled] block of secrets.toml.

    Credentials are read lazily (only when a token must be minted) and never
    logged. Raises a clear error if the block or its keys are missing.
    """
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(
            f"secrets.toml not found at {SECRETS_PATH}. It must contain an "
            "[acled] block with `username` and `password`."
        )
    block = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8")).get("acled", {})
    try:
        return block["username"], block["password"]
    except KeyError as exc:
        raise KeyError(
            f"secrets.toml [acled] block is missing key {exc}. "
            "Expected both `username` and `password`."
        ) from exc


def _normalise_tokens(payload: dict, *, previous: dict | None = None) -> dict:
    """Convert a raw OAuth2 token response to the on-disk cache shape.

    On a refresh response the server may omit ``refresh_token``; in that case
    the previous one is carried forward.
    """
    now = datetime.now(UTC)
    refresh_token = payload.get("refresh_token") or (previous or {}).get("refresh_token")
    if not payload.get("access_token") or not refresh_token:
        raise RuntimeError("ACLED token response missing access_token / refresh_token.")
    access_ttl = int(payload.get("expires_in", 0))
    # ACLED omits a refresh-token lifetime; ~14 days is the documented default.
    refresh_ttl = int(payload.get("refresh_expires_in", 14 * 24 * 3600))
    return {
        "access_token": payload["access_token"],
        "refresh_token": refresh_token,
        "access_expires_at": (now + timedelta(seconds=access_ttl)).isoformat(),
        "refresh_expires_at": (now + timedelta(seconds=refresh_ttl)).isoformat(),
    }


def _post_acled_token(data: dict) -> dict:
    """POST a grant request to the ACLED token endpoint (uncached)."""
    data["client_id"] = ACLED_CLIENT_ID  # mandatory on every grant type
    resp = requests.post(ACLED_TOKEN_URL, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def acled_access_token(force_mint: bool = False) -> str:
    """Return a valid ACLED access token, minting or refreshing as needed.

    Token lifecycle (cached to the gitignored ``tokens.json``):

    - no cache / refresh token stale  -> password-grant mint
    - access token near expiry        -> refresh-grant refresh
    - otherwise                       -> reuse the cached access token

    The access token (~24 h) and refresh token (~14 d) are never logged.
    """
    cache: dict | None = None
    if TOKENS_PATH.exists() and not force_mint:
        try:
            cache = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = None

    now = datetime.now(UTC)
    tokens: dict
    if cache is None or datetime.fromisoformat(cache["refresh_expires_at"]) <= now:
        # No usable cache (or refresh token dead) -> full password-grant mint.
        username, password = _read_acled_credentials()
        tokens = _normalise_tokens(
            _post_acled_token(
                {"grant_type": "password", "username": username, "password": password}
            )
        )
    elif datetime.fromisoformat(cache["access_expires_at"]) - now <= _PROACTIVE_REFRESH:
        # Access token near expiry but refresh token still valid -> refresh.
        tokens = _normalise_tokens(
            _post_acled_token(
                {"grant_type": "refresh_token", "refresh_token": cache["refresh_token"]}
            ),
            previous=cache,
        )
    else:
        return str(cache["access_token"])

    TOKENS_PATH.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return str(tokens["access_token"])


def _fetch_acled_country(country: str, date_to: str, page_limit: int = 5000) -> list[dict]:
    """Fetch all ACLED events for one country, April 2023 -> ``date_to``.

    Pages through ``/api/acled/read`` (``limit`` + 1-indexed ``page``), stopping
    when a page returns fewer rows than ``page_limit``. Page GETs go through the
    shared ``requests_cache`` session so notebook re-runs are free.
    """
    rows: list[dict] = []
    page = 1
    while True:
        resp = session.get(
            ACLED_READ_URL,
            params={
                "country": country,
                "event_date": f"{ACLED_START_DATE}|{date_to}",
                "event_date_where": "BETWEEN",
                "limit": page_limit,
                "page": page,
            },
            headers={"Authorization": f"Bearer {acled_access_token()}"},
            timeout=120,
        )
        resp.raise_for_status()
        batch = resp.json().get("data") or []
        rows.extend(batch)
        if len(batch) < page_limit:
            break
        page += 1
    return rows


def fetch_acled(date_to: str | None = None) -> pd.DataFrame:
    """Fetch ACLED events for Sudan + 5 neighbours, April 2023 -> ``date_to``.

    Parameters
    ----------
    date_to
        Inclusive end of the window (``YYYY-MM-DD``). Defaults to today (UTC).

    Returns
    -------
    pandas.DataFrame
        One row per ACLED event, all source columns preserved. A ``country``
        column is always present for downstream admin-1 reconciliation.

    Notes
    -----
    This hits the live API. The canonical analytic input is the *pinned*
    parquet snapshot written by :func:`snapshot_acled` — call that once, then
    read it back. Do not re-fetch silently in the analysis notebook.
    """
    date_to = date_to or datetime.now(UTC).date().isoformat()
    frames = [pd.DataFrame(_fetch_acled_country(country, date_to)) for country in ACLED_COUNTRIES]
    df = pd.concat(frames, ignore_index=True)
    # ACLED revises records; event_id_cnty is the stable per-event key.
    if "event_id_cnty" in df.columns:
        df = df.drop_duplicates(subset="event_id_cnty", ignore_index=True)
    return df


def load_acled_exports(access_date: str) -> pd.DataFrame:
    """Read ACLED Data Export Tool CSV(s) for the given access date.

    The API ``/read`` endpoint is gated behind ACLED's Research tier; the
    Data Export Tool is the manual fallback (one combined CSV or one per
    country). This reads every ``data/raw/acled_export_*<access_date>.csv``,
    concatenates, and de-duplicates on ``event_id_cnty`` — yielding the same
    shape as :func:`fetch_acled`.
    """
    paths = sorted(RAW_DIR.glob(f"acled_export*{access_date}.csv"))
    if not paths:
        raise FileNotFoundError(
            f"No ACLED export CSV found in {RAW_DIR} matching "
            f"'acled_export*{access_date}.csv'. Download it from the ACLED Data "
            "Export Tool (https://acleddata.com/data-export-tool/)."
        )
    df = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    if "event_id_cnty" in df.columns:
        df = df.drop_duplicates(subset="event_id_cnty", ignore_index=True)
    return df


def snapshot_acled(
    date_to: str | None = None, source: str = "export", access_date: str | None = None
) -> Path:
    """Write the pinned ACLED parquet snapshot.

    Writes ``data/processed/acled_snapshot_<access_date>.parquet``. ACLED
    revises history as new sourcing emerges, so this snapshot — not the live
    source — is the canonical analytic input for every notebook run (CLAUDE.md).

    Parameters
    ----------
    date_to
        Inclusive end of the window (``api`` source only). Defaults to today.
    source
        ``"export"`` (default) reads the manually downloaded Data Export Tool
        CSV(s) via :func:`load_acled_exports`; ``"api"`` calls the live
        ``/read`` endpoint via :func:`fetch_acled` (needs Research-tier access).
    access_date
        Snapshot date stamp (``YYYY-MM-DD``). Defaults to today (UTC). For the
        ``export`` source it also selects which export CSV(s) to read.
    """
    access_date = access_date or datetime.now(UTC).date().isoformat()
    if source == "api":
        df = fetch_acled(date_to=date_to)
    elif source == "export":
        df = load_acled_exports(access_date)
    else:
        raise ValueError(f"source must be 'export' or 'api', got {source!r}")
    path = PROCESSED_DIR / f"acled_snapshot_{access_date}.parquet"
    df.to_parquet(path, index=False)
    return path


# ===========================================================================
# UNHCR ingestion (Session 3)
# ===========================================================================
#
# Two complementary UNHCR sources, both public and key-free:
#
#  1. Refugee Statistics API (api.unhcr.org) -- *annual* origin->asylum counts.
#     Clean, complete back to 2023, broken out by country of asylum. This is
#     the canonical cross-border origin-destination source.
#  2. Operational Data Portal (data.unhcr.org) -- the "Sudan situation"
#     (situation_view_id 63). Gives a daily/weekly *cumulative* time series
#     (situation-wide) and a per-destination-country cumulative snapshot. The
#     portal does NOT expose a per-country time series, so per-country
#     granularity is annual (source 1) and the portal supplies the temporal
#     shape of the aggregate (source 2).
#
# The portal reports each destination country as of a different date (e.g.
# Egypt is frozen months behind Chad) -- a caveat for the S6 reconciliation.

UNHCR_STATS_URL = "https://api.unhcr.org/population/v1/population/"
UNHCR_PORTAL_URL = "https://data.unhcr.org/population/"
UNHCR_PORTAL_TS_URL = "https://data.unhcr.org/population/get/timeseries"
UNHCR_PORTAL_SUBLOC_URL = "https://data.unhcr.org/population/get/sublocation"

# data.unhcr.org "Sudan situation" identifiers (discovered from the portal page).
UNHCR_SUDAN_SITUATION_ID = 63
# Portal population groups within the Sudan situation:
#   5550 Refugees from Sudan - Newly Arrival 2023   (cross-border refugees)
#   5551 Refugees from Sudan - Newly returnees 2023
#   5552 IDP in Sudan - 2023 Situation
#   5583 Self-relocated Refugees in Sudan
UNHCR_PG_REFUGEES = "5550"
UNHCR_PG_ALL = "5550,5551,5552,5583"
# Portal widget ids on the Sudan situation page (situation-wide aggregates).
UNHCR_WIDGET_REFUGEES = 677407  # refugees-only cumulative series
UNHCR_WIDGET_ALL = 677404  # all-displacement cumulative series

ACLED_START_YEAR = 2023


def fetch_unhcr_statistics(
    year_from: int = ACLED_START_YEAR, year_to: int | None = None
) -> pd.DataFrame:
    """Fetch annual UNHCR refugee counts, origin Sudan -> each country of asylum.

    Uses the Refugee Statistics API (``api.unhcr.org``), which needs no key.
    Returns one row per ``(year, country_of_asylum)`` for refugees originating
    in Sudan. Numeric columns are coerced to integers (the API emits ``"-"``
    and ``"0"`` as strings).

    Parameters
    ----------
    year_from, year_to
        Inclusive year bounds. ``year_to`` defaults to the current UTC year.
    """
    year_to = year_to or datetime.now(UTC).year
    base = {
        "coo": "SDN",  # country of origin = Sudan
        "coa_all": "true",  # break results out by country of asylum
        "cf_type": "ISO",
        "yearFrom": year_from,
        "yearTo": year_to,
        "limit": 1000,
    }
    rows: list[dict] = []
    page = 1
    while True:
        resp = session.get(UNHCR_STATS_URL, params={**base, "page": page}, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        rows.extend(payload.get("items") or [])
        if page >= int(payload.get("maxPages", 1)):
            break
        page += 1

    df = pd.DataFrame(rows)
    num_cols = ["refugees", "asylum_seekers", "returned_refugees", "idps", "stateless"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    keep = ["year", "coo_name", "coa_name", "coa_iso", *num_cols]
    return df[[c for c in keep if c in df.columns]].sort_values(
        ["year", "coa_name"], ignore_index=True
    )


def fetch_unhcr_situation_countries(population_group: str = UNHCR_PG_REFUGEES) -> pd.DataFrame:
    """Fetch cumulative Sudan-origin arrivals by destination country (portal snapshot).

    Hits the Operational Data Portal ``sublocation`` endpoint for the Sudan
    situation. Returns one row per destination country with the latest
    cumulative ``individuals`` count and the ``as_of_date`` it was reported --
    the as-of date differs per country, so it is kept as a column.
    """
    resp = session.get(
        UNHCR_PORTAL_SUBLOC_URL,
        params={
            "widget_id": UNHCR_WIDGET_ALL,
            "sv_id": UNHCR_SUDAN_SITUATION_ID,
            "population_group": population_group,
            "forcesvid": 1,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    df = pd.DataFrame(
        {
            "destination": r.get("geomaster_name"),
            "geomaster_id": r.get("geomaster_id"),
            "individuals": pd.to_numeric(r.get("individuals"), errors="coerce"),
            "as_of_date": r.get("date"),
            "centroid_lat": r.get("centroid_lat"),
            "centroid_lon": r.get("centroid_lon"),
        }
        for r in data
    )
    df["origin"] = "Sudan"
    return df.sort_values("individuals", ascending=False, ignore_index=True)


def fetch_unhcr_situation_timeseries(refugees_only: bool = True) -> pd.DataFrame:
    """Fetch the situation-wide cumulative displacement time series (portal).

    Returns a ``(date, individuals)`` frame -- daily early in the crisis,
    weekly later. ``refugees_only=True`` covers cross-border refugees;
    ``False`` covers all displacement (refugees + returnees + IDPs +
    self-relocated). The series is *cumulative*, not per-period.
    """
    widget = UNHCR_WIDGET_REFUGEES if refugees_only else UNHCR_WIDGET_ALL
    pg = UNHCR_PG_REFUGEES if refugees_only else UNHCR_PG_ALL
    resp = session.get(
        UNHCR_PORTAL_TS_URL,
        params={
            "widget_id": widget,
            "sv_id": UNHCR_SUDAN_SITUATION_ID,
            "population_group": pg,
            "frequency": "day",
            "fromDate": ACLED_START_DATE,
        },
        timeout=60,
    )
    resp.raise_for_status()
    ts = (resp.json().get("data") or {}).get("timeseries") or []
    df = pd.DataFrame(ts)
    if not df.empty:
        df["date"] = pd.to_datetime(df["data_date"])
        df["individuals"] = pd.to_numeric(df["individuals"], errors="coerce")
        df = df[["date", "individuals"]].sort_values("date", ignore_index=True)
    return df


# ===========================================================================
# IOM DTM ingestion (Session 3)
# ===========================================================================
#
# IOM's Displacement Tracking Matrix exposes a public v3 API for non-sensitive
# IDP figures at country / admin-1 / admin-2 level. It needs a *free*
# subscription key (register at https://dtm-apim-portal.iom.int/), passed in
# the `Ocp-Apim-Subscription-Key` header. Store the key in the [dtm] block of
# secrets.toml (key `subscription_key`) or the DTM_SUBSCRIPTION_KEY env var.

DTM_BASE_URL = "https://dtmapi.iom.int/v3/displacement"
# DTM `Operation` / `CountryName` value for the Sudan crisis response.
DTM_SUDAN_COUNTRY = "Sudan"
# The DTM API sits behind an Azure Application Gateway WAF that blocks the
# default `python-requests` User-Agent with an HTML 403 (before the request
# ever reaches the API key check). A browser-style UA gets through.
DTM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _read_dtm_key() -> str:
    """Return the IOM DTM API subscription key.

    Looks first in the ``[dtm]`` block of ``secrets.toml`` (key
    ``subscription_key``), then the ``DTM_SUBSCRIPTION_KEY`` environment
    variable. Raises a clear, actionable error if neither is set.
    """
    import os

    if SECRETS_PATH.exists():
        block = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8")).get("dtm", {})
        if block.get("subscription_key"):
            return str(block["subscription_key"])
    env_key = os.environ.get("DTM_SUBSCRIPTION_KEY")
    if env_key:
        return env_key
    raise KeyError(
        "No IOM DTM subscription key found. Register a free key at "
        "https://dtm-apim-portal.iom.int/ and add it to secrets.toml as:\n"
        '    [dtm]\n    subscription_key = "..."\n'
        "or export it as the DTM_SUBSCRIPTION_KEY environment variable."
    )


def _fetch_dtm(level: str, **params: object) -> pd.DataFrame:
    """GET one DTM v3 displacement endpoint and return ``result`` as a frame.

    ``level`` is ``"admin0"``, ``"admin1"``, ``"admin2"`` or ``"country-list"``.
    The DTM API wraps its payload as ``{isSuccess, result, errorMessages}``.
    """
    resp = session.get(
        f"{DTM_BASE_URL}/{level}",
        params={k: v for k, v in params.items() if v is not None},
        headers={
            "Ocp-Apim-Subscription-Key": _read_dtm_key(),
            "User-Agent": DTM_USER_AGENT,  # bypasses the Azure WAF (see above)
        },
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("isSuccess", False):
        raise RuntimeError(f"DTM API error: {payload.get('errorMessages')}")
    return pd.DataFrame(payload.get("result") or [])


def fetch_dtm_admin1(
    country: str = DTM_SUDAN_COUNTRY,
    from_date: str = ACLED_START_DATE,
    to_date: str | None = None,
) -> pd.DataFrame:
    """Fetch IOM DTM admin-1 internal-displacement (IDP) counts for ``country``.

    Returns the DTM admin-1 IDP series -- one row per ``(admin1, reporting
    round)`` -- over the war window. Requires a DTM subscription key (see
    :func:`_read_dtm_key`). The canonical analytic input is the pinned
    snapshot written by :func:`snapshot_dtm`, not this live call.
    """
    return _fetch_dtm(
        "admin1",
        CountryName=country,
        FromReportingDate=from_date,
        ToReportingDate=to_date or datetime.now(UTC).date().isoformat(),
    )


def dtm_country_list() -> pd.DataFrame:
    """Fetch the list of countries/operations covered by the IOM DTM API."""
    return _fetch_dtm("country-list")


def snapshot_dtm(access_date: str | None = None) -> Path:
    """Write the pinned IOM DTM admin-1 parquet snapshot for Sudan.

    Writes ``data/processed/dtm_admin1_snapshot_<access_date>.parquet``. DTM
    revises figures as new assessment rounds publish, so -- as with ACLED --
    this snapshot is the canonical analytic input, refreshed only explicitly.
    """
    access_date = access_date or datetime.now(UTC).date().isoformat()
    df = fetch_dtm_admin1()
    path = PROCESSED_DIR / f"dtm_admin1_snapshot_{access_date}.parquet"
    df.to_parquet(path, index=False)
    return path


# ===========================================================================
# GADM admin-1 boundaries (Session 3)
# ===========================================================================
#
# GADM 4.1 admin-1 (state/province) polygons for Sudan + the five neighbours,
# downloaded as per-country zipped GeoJSON from the public UC Davis mirror.
# Used in S4 to co-register the violence and displacement layers on a common
# admin-1 grid.

GADM_BASE_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json"
GADM_DIR = RAW_DIR / "gadm"

# Country -> ISO 3166-1 alpha-3 (GADM file codes). Names match ACLED's
# `country` field for a clean later join.
GADM_ISO3 = {
    "Sudan": "SDN",
    "Chad": "TCD",
    "South Sudan": "SSD",
    "Egypt": "EGY",
    "Ethiopia": "ETH",
    "Central African Republic": "CAF",
}


def download_gadm_admin1(force: bool = False) -> dict[str, Path]:
    """Download GADM 4.1 admin-1 GeoJSON for Sudan + 5 neighbours.

    Each country is a separate zipped GeoJSON (``gadm41_<ISO3>_1.json.zip``).
    Files land in ``data/raw/gadm/`` (gitignored). Returns a mapping of
    country name -> local zip path.
    """
    GADM_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for country, iso3 in GADM_ISO3.items():
        fname = f"gadm41_{iso3}_1.json.zip"
        paths[country] = download_file(f"{GADM_BASE_URL}/{fname}", GADM_DIR / fname, force=force)
    return paths


def load_gadm_admin1(force: bool = False):
    """Load GADM 4.1 admin-1 polygons for all six countries as one GeoDataFrame.

    Downloads on first call (see :func:`download_gadm_admin1`), then reads each
    zipped GeoJSON with geopandas and concatenates. The key columns for the S4
    crosswalk are ``COUNTRY``, ``NAME_1`` (admin-1 name) and ``GID_1``.

    Requires the ``[geo]`` extra (geopandas + pyogrio).
    """
    import geopandas as gpd

    paths = download_gadm_admin1(force=force)
    frames = [gpd.read_file(p) for p in paths.values()]
    combined = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=frames[0].crs)


# ===========================================================================
# Admin-1 crosswalk / geo reconciliation (Session 4 — Decision 6)
# ===========================================================================
#
# ACLED, IOM DTM and GADM each label admin-1 units with their own conventions:
#   - ACLED   : English names with spaces ("North Kordofan", "Al Jazirah").
#   - IOM DTM : OCHA names + pcodes ("Aj Jazirah", SD01-SD18).
#   - GADM 4.1: BGN/PCGN romanisation, no spaces ("NorthKurdufan", "AlQadarif").
# UNHCR cross-border data is country-level only (Decision D3), so its crosswalk
# role is the destination *country* (ISO3), not an admin-1 unit.
#
# The crosswalk co-registers all of these on the GADM polygon set, keyed for
# Sudan by the OCHA pcode (SD01-SD18 — also DTM's key) and for the neighbours
# by GADM's GID_1. See decision block 6 for the full reconciliation rationale.

CROSSWALK_PATH = PROCESSED_DIR / "admin1_crosswalk.csv"

# ACLED reports "Abyei" as a 19th Sudan admin-1 unit. The Abyei Area is a
# disputed Sudan/South Sudan territory with no GADM 4.1 polygon and no DTM
# pcode. Per Decision 6 its ACLED events are folded into South Kordofan — the
# Sudan state Abyei most directly adjoins (it was administratively carved out
# of South Kordofan). The sensitivity of this merge is checked in S10.
ACLED_ADMIN1_REMAP: dict[tuple[str, str], tuple[str, str]] = {
    ("Sudan", "Abyei"): ("Sudan", "South Kordofan"),
}

# GADM admin-1 names that no amount of normalisation can bridge to the ACLED
# string — distinct romanisations resolved by hand. Keyed by (ISO3, GADM
# NAME_1) -> ACLED admin1 string. Egypt is deliberately absent: ACLED and GADM
# use entirely different romanisation systems for all 27 governorates, and
# Egypt's role here is a refugee *destination* (country-level, Decision D3) —
# its admin-1 violence detail is not used by any deliverable, so reconciling
# 27 governorate names by hand would be effort without downstream value.
_CROSSWALK_NAME_OVERRIDES: dict[tuple[str, str], str] = {
    ("SDN", "AlQadarif"): "Gedaref",
    ("TCD", "VilledeN'Djamena"): "Ndjamena",
    ("SSD", "Jungoli"): "Jonglei",
    ("SSD", "Warap"): "Warrap",
    ("SSD", "NorthBahr-al-Ghazal"): "Northern Bahr el Ghazal",
    ("SSD", "WestBahr-al-Ghazal"): "Western Bahr el Ghazal",
    ("SSD", "WestEquatoria"): "Western Equatoria",
    ("ETH", "AddisAbeba"): "Addis Ababa",
    ("ETH", "Benshangul-Gumaz"): "Benshangul/Gumuz",
    ("ETH", "GambelaPeoples"): "Gambela",
    ("ETH", "HarariPeople"): "Harari",
}


def _norm_admin1(name: object) -> str:
    """Normalise an admin-1 name for matching across sources.

    Strips diacritics, lower-cases, drops every non-alphanumeric character,
    then applies a few token substitutions for known romanisation splits
    (GADM's "Kurdufan" vs "Kordofan", "Aj Jazirah" vs "Al Jazirah"). This
    bridges spacing, casing and accent differences; genuine romanisation
    divergences are handled by :data:`_CROSSWALK_NAME_OVERRIDES`.
    """
    decomposed = unicodedata.normalize("NFKD", str(name))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    key = re.sub(r"[^a-z0-9]", "", stripped.lower())
    for src, dst in (("kurdufan", "kordofan"), ("ajjazirah", "aljazirah")):
        key = key.replace(src, dst)
    return key


def _latest_snapshot(prefix: str) -> Path:
    """Return the most recent ``data/processed/<prefix>_*.parquet`` snapshot."""
    paths = sorted(PROCESSED_DIR.glob(f"{prefix}_*.parquet"))
    if not paths:
        raise FileNotFoundError(
            f"No {prefix}_*.parquet snapshot in {PROCESSED_DIR}. Run the "
            "corresponding ingestion session first."
        )
    return paths[-1]


def build_admin1_crosswalk(write: bool = True) -> pd.DataFrame:
    """Build the admin-1 crosswalk reconciling GADM, ACLED and IOM DTM.

    Produces one row per GADM 4.1 admin-1 polygon (Sudan + 5 neighbours, 106
    rows) with the matched ACLED admin1 string and — for Sudan — the IOM DTM
    pcode/name. Matching is by :func:`_norm_admin1` normalisation, with
    :data:`_CROSSWALK_NAME_OVERRIDES` for irreducible romanisation gaps.

    Columns: ``country``, ``iso3``, ``gadm_gid1``, ``gadm_name1``,
    ``canonical_pcode`` (OCHA SD-pcode for Sudan, GADM GID_1 elsewhere),
    ``acled_admin1``, ``acled_aliases`` (extra ACLED strings folded in, e.g.
    Abyei), ``dtm_pcode``, ``dtm_name``, ``match_method``, ``notes``.

    Reads the pinned ACLED and DTM snapshots and the GADM polygons. Writes
    ``data/processed/admin1_crosswalk.csv`` when ``write`` is True.
    """
    gadm = load_gadm_admin1()
    acled = pd.read_parquet(_latest_snapshot("acled_snapshot"))
    dtm = pd.read_parquet(_latest_snapshot("dtm_admin1_snapshot"))

    # ACLED admin-1 strings per ISO3, after applying the remap rules so a
    # remapped value (Abyei) is not reported as unmatched. `aliases` records,
    # per target name, which extra ACLED strings were folded into it.
    acled_lookup: dict[str, dict[str, str]] = {}
    acled_aliases: dict[tuple[str, str], list[str]] = {}
    for country, iso in GADM_ISO3.items():
        names = set(acled.loc[acled.country == country, "admin1"].dropna())
        resolved: dict[str, str] = {}
        for raw in names:
            remap = ACLED_ADMIN1_REMAP.get((country, raw))
            target = remap[1] if remap else raw
            resolved[_norm_admin1(target)] = target
            if remap:
                acled_aliases.setdefault((iso, target), []).append(raw)
        acled_lookup[iso] = resolved

    # DTM normalised lookup (Sudan only): normalised name -> (name, pcode).
    dtm_lookup = {
        _norm_admin1(r.admin1Name): (r.admin1Name, r.admin1Pcode)
        for r in dtm[["admin1Name", "admin1Pcode"]].drop_duplicates().itertuples()
    }

    rows: list[dict] = []
    for r in gadm.sort_values(["GID_0", "GID_1"]).itertuples():
        iso = r.GID_0
        gadm_name = r.NAME_1
        norm_g = _norm_admin1(gadm_name)
        country_acled = acled_lookup.get(iso, {})

        override = _CROSSWALK_NAME_OVERRIDES.get((iso, gadm_name))
        if override is not None:
            acled_match: str | None = override
            method = "manual_override"
        elif gadm_name in {v for v in country_acled.values()}:
            acled_match = gadm_name
            method = "exact"
        elif norm_g in country_acled:
            acled_match = country_acled[norm_g]
            method = "normalized"
        else:
            acled_match = None
            method = "unmatched"

        if iso == "SDN":
            # DTM and ACLED romanise Sudan states near-identically; resolve the
            # DTM pcode via the (override-corrected) ACLED match where present.
            dtm_key = _norm_admin1(acled_match) if acled_match else norm_g
            dtm_name, dtm_pcode = dtm_lookup.get(dtm_key, (None, None))
            canonical = dtm_pcode
        else:
            dtm_name = dtm_pcode = None
            canonical = r.GID_1

        aliases = acled_aliases.get((iso, acled_match), []) if acled_match else []
        notes = ""
        if method == "unmatched":
            notes = "no ACLED admin1 match — see decision block 6"
        if aliases:
            notes = f"ACLED '{', '.join(aliases)}' folded into this unit"

        rows.append(
            {
                "country": r.COUNTRY,
                "iso3": iso,
                "gadm_gid1": r.GID_1,
                "gadm_name1": gadm_name,
                "canonical_pcode": canonical,
                "acled_admin1": acled_match,
                "acled_aliases": ";".join(aliases),
                "dtm_pcode": dtm_pcode,
                "dtm_name": dtm_name,
                "match_method": method,
                "notes": notes,
            }
        )

    crosswalk = pd.DataFrame(rows)
    if write:
        crosswalk.to_csv(CROSSWALK_PATH, index=False)
    return crosswalk


def crosswalk_unmatched_acled() -> pd.DataFrame:
    """Return ACLED admin1 strings with no row in the crosswalk.

    These are ACLED units that did not match any GADM polygon — enumerated so
    the non-matching cases are explicit (a Decision 6 completion criterion).
    Abyei is *absent* here: it is remapped to South Kordofan, not dropped.
    """
    crosswalk = load_admin1_crosswalk()
    acled = pd.read_parquet(_latest_snapshot("acled_snapshot"))
    matched = {
        (iso, _norm_admin1(name))
        for iso, name in crosswalk[["iso3", "acled_admin1"]].dropna().itertuples(index=False)
    }
    iso_by_country = {c: i for c, i in GADM_ISO3.items()}
    out: list[dict] = []
    for country, raw in (
        acled[["country", "admin1"]].dropna().drop_duplicates().itertuples(index=False)
    ):
        iso = iso_by_country[country]
        remap = ACLED_ADMIN1_REMAP.get((country, raw))
        if remap:
            continue  # explicitly remapped, not unmatched
        if (iso, _norm_admin1(raw)) not in matched:
            out.append({"country": country, "iso3": iso, "acled_admin1": raw})
    return pd.DataFrame(out).sort_values(["country", "acled_admin1"], ignore_index=True)


def load_admin1_crosswalk() -> pd.DataFrame:
    """Read the admin-1 crosswalk, building it on first use if absent."""
    if not CROSSWALK_PATH.exists():
        return build_admin1_crosswalk(write=True)
    return pd.read_csv(CROSSWALK_PATH)
