"""
Central configuration for packing problems, parallel loops,
and adaptive attempt scaling.

This file:
- Defines per-problem geometry and metrics.
- Defines parallel-loop runtime behavior.
- Defines difficulty scoring and adaptive attempt scaling.
"""

import csv
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

# =====================
# General configuration
# =====================

RUST_PROJECT_PATH = "packer_rs"
RUST_RELEASE_BIN = os.path.join(
    RUST_PROJECT_PATH, "target", "release", "packer_rs"
)

# Alias used elsewhere
RUST_BINARY: str = RUST_RELEASE_BIN
RUST_TOLERANCE: str = "1e-28"
RUST_DEFAULT_ATTEMPTS: int = 1000
RUST_DEFAULT_TIME_LIMIT: int = 1000

# =====================
# Python optimizer constants
# =====================
OPTIMIZER_ATTEMPTS: int = 1000
OPTIMIZER_TOLERANCE: float = 1e-8
OPTIMIZER_FINAL_STEP: float = 0.0001
OPTIMIZER_N_JOBS: int = -1

# =====================
# Verification tolerances
# =====================
VERIFY_SAT_TOLERANCE: float = 1e-5
VERIFY_METRIC_TOLERANCE: float = 1e-6
GEOMETRY_SAT_TOLERANCE: float = 1e-12
MIN_VALID_CIRCLE_SCORE: float = 0.1

# =====================
# File paths
# =====================
RESULTS_DIR: str = "results"
RESULTS_TSV: str = "results.tsv"
RESULTS_TSV_PATH: str = "results.tsv"
PRIORITY_QUEUE_PATH: str = "priority_queue.json"
PACKING_VERIFICATION_DIR: str = "packingVerification"
FILTER_JSON_PATH: str = "filter.json"
PACKING_REFERENCE_TSV: str = "PACKING_REFERENCE.tsv"

# =====================
# Rendering & plot settings
# =====================
RENDER_DPI: int = 300
RENDER_FIGURE_SIZE: Tuple[int, int] = (6, 6)
RENDER_CROP_MODE: str = "tight"
RENDER_CONTAINER_LINEWIDTH: float = 2.0
RENDER_INNER_LINEWIDTH: float = 1.2
RENDER_SIZE_PX: Optional[int] = None
RENDER_PAD_PX: float = 1.0
RENDER_INNER_FACE_COLOR: str = "#CCCCCC"
RENDER_INNER_EDGE_COLOR: str = "#000000"
RENDER_CONTAINER_COLOR: str = "#000000"
RENDER_BG_COLOR: Optional[str] = "#FFFFFF"
RENDER_ALIGN_CONTAINER: bool = True
ANALYSIS_PLOT_DPI: int = 200

FAMILY_PROPERTIES_PATH: str = os.path.join(os.path.dirname(__file__), "family_properties.json")
FAMILY_COLORS_PATH: str = FAMILY_PROPERTIES_PATH
_FAMILY_PROPERTIES_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_FAMILY_COLORS_CACHE: Optional[Dict[str, Dict[str, Any]]] = None

_FAMILY_TOKEN_NAME_MAP = {
    "3": "tri",
    "4": "squ",
    "5": "pen",
    "6": "hex",
    "7": "hep",
    "8": "oct",
    "9": "non",
    "10": "dec",
    "triangle": "tri",
    "square": "squ",
    "pentagon": "pen",
    "hexagon": "hex",
    "heptagon": "hep",
    "octagon": "oct",
    "nonagon": "non",
    "decagon": "dec",
    "circle": "cir",
    "cir": "cir",
    "tan": "tan",
    "domino": "dom",
    "dom": "dom",
    "l": "l",
    "l-tromino": "l",
    "el": "el",
    "ttt": "ttt",
}


def _normalize_family_token(token: str) -> str:
    s = str(token).strip().lower()
    return _FAMILY_TOKEN_NAME_MAP.get(s, s)


