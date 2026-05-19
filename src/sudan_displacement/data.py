"""Data loading utilities with HTTP caching.

All API calls go through a memoized session so notebooks re-run fast.
Paths are resolved relative to the project root (the folder containing pyproject.toml).

Source-specific loaders (UNHCR, IOM DTM, GADM) are added in later sessions;
this module currently provides the shared cache + path scaffolding and the
ACLED loader (Session 2).
"""

from __future__ import annotations

import json
import tomllib
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
    frames = [
        pd.DataFrame(_fetch_acled_country(country, date_to))
        for country in ACLED_COUNTRIES
    ]
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
