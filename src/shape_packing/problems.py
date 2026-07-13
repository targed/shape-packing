"""
problems.py

ProblemModule: deep module for "what is a packing problem?"

Single, testable seam for:
- Parsing problem names
- Mapping shape tokens to polygon sides
- Validating problem specifications
- Generating packer CLI arguments from a Problem

Consumers:
- train.py
- verify_solution.py
- render_solution.py (if it needs semantic problem info)
- agent loops / future tooling
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .packing_config import SHAPE_TO_SIDES, SPECIAL_SHAPES, ALL_FAMILIES


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Problem:
    """
    Represents one packing problem, e.g. '8_3_in_5' means:
    8 triangles packed in a regular pentagon container.

    - name:          canonical identifier, e.g. "8_3_in_5"
    - N:             number of inner shapes
    - inner_token:   token for the inner shape, e.g. "3", "CIRCLE", "DOMINO"
    - container_token: token for the container shape, e.g. "5", "CIRCLE"
    """
    name: str
    N: int
    inner_token: str
    container_token: str


# ---------------------------------------------------------------------------
# Core interface
# ---------------------------------------------------------------------------

def parse_problem(name: str) -> Problem:
    """
    Parse a problem name in the canonical format:

        {N}_{inner}_in_{container}

    Examples:
        "8_3_in_5"         -> Problem(8, "3",   "5")
        "10_4_in_CIRCLE"   -> Problem(10, "4", "CIRCLE")
        "12_DOMINO_in_4"   -> Problem(12, "DOMINO", "4")

    Raises ValueError if the format is invalid.
    """
    m = re.match(r"^(\d+)_(.+)_(in)_(.+)$", name)
    if not m:
        raise ValueError(f"Invalid problem format: {name!r}. Expected: N_inner_in_container")

    N = int(m.group(1))
    inner_token = m.group(2)
    container_token = m.group(4)

    return Problem(
        name=name,
        N=N,
        inner_token=inner_token,
        container_token=container_token,
    )


def shape_token_to_sides(token: str) -> Optional[int]:
    """
    Map a shape token to the number of sides of a regular polygon.

    - For known tokens in SHAPE_TO_SIDES: use that (case-insensitive).
    - For special shapes (TAN, DOMINO, L): return None (handled separately).
    - For numeric tokens >= 3: treat as that many sides.
    - Otherwise: raise ValueError.
    """
    t = token.strip().upper()

    if is_special_shape(t):
        return None

    if t in SHAPE_TO_SIDES:
        return SHAPE_TO_SIDES[t]

    # Support arbitrary numeric tokens like "7" or "12"
    try:
        s = int(token)
        if s >= 3:
            return s
    except ValueError:
        pass

    raise ValueError(f"Cannot map shape token to sides: {token!r}")


def is_special_shape(token: str) -> bool:
    """
    True if token corresponds to a special (non-regular-polygon) shape
    requiring custom geometry logic.

    Examples: TAN, DOMINO, L
    """
    return token.upper() in {s.upper() for s in SPECIAL_SHAPES}


def validate_problem(p: Problem) -> None:
    """
    Validate that a Problem is well-formed according to current conventions.

    Checks:
    - N > 0
    - inner_token and container_token are recognizable
    - If both are numeric or in SHAPE_TO_SIDES, they are >= 3
      (special shapes allowed with no extra constraint for now)

    Raises ValueError with a message describing the issue.
    """
    if p.N <= 0:
        raise ValueError(
            f"Problem {p.name!r}: N must be > 0, got {p.N}"
        )

    # Validate inner token
    _validate_token(p.inner_token, "inner", p.name)
    # Validate container token
    _validate_token(p.container_token, "container", p.name)


def _validate_token(token: str, role: str, problem_name: str) -> None:
    """
    Helper for validate_problem to check a single token.
    role is 'inner' or 'container' for clearer errors.
    """
    if is_special_shape(token):
        return

    if token in SHAPE_TO_SIDES:
        return

    # numeric
    try:
        s = int(token)
        if s >= 3:
            return
        raise ValueError(
            f"Problem {problem_name!r}: {role} token {token!r} is numeric but < 3"
        )
    except ValueError:
        raise ValueError(
            f"Problem {problem_name!r}: unknown {role} token {token!r}"
        )


def problem_to_packer_args(p: Problem):
    """
    Convert a Problem to arguments suitable for calling the packer.

    Returns:
        N: int
        inner_sides: int or None
        container_sides: int or None

    - None indicates a special shape that must be handled symbolically
      by the packer or an adapter layer.
    """
    N = p.N
    inner_sides = shape_token_to_sides(p.inner_token)
    container_sides = shape_token_to_sides(p.container_token)
    return N, inner_sides, container_sides


def list_problem_families() -> list[str]:
    """
    Return the catalog of problem families (e.g. 'Triangles in Circles').

    Delegates to packing_config.ALL_FAMILIES.
    """
    return list(ALL_FAMILIES)