def load_family_properties(json_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Load the shape family properties configuration mapping from JSON."""
    global _FAMILY_PROPERTIES_CACHE, _FAMILY_COLORS_CACHE
    if json_path is None and _FAMILY_PROPERTIES_CACHE is not None:
        return _FAMILY_PROPERTIES_CACHE

    target_path = json_path or FAMILY_PROPERTIES_PATH
    if not os.path.exists(target_path) and os.path.exists(os.path.join(os.path.dirname(__file__), "family_colors.json")):
        target_path = os.path.join(os.path.dirname(__file__), "family_colors.json")

    if os.path.exists(target_path):
        import json
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            props = {str(k).strip().lower(): v for k, v in data.items()}
            if json_path is None:
                _FAMILY_PROPERTIES_CACHE = props
                _FAMILY_COLORS_CACHE = props
            return props
    return {}


def load_family_colors(json_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Alias for load_family_properties for backward compatibility."""
    return load_family_properties(json_path)


def get_family_properties(
    inner_or_family: str,
    container: Optional[str] = None,
    json_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get full properties for a given shape family (colors, dimensions, format, filename template).
    Logs a warning if dimensions are variable or unconfirmed.
    """
    props_map = load_family_properties(json_path)

    if container is not None:
        inner_token = _normalize_family_token(str(inner_or_family))
        container_token = _normalize_family_token(str(container))
        family_key = f"{inner_token}in{container_token}"
    else:
        raw = str(inner_or_family).strip()
        if "_in_" in raw:
            parts = raw.split("_in_")
            inner_part = parts[0].split("_")[-1]
            container_part = parts[1]
            inner_token = _normalize_family_token(inner_part)
            container_token = _normalize_family_token(container_part)
            family_key = f"{inner_token}in{container_token}"
        else:
            family_key = raw.lower()

    if family_key in props_map:
        cfg = props_map[family_key]
        width = cfg.get("width")
        height = cfg.get("height")
        file_format = cfg.get("file_format", "png").lower()
        template = cfg.get("filename_template", "{n}.png")
        manual_check = cfg.get("manual_check_required", False) or cfg.get("variable_dimensions", False)

        if manual_check or width is None or height is None:
            print(f"[WARN] Shape family '{family_key}' has variable or unconfirmed dimensions ({width}x{height}, format={file_format}). Please manually check Friedman's page.")
            # Fallback default geometry dimensions if None
            if width is None:
                width = 240
            if height is None:
                height = 240

        return {
            "family_code": family_key,
            "inner": cfg.get("inner", RENDER_INNER_FACE_COLOR),
            "container": cfg.get("container", RENDER_BG_COLOR or "#FFFFFF"),
            "width": width,
            "height": height,
            "file_format": file_format,
            "filename_template": template,
            "variable_dimensions": cfg.get("variable_dimensions", False),
            "manual_check_required": manual_check,
        }

    return {
        "family_code": family_key,
        "inner": RENDER_INNER_FACE_COLOR,
        "container": RENDER_BG_COLOR or "#FFFFFF",
        "width": 240,
        "height": 240,
        "file_format": "png",
        "filename_template": "{n}.png",
        "variable_dimensions": False,
        "manual_check_required": False,
    }


def get_family_colors(
    inner_or_family: str,
    container: Optional[str] = None,
    json_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Get color and dimension dictionary for a family (backward compatible with get_family_properties)."""
    return get_family_properties(inner_or_family, container, json_path)


def get_family_target_filename(
    inner_or_family: str,
    N: int,
    container: Optional[str] = None,
    json_path: Optional[str] = None,
) -> str:
    """Resolve the exact website target filename for a problem and piece count N (e.g. 'pent.21.png', 'hc22.gif', '21.png')."""
    props = get_family_properties(inner_or_family, container, json_path)
    tmpl = props.get("filename_template", "{n}.png")
    return tmpl.replace("{n}", str(N)).replace("<n>", str(N)).replace("<# of shapes>", str(N))


# =====================
# Loop / runtime behavior
# =====================

LOOP_SLEEP_BETWEEN_RUNS: int = 2
LOOP_MAX_CONSECUTIVE_FAILURES: int = 30
LOOP_BASE_BACKOFF: float = 1.0
LOOP_MAX_BACKOFF: float = 60.0

LOOP_DEFAULT_ATTEMPTS: int = 5_000
LOOP_HIGH_N_THRESHOLD: int = 10
LOOP_HIGH_N_ATTEMPTS: int = 50_000
LOOP_STUCK_ATTEMPTS: int = 100_000

LOOP_STUCK_SWARM_COUNT: int = 20
LOOP_HARD_SWARM_COUNT: int = 15

LOOP_MIN_ATTEMPTS: int = 500
LOOP_MAX_ATTEMPTS: int = 200_000

# =====================
# Shape geometry
# =====================

# Regular polygon vertices on unit circle
def regular_polygon_vertices(n_sides: int, radius: float = 1.0) -> List[Tuple[float, float]]:
    return [
        (radius * math.cos(2 * math.pi * i / n_sides),
         radius * math.sin(2 * math.pi * i / n_sides))
        for i in range(n_sides)
    ]

# Circle as high-vertex polygon for solver
CIRCLE_APPROX_VERTICES = 64

def circle_vertices(radius: float = 1.0) -> List[Tuple[float, float]]:
    return regular_polygon_vertices(CIRCLE_APPROX_VERTICES, radius)

# L-shape
def l_shape_vertices(size: float = 1.0) -> List[Tuple[float, float]]:
    return [
        (0.0, 0.0),
        (size, 0.0),
        (size, size / 2),
        (size / 2, size / 2),
        (size / 2, size),
        (0.0, size),
    ]

# Tangram triangle
def tangram_triangle_vertices(size: float = 1.0) -> List[Tuple[float, float]]:
    s = size
    return [
        (0.0, 0.0),
        (s, 0.0),
        (0.0, s),
    ]

# Tangram parallelogram
def tangram_parallelogram_vertices(size: float = 1.0) -> List[Tuple[float, float]]:
    s = size
    return [
        (0.0, 0.0),
        (s, 0.0),
        (s + 0.5 * s, 0.5 * s),
        (0.5 * s, 0.5 * s),
    ]

# Trapezoid
def trapezoid_vertices(size: float = 1.0) -> List[Tuple[float, float]]:
    s = size
    return [
        (0.0, 0.0),
        (s, 0.0),
        (0.75 * s, 0.5 * s),
        (0.25 * s, 0.5 * s),
    ]

# =====================
# Problem metadata helpers
# =====================

def parse_problem(problem: str) -> Dict[str, Any]:
    """
    Parse problem string into:
      {
        'N': int,
        'inner': str,
        'container': str,
        'token': str
      }
    """
    token = problem.strip()
    parts = token.split("_in_")
    if len(parts) != 2:
        return {"N": 0, "inner": token, "container": "UNKNOWN", "token": token}
    left, container = parts
    n_str, inner = left.split("_", 1)
    N = int(n_str)
    return {"N": N, "inner": inner, "container": container, "token": token}

def shape_to_vertices(shape: str, size: float = 1.0) -> List[Tuple[float, float]]:
    """
    Convert a shape token (e.g. '3', '4', 'domino', 'CIRCLE')
    into vertices.
    """
    shape = shape.strip().upper()

    # Simple integer -> regular polygon
    if shape.isdigit():
        n = int(shape)
        return regular_polygon_vertices(n, size)

    # Circle
    if shape in ("CIRCLE", "C"):
        return circle_vertices(size)

    # Domino
    if shape == "DOMINO":
        return l_shape_vertices(size)

    # L
    if shape == "L":
        return l_shape_vertices(size)

    # Triangle
    if shape in ("TRI", "TRANGLE"):
        return tangram_triangle_vertices(size)

    # Parallelogram
    if shape in ("PAR", "PARALLELOGRAM"):
        return tangram_parallelogram_vertices(size)

    # Trapezoid
    if shape in ("TRA", "TRAPEZOID"):
        return trapezoid_vertices(size)

    # Default to polygon if numeric-ish
    try:
        n = int(shape)
        return regular_polygon_vertices(n, size)
    except ValueError:
        raise ValueError(f"Unknown shape: {shape}")

# =====================
# History-based stats
# =====================

_HISTORY_STATS_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _normalize_key(p_str: str) -> str:
    """Normalize problem token for robust key matching across case and shape synonyms."""
    s = str(p_str).strip().lower()
    replacements = {
        "pentagon": "5",
        "hexagon": "6",
        "triangle": "3",
        "square": "4",
        "octagon": "8",
        "cir": "circle",
        "circ": "circle",
        "dom": "domino",
    }
    # Split by delimiters while preserving tokens
    parts = re.split(r"(_|\s+)", s)
    norm_parts = [replacements.get(p, p) for p in parts]
    return "".join(norm_parts)


def load_all_problem_history_stats(
    history_path: str = "results.tsv",
) -> Dict[str, Dict[str, Any]]:
    """
    Parse results.tsv once and cache all per-problem stats in memory.
    Returns mapping from normalized problem key -> stats dictionary.
    """
    if not os.path.isfile(history_path):
        return {}

    abs_path = os.path.abspath(history_path)
    mtime = os.path.getmtime(abs_path)
    cache_key = f"{abs_path}:{mtime}"

    if cache_key in _HISTORY_STATS_CACHE:
        return _HISTORY_STATS_CACHE[cache_key]

    stats_by_key: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "total_runs": 0,
            "success_count": 0,
            "failure_count": 0,
            "best_score": None,
        }
    )

    with open(history_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        if not header:
            _HISTORY_STATS_CACHE[cache_key] = {}
            return {}

        prob_idx = None
        score_idx = None
        status_idx = None

        for i, col in enumerate(header):
            c = col.strip().lower()
            if c in ("problem",):
                prob_idx = i
            elif c in ("score", "final_metric"):
                score_idx = i
            elif c in ("status", "result"):
                status_idx = i

        if prob_idx is None:
            _HISTORY_STATS_CACHE[cache_key] = {}
            return {}

        for row in reader:
            if not row or prob_idx >= len(row):
                continue

            p = row[prob_idx].strip()
            norm_key = _normalize_key(p)
            entry = stats_by_key[norm_key]
            entry["total_runs"] += 1

            # Extract score
            score = None
            if score_idx is not None and score_idx < len(row):
                try:
                    score = float(row[score_idx])
                except ValueError:
                    score = None

            # Extract status
            status_text = ""
            if status_idx is not None and status_idx < len(row):
                status_text = row[status_idx].strip().lower()

            # Determine success/failure
            is_fail_keywords = any(
                kw in status_text
                for kw in ("fail", "error", "no solution", "no valid")
            )

            if score is not None and not is_fail_keywords:
                entry["success_count"] += 1
                if entry["best_score"] is None or score < entry["best_score"]:
                    entry["best_score"] = score
            else:
                entry["failure_count"] += 1

    result = dict(stats_by_key)
    _HISTORY_STATS_CACHE[cache_key] = result
    return result


def get_problem_history_stats(
    problem: str,
    history_path: str = "results.tsv",
    cache: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Compute history stats for a problem from results.tsv with in-memory caching.
    Returns:
        {
            "total_runs": int,
            "success_count": int,
            "failure_count": int,
            "best_score": float | None
        }
    """
    target_key = _normalize_key(problem)
    if cache is not None:
        if target_key in cache:
            return cache[target_key]
        if problem in cache:
            return cache[problem]

    all_stats = load_all_problem_history_stats(history_path)
    if target_key in all_stats:
        stats = dict(all_stats[target_key])
    else:
        stats = {
            "total_runs": 0,
            "success_count": 0,
            "failure_count": 0,
            "best_score": None,
        }

    if cache is not None:
        cache[problem] = stats

    return stats

# =====================
# Friedman reference cache
# =====================

_FRIEDMAN_BEST_CACHE: Dict[str, float] = {}
_FRIEDMAN_BEST_LOADED = False

def _load_friedman_verification_jsons():
    """
    Load all JSONs from packingVerification/ into _FRIEDMAN_BEST_CACHE.

    Two shapes are supported:

      1) List of objects:
          [
            {
              "problem": "1_CIRCLE_in_CIRCLE",
              "best_value": 1.234567
            },
            ...
          ]

      2) Dict keyed by problem token:
          {
            "1_CIRCLE_in_CIRCLE": 1.234567,
            "2_domino_in_5": { "best_score": 1.234567 }
          }

    Silently ignores unrecognized structures.
    """
    import json
    import os

    if not os.path.isdir(PACKING_VERIFICATION_DIR):
        return

    for fname in os.listdir(PACKING_VERIFICATION_DIR):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(PACKING_VERIFICATION_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            continue

        # Case 1: list of objects
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue

                # Use 'problem' if present
                prob = (entry.get("problem") or "").strip()

                # If not present, try reconstructing from fields
                if not prob:
                    N = entry.get("N")
                    inner = (entry.get("inner_shape") or "").strip().upper()
                    container = (entry.get("container_shape") or "").strip().upper()
                    if N is not None and inner and container:
                        prob = f"{int(N)}_{inner}_in_{container}"

                if not prob:
                    continue

                # Try to get score
                score = None
                bv = entry.get("best_value")
                if isinstance(bv, (int, float)):
                    score = float(bv)
                else:
                    # Some files use Friedman.best_score
                    fr = entry.get("Friedman")
                    if isinstance(fr, dict):
                        bs = fr.get("best_score")
                        if isinstance(bs, (int, float)):
                            score = float(bs)
                if score is not None:
                    _FRIEDMAN_BEST_CACHE[_normalize_key(prob)] = score

        # Case 2: dict keyed by problem token
        elif isinstance(data, dict):
            for token, value in data.items():
                prob = str(token).strip()
                if not prob:
                    continue

                score = None
                if isinstance(value, (int, float)):
                    score = float(value)
                elif isinstance(value, dict):
                    bs = value.get("best_score") or value.get("score")
                    if isinstance(bs, (int, float)):
                        score = float(bs)

                if score is not None:
                    _FRIEDMAN_BEST_CACHE[_normalize_key(prob)] = score

def get_friedman_best_for_problem(problem: str) -> float | None:
    """
    Return the Friedman best_score for a given problem from packingVerification JSONs.

    Uses an in-memory cache to avoid repeatedly loading files.
    Returns None if:
      - JSONs are unreadable / directory missing.
      - No match found.
    """
    global _FRIEDMAN_BEST_LOADED

    if not _FRIEDMAN_BEST_LOADED:
        _load_friedman_verification_jsons()
        _FRIEDMAN_BEST_LOADED = True

    return _FRIEDMAN_BEST_CACHE.get(_normalize_key(problem))

# =====================
# Difficulty scoring
# =====================

def _parse_problem_N(problem: str) -> int:
    """
    Parse N from a problem like '2_domino_in_5'.

    Returns the leading integer token before the first underscore;
    falls back to 1 if parsing fails.
    """
    try:
        n_str = problem.split("_")[0]
        return int(n_str)
    except (ValueError, IndexError):
        return 1

def compute_problem_difficulty_score(
    problem: str,
    stats: dict,
    friedman_best: float | None,
) -> float:
    """
    Compute a difficulty score in [0.0, 1.0] for a problem.

    Inputs:
      - problem: str (e.g. '2_domino_in_5')
      - stats: dict from get_problem_history_stats with:
          {total_runs, success_count, failure_count, best_score}
      - friedman_best: float | None (from get_friedman_best_for_problem)

    Formula (tunable):
      - Start at base 0.3.
      - +0.15 if N >= 10.
      - +0.10 if N >= 15 (on top of the 0.15).
      - +0.15 * min(1, failure_ratio / 0.5).
      - +0.15 * min(1, max(0, gap_ratio)) when Friedman gap is available.
      - Clamp to [0, 1].
    """
    N = _parse_problem_N(problem)

    total = stats.get("total_runs", 0) or 0
    failures = stats.get("failure_count", 0) or 0

    # Base difficulty
    score = 0.3

    # N-based difficulty
    if N >= 10:
        score += 0.15
    if N >= 15:
        score += 0.10

    # History-based failure ratio
    failure_ratio = failures / max(total, 1)
    score += 0.15 * min(1.0, failure_ratio / 0.5)

    # Factor in gap to Friedman's best, when available
    best_score = stats.get("best_score")
    gap_ratio = 0.0
    if friedman_best is not None and best_score is not None:
        gap = (best_score - friedman_best) / max(abs(friedman_best), 1e-9)
        gap_ratio = max(0.0, gap)
    score += 0.15 * min(1.0, gap_ratio)

    # Clamp to [0, 1]
    score = min(1.0, max(0.0, score))
    return score

# =====================
# Adaptive attempt scaling
# =====================

def compute_adaptive_attempts(
    difficulty: float,
    status: str = "normal",
    min_attempts: int = None,
    max_attempts: int = None,
) -> int:
    """
    Map a difficulty score in [0, 1] to a smooth, monotonic range of solver attempts.

    Uses four difficulty bands with linear interpolation within each band:

      [0.0, 0.2]   -> [min_attempts, LOOP_DEFAULT_ATTEMPTS]
      (0.2, 0.5]   -> [LOOP_DEFAULT_ATTEMPTS, LOOP_HIGH_N_ATTEMPTS]
      (0.5, 0.8]   -> [LOOP_HIGH_N_ATTEMPTS, max_attempts * 0.7]
      (0.8, 1.0]   -> [max_attempts * 0.7, max_attempts]

    For status in {"stuck", "hard"}, difficulty is biased upward (multiplied
    by 1.2 then clamped to 1.0) before interpolation, so those problems
    consistently get more attempts than "normal" at the same base difficulty.

    Parameters
    ----------
    difficulty : float
        Difficulty score in [0, 1] (e.g. from compute_problem_difficulty_score).
    status : str
        One of "normal", "stuck", or "hard".
    min_attempts : int | None
        Lower bound; defaults to 500 if None.
    max_attempts : int | None
        Upper bound; defaults to 200_000 if None.

    Returns
    -------
    int
        Number of attempts, guaranteed in [min_attempts, max_attempts]
        and monotonic with respect to difficulty.
    """

    if min_attempts is None:
        min_attempts = 500
    if max_attempts is None:
        max_attempts = 200_000

    # Clamp difficulty
    difficulty = max(0.0, min(1.0, float(difficulty)))

    # Bias for stuck/hard problems
    if status in ("stuck", "hard"):
        difficulty = min(1.0, difficulty * 1.2)

    # Compute attempts using bands
    high_mid = max_attempts * 0.7

    if difficulty <= 0.2:
        # [0.0, 0.2] -> [min_attempts, LOOP_DEFAULT_ATTEMPTS]
        t = difficulty / 0.2
        attempts = min_attempts + t * (LOOP_DEFAULT_ATTEMPTS - min_attempts)
    elif difficulty <= 0.5:
        # (0.2, 0.5] -> [LOOP_DEFAULT_ATTEMPTS, LOOP_HIGH_N_ATTEMPTS]
        t = (difficulty - 0.2) / 0.3
        attempts = LOOP_DEFAULT_ATTEMPTS + t * (LOOP_HIGH_N_ATTEMPTS - LOOP_DEFAULT_ATTEMPTS)
    elif difficulty <= 0.8:
        # (0.5, 0.8] -> [LOOP_HIGH_N_ATTEMPTS, max_attempts * 0.7]
        t = (difficulty - 0.5) / 0.3
        attempts = LOOP_HIGH_N_ATTEMPTS + t * (high_mid - LOOP_HIGH_N_ATTEMPTS)
    else:
        # (0.8, 1.0] -> [max_attempts * 0.7, max_attempts]
        t = (difficulty - 0.8) / 0.2
        attempts = high_mid + t * (max_attempts - high_mid)

    # Ensure within bounds
    attempts = int(max(min_attempts, min(max_attempts, round(attempts))))
    return attempts

# =====================
# Queue / priority / misc
# =====================

CIRCLE_SIDES = 32

MIN_VALID_CIRCLE_SCORE = 0.1

QUEUE_FALLBACK_PROBLEM = "8_3_in_5"

QUEUE_RECENT_WINDOW = 10

QUEUE_PROBLEM_CAP1 = 60
QUEUE_PROBLEM_CAP2 = 100
QUEUE_FAMILY_CAP1 = 400
QUEUE_FAMILY_CAP2 = 800

PRIORITY_QUEUE_PATH = "priority_queue.json"
RESULTS_TSV_PATH = "results.tsv"

# =====================
# Shape metadata & Families
# =====================

SHAPE_TO_SIDES = {
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "8": 8,
    "CIRCLE": CIRCLE_SIDES,
    "SQUARE": 4,
    "TRIANGLE": 3,
    "PENTAGON": 5,
    "HEXAGON": 6,
    "HEPTAGON": 7,
    "OCTAGON": 8,
    "ENNEAGON": 9,
    "DECAGON": 10,
}

SPECIAL_SHAPES = {
    "TAN",
    "DOMINO",
    "L",
}

CIRCLE_FAMILIES = [
    "Circles in Circles", "Triangles in Circles", "Squares in Circles",
    "Pentagons in Circles", "Hexagons in Circles", "Octagons in Circles",
    "Tans in Circles", "Dominoes in Circles", "L's in Circles",
]

TRIANGLE_FAMILIES = [
    "Circles in Triangles", "Triangles in Triangles", "Squares in Triangles",
    "Pentagons in Triangles", "Hexagons in Triangles", "Octagons in Triangles",
    "Tans in Triangles", "Dominoes in Triangles", "L's in Triangles",
]

SQUARE_FAMILIES = [
    "Circles in Squares", "Triangles in Squares", "Squares in Squares",
    "Pentagons in Squares", "Hexagons in Squares", "Octagons in Squares",
    "Tans in Squares", "Dominoes in Squares", "L's in Squares",
]

PENTAGON_FAMILIES = [
    "Circles in Pentagons", "Triangles in Pentagons", "Squares in Pentagons",
    "Pentagons in Pentagons", "Hexagons in Pentagons", "Octagons in Pentagons",
    "Tans in Pentagons", "Dominoes in Pentagons", "L's in Pentagons",
]

HEXAGON_FAMILIES = [
    "Circles in Hexagons", "Triangles in Hexagons", "Squares in Hexagons",
    "Pentagons in Hexagons", "Hexagons in Hexagons", "Octagons in Hexagons",
    "Tans in Hexagons", "Dominoes in Hexagons", "L's in Hexagons",
]

OCTAGON_FAMILIES = [
    "Circles in Octagons", "Triangles in Octagons", "Squares in Octagons",
    "Pentagons in Octagons", "Hexagons in Octagons", "Octagons in Octagons",
    "Tans in Octagons", "Dominoes in Octagons", "L's in Octagons",
]

TAN_FAMILIES = [
    "Circles in Tans", "Triangles in Tans", "Squares in Tans",
    "Pentagons in Tans", "Hexagons in Tans", "Octagons in Tans",
    "Tans in Tans", "Dominoes in Tans", "L's in Tans",
]

DOMINO_FAMILIES = [
    "Circles in Dominoes", "Triangles in Dominoes", "Squares in Dominoes",
    "Pentagons in Dominoes", "Hexagons in Dominoes", "Octagons in Dominoes",
    "Tans in Dominoes", "Dominoes in Dominoes", "L's in Dominoes",
]

L_FAMILIES = [
    "Circles in L's", "Triangles in L's", "Squares in L's",
    "Pentagons in L's", "Hexagons in L's", "Octagons in L's",
    "Tans in L's", "Dominoes in L's", "L's in L's",
]

ALL_FAMILIES = (
    CIRCLE_FAMILIES
    + TRIANGLE_FAMILIES
    + SQUARE_FAMILIES
    + PENTAGON_FAMILIES
    + HEXAGON_FAMILIES
    + OCTAGON_FAMILIES
    + TAN_FAMILIES
    + DOMINO_FAMILIES
    + L_FAMILIES
)

DEFAULT_EXPERIMENT_KWARGS = {
    "attempts": 1000,
    "tolerance": 1e-8,
    "finalstep": 0.0001,
}

# =====================
# Geometry tolerances
# =====================

GEOMETRY_SAT_TOLERANCE = 1e-12
ANALYSIS_PLOT_DPI = 200
