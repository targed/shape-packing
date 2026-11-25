"""Coordinator server package for distributed shape packing."""
from __future__ import annotations

from .database import (
    CANONICAL_SHAPE_TOKENS,
    RECORD_MIN_IMPROVEMENT,
    SCHEMA,
    get_problem,
    init_db,
    migrate_legacy_problem_ids,
    normalize_shape_token,
    register_worker,
    seed_frontier_problems,
    seed_problems_from_verification,
    sync_problem_catalog,
    update_solution_record,
)

__all__ = [
    "SCHEMA",
    "RECORD_MIN_IMPROVEMENT",
    "CANONICAL_SHAPE_TOKENS",
    "normalize_shape_token",
    "init_db",
    "migrate_legacy_problem_ids",
    "register_worker",
    "get_problem",
    "update_solution_record",
    "seed_problems_from_verification",
    "seed_frontier_problems",
    "sync_problem_catalog",
]
