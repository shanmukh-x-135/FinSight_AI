"""Feature flags.

A tiny, dependency-free flag registry. Flags default to off and can be
overridden by environment variables of the form ``FEATURE_<NAME>=true``.
Later phases add real flags (e.g. gating the scheduler or AI report generation);
Phase 0 only establishes the mechanism.
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}


def is_enabled(name: str, default: bool = False) -> bool:
    """Return whether feature ``name`` is enabled.

    Checks the environment variable ``FEATURE_<NAME>`` (case-insensitive),
    falling back to ``default``.
    """
    raw = os.getenv(f"FEATURE_{name.upper()}")
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY
