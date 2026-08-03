"""Prompt template registry (placeholder).

Phase 0 only reserves this module so later phases (Phase 6 — AI Intelligence)
can add versioned, structured prompt templates here instead of scattering raw
strings through the codebase. Intentionally empty of real prompts for now.

See the Engineering Design Document §5.9 (Prompt Strategy) for the structure
these templates must follow: system instructions, structured analytics,
retrieved knowledge, required output format, and validation constraints.
"""

from __future__ import annotations

# Populated in Phase 6. Kept as an explicit, empty registry so its shape is
# established from the start.
PROMPT_TEMPLATES: dict[str, str] = {}
