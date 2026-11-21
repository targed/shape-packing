"""Coordinator server package for distributed shape packing."""
from __future__ import annotations

from .database import (
    CANONICAL_SHAPE_TOKENS,
    RECORD_MIN_IMPROVEMENT,
    SCHEMA,
    get_problem,
    init_db,
    normalize_shape_token,
    register_worker,
    seed_problems_from_verification,
    update_solution_record,
)

__all__ = [
    "SCHEMA",
    "RECORD_MIN_IMPROVEMENT",
    "CANONICAL_SHAPE_TOKENS",
    "normalize_shape_token",
    "init_db",
    "register_worker",
    "get_problem",
    "update_solution_record",
    "seed_problems_from_verification",
]
