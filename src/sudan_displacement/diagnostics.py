"""Diagnostic helpers for educated data-processing decisions.

These utilities support the "decision discipline" pattern from
``notebooks/NOTEBOOK_STRUCTURE.md``: every meaningful data-processing step
is preceded by diagnostic analysis that informs the choice between alternatives.

The functions here are deliberately small and composable — they print/return
summary tables that fit naturally into a notebook decision block. Each project
will add its own domain-specific diagnostics on top of these.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Missingness
# ---------------------------------------------------------------------------

def missingness_summary(df: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """High-level missingness summary as a DataFrame.

    Parameters
    ----------
    df
        DataFrame to summarize.
    by
        Optional grouping column. If given, returns missingness per group.

    Returns
    -------
    DataFrame with columns ``column``, ``n_missing``, ``pct_missing``,
    sorted descending by ``pct_missing``. If ``by`` is set, ``by`` is included.

    Example
    -------
    >>> missingness_summary(df).head()
    >>> missingness_summary(df, by="country")  # per-country missingness
    """
    if by is None:
        out = pd.DataFrame(
            {
                "n_missing": df.isna().sum(),
                "pct_missing": (df.isna().mean() * 100).round(2),
            }
        )
        out.index.name = "column"
        return out.reset_index().sort_values("pct_missing", ascending=False)

    rows = []
    for group_val, sub in df.groupby(by):
        for col in sub.columns:
            if col == by:
                continue
            rows.append(
                {
                    by: group_val,
                    "column": col,
                    "n_missing": int(sub[col].isna().sum()),
                    "pct_missing": round(float(sub[col].isna().mean() * 100), 2),
                }
            )
    return (
        pd.DataFrame(rows)
        .sort_values([by, "pct_missing"], ascending=[True, False])
        .reset_index(drop=True)
    )


def missingness_pattern(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Most common missingness *patterns* across rows.

    A "pattern" is the set of columns that are missing together in a row.
    Useful for distinguishing MCAR-looking randomness from structural gaps
    (e.g. an entire reporting period missing for several variables at once).

    Returns
    -------
    DataFrame with one row per pattern: which columns are missing,
    how many rows show that pattern, and the share of rows.
    """
    nulls = df.isna()
    patterns = nulls.apply(
        lambda r: ", ".join(sorted(c for c in df.columns if r[c])) or "<no missing>",
        axis=1,
    )
    counts = patterns.value_counts().head(top_n)
    return pd.DataFrame(
        {
            "pattern": counts.index,
            "n_rows": counts.values,
            "pct_rows": (counts.values / len(df) * 100).round(2),
        }
    )


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

def distribution_summary(
    s: pd.Series,
    percentiles: tuple[float, ...] = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99),
) -> pd.Series:
    """Extended ``describe()`` with skew, kurtosis, and unique count.

    Useful at the start of a decision block to characterize a variable
    before deciding e.g. whether to log-transform, winsorize, or leave alone.
    """
    desc = s.describe(percentiles=list(percentiles)).to_dict()
    desc["skew"] = float(s.skew())
    desc["kurtosis"] = float(s.kurtosis())
    desc["n_unique"] = int(s.nunique())
    desc["n_missing"] = int(s.isna().sum())
    return pd.Series(desc)


def distribution_compare(
    series_dict: dict[str, pd.Series],
    percentiles: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75, 0.95),
) -> pd.DataFrame:
    """Compare distributions side-by-side.

    Parameters
    ----------
    series_dict
        Mapping ``{label: Series}``. Useful for comparing:
        - before vs. after a transformation
        - the same variable across groups
        - alternative imputation outputs

    Returns
    -------
    DataFrame with one row per label and percentile/moment columns.
    """
    rows = []
    for label, s in series_dict.items():
        row = {"label": label, "n": int(s.notna().sum())}
        row.update({"mean": float(s.mean()), "std": float(s.std())})
        for p in percentiles:
            row[f"p{int(p * 100):02d}"] = float(s.quantile(p))
        row["skew"] = float(s.skew())
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Before / after comparisons
# ---------------------------------------------------------------------------

def before_after(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    label_before: str = "before",
    label_after: str = "after",
) -> pd.DataFrame:
    """High-level comparison of two DataFrames after a transformation.

    Documents "what changed" — useful at the end of a cleaning step
    to make the impact visible in the notebook.
    """
    common = sorted(set(df_before.columns) & set(df_after.columns))
    rows = []
    for col in common:
        rows.append(
            {
                "column": col,
                f"n_{label_before}": len(df_before),
                f"n_{label_after}": len(df_after),
                f"missing_{label_before}": int(df_before[col].isna().sum()),
                f"missing_{label_after}": int(df_after[col].isna().sum()),
                f"dtype_{label_before}": str(df_before[col].dtype),
                f"dtype_{label_after}": str(df_after[col].dtype),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Alternatives comparison (sensitivity)
# ---------------------------------------------------------------------------

def compare_alternatives(
    data: Any,
    alternatives: dict[str, Callable[[Any], Any]],
    summarize: Callable[[Any], dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Apply several alternative functions to the same data and compare outcomes.

    The classic sensitivity-check helper: feed it the data and a dict of
    candidate processing functions (e.g. different imputation strategies),
    and get back a side-by-side summary of what each produces.

    Parameters
    ----------
    data
        Input data passed to each alternative function.
    alternatives
        Mapping ``{name: fn}`` where each ``fn`` takes ``data`` and returns
        either a DataFrame, Series, scalar, or something ``summarize`` can handle.
    summarize
        Optional custom summary function. If None, uses sensible defaults
        for DataFrame / Series / scalar.

    Returns
    -------
    DataFrame, one row per alternative.

    Example
    -------
    >>> compare_alternatives(
    ...     series,
    ...     {
    ...         "mean_impute": lambda s: s.fillna(s.mean()),
    ...         "median_impute": lambda s: s.fillna(s.median()),
    ...         "drop_missing": lambda s: s.dropna(),
    ...     },
    ... )
    """
    def _default_summary(result: Any) -> dict[str, Any]:
        if isinstance(result, pd.DataFrame):
            return {"n_rows": len(result), "n_cols": result.shape[1]}
        if isinstance(result, pd.Series):
            return {
                "n": int(result.notna().sum()),
                "mean": float(result.mean()) if pd.api.types.is_numeric_dtype(result) else np.nan,
                "std": float(result.std()) if pd.api.types.is_numeric_dtype(result) else np.nan,
            }
        return {"value": result}

    summarize = summarize or _default_summary

    rows = []
    for name, fn in alternatives.items():
        result = fn(data)
        row = {"alternative": name}
        row.update(summarize(result))
        rows.append(row)
    return pd.DataFrame(rows)
