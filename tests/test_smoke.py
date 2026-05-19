"""Smoke tests — verify the project module imports and data paths exist."""


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
