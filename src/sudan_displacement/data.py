"""Data loading utilities with HTTP caching.

All API calls go through a memoized session so notebooks re-run fast.
Paths are resolved relative to the project root (the folder containing pyproject.toml).

Source-specific loaders (ACLED, UNHCR, IOM DTM, GADM) are added in later
sessions; this module currently provides the shared cache + path scaffolding.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
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
