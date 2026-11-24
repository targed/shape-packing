"""Shared declarative shape catalog and capability registry."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

CATALOG_PATH = Path(__file__).resolve().parent / "shape_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    """Load the declarative shape catalog JSON once per process."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _alias_index() -> Dict[str, str]:
    catalog = load_catalog()
    index: Dict[str, str] = {}
    for canonical, spec in catalog["shapes"].items():
        index[canonical.upper()] = canonical
        for alias in spec.get("aliases", []):
            index[str(alias).strip().upper()] = canonical
    return index


def get_canonical_tokens() -> Set[str]:
    """Return the set of all canonical shape tokens in the catalog."""
    return set(load_catalog()["shapes"].keys())


def normalize_token(token: Any) -> str:
    """Normalize any alias or numeric/string token to its canonical uppercase token."""
    if token is None:
        return ""
    raw = str(token).strip().upper()
    if not raw:
        return ""
    return _alias_index().get(raw, raw)


def get_shape_spec(token: Any) -> Optional[Dict[str, Any]]:
    """Return catalog metadata dict for a canonical token or alias, else None."""
    canon = normalize_token(token)
    return load_catalog()["shapes"].get(canon)


def is_curved_circle_container(token: Any) -> bool:
    """Return True if token is a curved container restricted strictly to CIRCLE inner items."""
    spec = get_shape_spec(token)
    return bool(spec and spec.get("kind") == "curved_circle_container")


@lru_cache(maxsize=1)
def _pair_tier_map() -> Dict[Tuple[str, str], str]:
    rules = load_catalog()["pair_rules"]
    pairs: Dict[Tuple[str, str], str] = {}

    base = rules["benchmark_base"]
    for inner in base:
        for container in base:
            pairs[(inner, container)] = "benchmark"

    for inner, container in rules["benchmark_extra_pairs"]:
        pairs[(inner, container)] = "benchmark"

    quads = rules["frontier_quads"]
    partners = rules["frontier_partners"]
    for q in quads:
        for p in partners:
            pairs[(q, p)] = "frontier"
            pairs[(p, q)] = "frontier"
        for q2 in quads:
            pairs[(q, q2)] = "frontier"

    return pairs


def is_pair_supported(inner_token: Any, container_token: Any) -> bool:
    """Return True if (inner, container) is enabled under Option B capabilities."""
    inner = normalize_token(inner_token)
    container = normalize_token(container_token)
    if not inner or not container:
        return False
    return (inner, container) in _pair_tier_map()


def get_pair_tier(inner_token: Any, container_token: Any) -> Optional[str]:
    """Return 'benchmark' or 'frontier' for supported pairs, or None if unsupported."""
    inner = normalize_token(inner_token)
    container = normalize_token(container_token)
    return _pair_tier_map().get((inner, container))


def list_frontier_families() -> List[Tuple[str, str, str]]:
    """Return deterministic list of (family_slug, inner_token, container_token) for all Frontier pairs."""
    shapes = load_catalog()["shapes"]
    out: List[Tuple[str, str, str]] = []
    for (inner, container), tier in sorted(_pair_tier_map().items()):
        if tier != "frontier":
            continue
        i_slug = shapes[inner]["slug"]
        c_slug = shapes[container]["slug"]
        out.append((f"{i_slug}_in_{c_slug}", inner, container))
    return out


def list_benchmark_extra_families() -> List[Tuple[str, str, str]]:
    """Return Packomania non-grid benchmark families (cirin7, cirin9, cirin10, cirinsemi, cirinquad)."""
    shapes = load_catalog()["shapes"]
    rules = load_catalog()["pair_rules"]
    out: List[Tuple[str, str, str]] = []
    for inner, container in rules["benchmark_extra_pairs"]:
        i_slug = shapes[inner]["slug"]
        c_slug = shapes[container]["slug"]
        out.append((f"{i_slug}_in_{c_slug}", inner, container))
    return out


def shape_area(token: Any, size: float) -> Optional[float]:
    """Compute exact 2D area of shape at given characteristic metric size (unit=1.0 for inner)."""
    if size is None or size <= 0 or math.isnan(size) or math.isinf(size):
        return None
    canon = normalize_token(token)
    spec = get_shape_spec(canon)
    if spec is not None:
        kind = spec["kind"]
        if kind == "regular_polygon":
            n = int(spec["sides"])
            if n == 4:
                return float(size * size)
            return 0.25 * n * (size ** 2) / math.tan(math.pi / n)
        if canon == "CIRCLE":
            return math.pi * (size ** 2)
        if canon == "SEMICIRCLE":
            return 0.5 * math.pi * (size ** 2)
        if canon == "QUADRANT":
            return 0.25 * math.pi * (size ** 2)
        if canon == "TAN":
            return 0.5 * (size ** 2)
        if canon == "DOMINO":
            return 2.0 * (size ** 2)
        if canon == "L":
            return 3.0 * (size ** 2)
        if canon == "RHOMBUS":
            return (math.sqrt(3.0) / 2.0) * (size ** 2)
        if canon == "PARALLELOGRAM":
            return 1.0 * (size ** 2)
        if canon == "TRAPEZOID":
            return (3.0 * math.sqrt(3.0) / 4.0) * (size ** 2)

    try:
        sides = int(canon)
        if sides == 4:
            return float(size * size)
        if sides >= 3:
            return 0.25 * sides * (size ** 2) / math.tan(math.pi / sides)
    except ValueError:
        pass
    return None
