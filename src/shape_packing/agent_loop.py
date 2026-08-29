"""
AgentLoopModule: deep module for the experiment loop.

Responsibilities:
- Load/append results.tsv
- Choose next problem (reference-aware + diversity)
- Detect stuck / need radical switch
- Decide keep vs discard vs crash

This is the canonical implementation of the loop policies
described (at a high level) in program.md.

Usage examples:

    from agent_loop import (
        load_history,
        choose_problem,
        is_stuck,
        should_switch_radically,
        log_result,
        current_best_scores,
        ExperimentResult,
    )

    history = load_history()
    best = current_best_scores(history)

    # Example loop (pseudo-code)
    current = choose_problem(history)
    while True:
        score, seconds, desc = run_experiment(current)  # implemented externally
        status = log_result(
            history,
            problem=current,
            score=score,
            seconds=seconds,
            description=desc,
            commit="HEAD",
            memory_gb=0.0,
        )

        # Optionally check stuck / radical switch next iteration.
        if is_stuck(history, current):
            current = choose_problem(history, prefer_different=True)
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from collections import Counter
from typing import List, Dict, Optional, Tuple, Any


from .packing_config import (
    CIRCLE_SIDES,
    MIN_VALID_CIRCLE_SCORE,
    QUEUE_FALLBACK_PROBLEM,
    QUEUE_RECENT_WINDOW,
    QUEUE_PROBLEM_CAP1,
    QUEUE_PROBLEM_CAP2,
    QUEUE_FAMILY_CAP1,
    QUEUE_FAMILY_CAP2,
    PRIORITY_QUEUE_PATH,
    RESULTS_TSV_PATH,
    PACKING_VERIFICATION_DIR,
)


# --------------- Data types ---------------


@dataclass
class ExperimentResult:
    problem: str
    score: float  # 0.0 if crash
    status: str  # "keep" | "discard" | "crash"
    description: str
    seconds: float
    commit: str
    memory_gb: float


TSV_COLUMNS = ["commit", "score", "memory_gb", "status", "problem", "description"]


# --------------- History I/O ---------------


def load_history(path: str = "results.tsv") -> List[ExperimentResult]:
    """
    Load results.tsv into a list of ExperimentResult.
    Skips malformed rows.
    """
    if not os.path.exists(path):
        return []

    rows: List[ExperimentResult] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                try:
                    r = ExperimentResult(
                        problem=row.get("problem", ""),
                        score=float(row.get("score", 0) or 0),
                        status=row.get("status", "discard"),
                        description=row.get("description", ""),
                        seconds=float(row.get("seconds", 0) or 0),
                        commit=row.get("commit", ""),
                        memory_gb=float(row.get("memory_gb", 0) or 0),
                    )
                    rows.append(r)
                except Exception:
                    # skip malformed
                    pass
    except Exception:
        return []
    return rows


def append_result(path: str, result: ExperimentResult) -> None:
    """
    Append a single ExperimentResult to results.tsv.
    Creates file with header if it does not exist.
    """
    write_header = not (os.path.exists(path) and os.path.getsize(path) > 0)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_COLUMNS, delimiter="\t")
        if write_header:
            writer.writeheader()

        writer.writerow({
            "commit": result.commit,
            "score": result.score,
            "memory_gb": result.memory_gb,
            "status": result.status,
            "problem": result.problem,
            "description": result.description,
        })


# --------------- Reference utilities ---------------


def load_packing_reference(verif_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load all verified JSON datasets in packingVerification as list of dicts.
    Fields per entry:
      id, problem_family, N, inner_shape, container_shape,
      best_value (float|null), status, source_url, source_note, our_problem.
    """
    import glob
    rows = []
    if verif_dir is None:
        verif_dir = PACKING_VERIFICATION_DIR
        if not os.path.exists(verif_dir):
            if os.path.exists(os.path.join("data", "packingVerification")):
                verif_dir = os.path.join("data", "packingVerification")
            elif os.path.exists("packingVerification"):
                verif_dir = "packingVerification"
    if not os.path.exists(verif_dir):
        return rows
        
    json_files = glob.glob(os.path.join(verif_dir, "*.json"))
    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                rows.extend(data)
        except Exception:
            pass
    return rows


def is_reference_blocked(
    reference_rows: List[Dict[str, any]],
    problem: str,
) -> bool:
    """
    Decide if a problem is blocked by reference metadata.

    Blocked if status in ('trivial', 'proved_optimal') and our_problem matches.
    """
    for row in reference_rows:
        our = row.get("our_problem")
        if not our or str(our).strip() != problem:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in ("trivial", "proved_optimal"):
            return True
    return False


def is_preferred_reference(
    reference_rows: List[Dict[str, any]],
    problem: str,
) -> bool:
    """
    Soft signal: problem is aligned with 'best_known' or human-found source.
    Uses status and source_note from PACKING_REFERENCE.json.
    """
    for row in reference_rows:
        our = row.get("our_problem")
        if not our or str(our).strip() != problem:
            continue
        status = str(row.get("status") or "").strip().lower()
        note = str(row.get("source_note") or "").strip().lower()
        if status == "best_known":
            return True
        if "found by" in note or "erich friedman" in note:
            return True
    return False


# --------------- Analysis utilities ---------------


import math

def _get_inner_shape_area(inner_token: str) -> Optional[float]:
    t = str(inner_token).upper()
    if t in ("3", "TRIANGLE", "TRI"):
        return math.sqrt(3) / 4.0
    if t in ("4", "SQUARE", "SQU"):
        return 1.0
    if t in ("5", "PENTAGON", "PEN"):
        return 0.25 * math.sqrt(5.0 * (5.0 + 2.0 * math.sqrt(5.0)))
    if t in ("6", "HEXAGON", "HEX"):
        return 1.5 * math.sqrt(3)
    if t in ("8", "OCTAGON", "OCT"):
        return 2.0 * (1.0 + math.sqrt(2.0))
    if t in ("TAN", "TANGRAM"):
        return 0.5
    if t in ("L", "LTROMINO", "L-TROMINO"):
        return 3.0
    return None


def _get_container_shape_area(s: float, container_token: str) -> Optional[float]:
    t = str(container_token).upper()
    if t in ("CIRCLE", "CIR", "0"):
        return math.pi * (s ** 2)
    if t in ("3", "TRIANGLE", "TRI"):
        return (math.sqrt(3) / 4.0) * (s ** 2)
    if t in ("4", "SQUARE", "SQU"):
        return s ** 2
    if t in ("5", "PENTAGON", "PEN"):
        return (5.0 / 4.0) * (s ** 2) / math.tan(math.pi / 5.0)
    if t in ("6", "HEXAGON", "HEX"):
        return 1.5 * math.sqrt(3) * (s ** 2)
    if t in ("8", "OCTAGON", "OCT"):
        return 2.0 * (1.0 + math.sqrt(2.0)) * (s ** 2)
    if t in ("TAN", "TANGRAM"):
        return 0.5 * (s ** 2)
    if t in ("DOMINO", "DOM"):
        return 2.0 * (s ** 2)
    if t in ("L", "LTROMINO", "L-TROMINO"):
        return 3.0 * (s ** 2)
    return None


def is_physically_valid_score(problem: str, score: float) -> bool:
    if score <= 0:
        return False
    parts = str(problem).split("_")
    if len(parts) == 4 and parts[2] == "in":
        container = parts[3].upper()
        if container in ("CIRCLE", "CIR", "0") and score < MIN_VALID_CIRCLE_SCORE:
            return False
    return True


def current_best_scores(history: List[ExperimentResult]) -> Dict[str, float]:
    """
    For each problem, return the best (lowest) valid score we have achieved.
    """
    best: Dict[str, float] = {}
    for r in history:
        if not is_physically_valid_score(r.problem, r.score):
            continue
        p = r.problem
        if p not in best or r.score < best[p]:
            best[p] = r.score
    return best


def extract_problem_family(problem: str) -> str:
    """
    Given problem like '12_5_in_8', return family like '5_in_8'.
    If not parseable, return the whole name.
    """
    try:
        parts = problem.split("_")
        if len(parts) >= 3:
            # skip N (first token)
            return "_".join(parts[1:])
        return problem
    except Exception:
        return problem


def recent_problems(history: List[ExperimentResult], last: int = 10) -> List[str]:
    """
    Return list of problems from the last `last` experiments.
    """
    tail = history[-last:] if len(history) >= last else history
    return [r.problem for r in tail]


def last_experiments_for(history: List[ExperimentResult], problem: str, last: int = 5) -> List[ExperimentResult]:
    """
    Last N experiments for a given problem.
    """
    out: List[ExperimentResult] = []
    for r in history:
        if r.problem != problem:
            continue
        out.append(r)
    return out[-last:] if len(out) >= last else out


def has_improved(window: List[ExperimentResult]) -> bool:
    """
    Check if there was any strict improvement (lower score) in this window.
    """
    if not window:
        return False
    best = min(r.score for r in window if r.score > 0)
    # Compare last to best; if last is worse, and all intermediate are same as last -> no improvement.
    # Simpler: if scores are strictly non-increasing with no drop, consider no improvement.
    # For now, check if last score is strictly less than first in window.
    if len(window) < 2:
        return False
    first = next((r.score for r in window if r.score > 0), 0)
    last = next((r.score for r in reversed(window) if r.score > 0), 0)
    return last < first


# --------------- Loop policies ---------------


import re

_NORM_FULL_RE = re.compile(r"^(\d+)_(.+)_(in)_(.+)$")
_NORM_COMPACT_RE = re.compile(r"^(\d+)_([a-zA-Z]+)in([a-zA-Z]+)$")


def normalize_problem_name(p_str: str) -> str:
    if _NORM_FULL_RE.match(p_str):
        return p_str
    m = _NORM_COMPACT_RE.match(p_str)
    if m:
        N = m.group(1)
        inner = m.group(2).lower()
        container = m.group(3).lower()
        token_map = {
            "squ": "4", "cir": "CIRCLE", "tri": "3", "pen": "5",
            "hex": "6", "oct": "8", "l": "L", "tan": "TAN", "dom": "DOMINO"
        }
        c_inner = token_map.get(inner, inner.upper())
        c_container = token_map.get(container, container.upper())
        return f"{N}_{c_inner}_in_{c_container}"
    return p_str

@dataclass
class ProblemSelectionConfig:
    """Configuration options for choosing the next problem from priority queue."""
    queue_path: str = PRIORITY_QUEUE_PATH
    prefer_different: bool = False
    filters: Optional[dict] = None
    exclude_problems: Optional[set] = None
    problem_cap1: int = QUEUE_PROBLEM_CAP1
    problem_cap2: int = QUEUE_PROBLEM_CAP2
    family_cap1: int = QUEUE_FAMILY_CAP1
    family_cap2: int = QUEUE_FAMILY_CAP2


def load_priority_queue(path: str = "priority_queue.json") -> List[Dict[str, float]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _is_shape_unsupported(token: str, filters: dict) -> bool:
    from .problems import is_special_shape
    t = str(token).upper().replace(" (COVERING)", "")
    if t == "CIR":
        t = "CIRCLE"
    if t == "DOM":
        t = "DOMINO"
    if t in ("TAN", "TANGRAM"):
        t = "TAN"
    if t in ("L", "LTROMINO", "L-TROMINO"):
        t = "L"

    if is_special_shape(t):
        if t in ("DOMINO", "TAN", "L"):
            return False
        if (filters or {}).get("include_inner") or (filters or {}).get("include_container"):
            return False
        return True
    allowed = {
        "3", "4", "5", "6", "7", "8", "9", "10",
        "CIRCLE", "SQUARE", "DOMINO", "TAN", "L", "TRIANGLE", "PENTAGON", "HEXAGON", "OCTAGON",
    }
    return t not in allowed


def _parse_filter_sets(filters: Optional[dict]) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    if not filters:
        return set(), set(), set(), set()

    def _to_set(v) -> Set[str]:
        if isinstance(v, str):
            raw = [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            raw = [str(x).strip() for x in v]
        else:
            raw = [str(v)]
        res = set(t.upper() for t in raw)
        if "CIRCLE" in res or "CIR" in res:
            res.add("CIRCLE")
            res.add("CIR")
        if "3" in res or "TRIANGLE" in res:
            res.add("3")
            res.add("TRIANGLE")
        if "TAN" in res or "TANGRAM" in res:
            res.add("TAN")
            res.add("TANGRAM")
        if "L" in res or "LTROMINO" in res or "L-TROMINO" in res:
            res.add("L")
            res.add("LTROMINO")
            res.add("L-TROMINO")
        return res

    inc_inner = _to_set(filters["include_inner"]) if filters.get("include_inner") else set()
    exc_inner = _to_set(filters["exclude_inner"]) if filters.get("exclude_inner") else set()
    inc_cont = _to_set(filters["include_container"]) if filters.get("include_container") else set()
    exc_cont = _to_set(filters["exclude_container"]) if filters.get("exclude_container") else set()

    return inc_inner, exc_inner, inc_cont, exc_cont


def _matches_external_filters(
    p0: Any,
    item: Dict[str, Any],
    filters: dict,
    inc_inner: Set[str],
    exc_inner: Set[str],
    inc_cont: Set[str],
    exc_cont: Set[str],
) -> bool:
    from .problems import shape_token_to_sides

    try:
        inner_token = p0.inner_token.upper()
        container_token = p0.container_token.upper()
        n = p0.N

        if inner_token == "CIR": inner_token = "CIRCLE"
        if container_token == "CIR": container_token = "CIRCLE"
        if container_token == "TRIANGLE": container_token = "3"
        if inner_token == "TRIANGLE": inner_token = "3"

        p0_inner = p0.inner_token.upper()
        p0_cont = p0.container_token.upper()
        if p0_inner == "CIR": p0_inner = "CIRCLE"
        if p0_cont == "CIR": p0_cont = "CIRCLE"
        if p0_cont == "TRIANGLE": p0_cont = "3"
        if p0_inner == "TRIANGLE": p0_inner = "3"

        inner_sides = shape_token_to_sides(inner_token)
        container_sides = shape_token_to_sides(container_token)

        if filters.get("min_n") is not None and n < filters["min_n"]:
            return False
        if filters.get("max_n") is not None and n > filters["max_n"]:
            return False
        if filters.get("equal_n") is not None and n != filters["equal_n"]:
            return False

        item_inner = str(item.get("inner_shape", "")).upper()
        item_container = str(item.get("container_shape", "")).upper().replace(" (COVERING)", "")

        if item_inner == "CIR": item_inner = "CIRCLE"
        if item_container == "CIR": item_container = "CIRCLE"
        if item_container == "3": item_container = "TRIANGLE"
        if item_inner == "3": item_inner = "TRIANGLE"
        if item_container == "TRIANGLE": item_container = "3"
        if item_inner == "TRIANGLE": item_inner = "3"

        if inc_inner and (inner_token not in inc_inner and p0_inner not in inc_inner and item_inner not in inc_inner):
            return False
        if exc_inner and (inner_token in exc_inner or p0_inner in exc_inner or item_inner in exc_inner):
            return False

        if inc_cont and (container_token not in inc_cont and p0_cont not in inc_cont and item_container not in inc_cont):
            return False
        if exc_cont and (container_token in exc_cont or p0_cont in exc_cont or item_container in exc_cont):
            return False

        if inner_token == "CIRCLE":
            inner_sides = CIRCLE_SIDES
        if container_token == "CIRCLE":
            container_sides = CIRCLE_SIDES

        if inner_sides is not None:
            if filters.get("min_inner_sides") is not None and inner_sides < filters["min_inner_sides"]:
                return False
            if filters.get("max_inner_sides") is not None and inner_sides > filters["max_inner_sides"]:
                return False
        if container_sides is not None:
            if filters.get("min_container_sides") is not None and container_sides < filters["min_container_sides"]:
                return False
            if filters.get("max_container_sides") is not None and container_sides > filters["max_container_sides"]:
                return False

        return True
    except Exception:
        return False


def _calculate_candidate_score(
    item: Dict[str, Any],
    p_str: str,
    base_density: float,
    recent_counts: Counter,
    our_best: Dict[str, float],
    problem_runs: Dict[str, int],
    family_runs: Dict[str, int],
    problem_last_k: Dict[str, List[float]],
    config: ProblemSelectionConfig,
) -> Optional[float]:
    ref_status = str(item.get("status") or "").strip().lower()

    if ref_status in ("trivial", "proved_optimal"):
        return None

    best_value = item.get("best_value")
    try:
        best_value = float(best_value) if best_value is not None else None
    except ValueError:
        best_value = None

    stagnation = recent_counts.get(p_str, 0)
    penalty = stagnation * 0.05

    total_runs = problem_runs.get(p_str, 0)
    penalty += total_runs * 0.01

    if total_runs > config.problem_cap1:
        penalty += 5.0
    if total_runs > config.problem_cap2:
        penalty += 15.0

    family = extract_problem_family(p_str)
    fam_runs = family_runs.get(family, 0)
    if fam_runs > config.family_cap1:
        penalty += 5.0
    if fam_runs > config.family_cap2:
        penalty += 15.0

    if total_runs == 0:
        penalty -= 3.0
    elif total_runs <= 5:
        penalty -= 1.5

    if is_stuck(problem_last_k, p_str, threshold_no_improve=5):
        penalty += 10.0

    our = our_best.get(p_str, float("inf"))
    if best_value is not None and our != float("inf"):
        rel_gap = (our - best_value) / best_value if best_value > 0 else 0.0
        if rel_gap < 0.002:
            penalty += 5.0
        if rel_gap > 0.10 and total_runs < 30:
            penalty -= 0.3

    if ref_status == "best_known":
        penalty -= 0.5
    else:
        source_note = (item.get("source_note") or "").strip().lower()
        if "found by" in source_note or "erich friedman" in source_note:
            penalty -= 0.3

    if config.prefer_different and p_str in recent_counts:
        penalty += 3.0

    return base_density + penalty


def choose_problem(
    history: List[ExperimentResult],
    config: Optional[ProblemSelectionConfig] = None,
    queue_path: str = PRIORITY_QUEUE_PATH,
    prefer_different: bool = False,
    filters: Optional[dict] = None,
    exclude_problems: Optional[set] = None,
    problem_cap1: int = QUEUE_PROBLEM_CAP1,
    problem_cap2: int = QUEUE_PROBLEM_CAP2,
    family_cap1: int = QUEUE_FAMILY_CAP1,
    family_cap2: int = QUEUE_FAMILY_CAP2,
) -> str:
    if config is None:
        config = ProblemSelectionConfig(
            queue_path=queue_path,
            prefer_different=prefer_different,
            filters=filters,
            exclude_problems=exclude_problems,
            problem_cap1=problem_cap1,
            problem_cap2=problem_cap2,
            family_cap1=family_cap1,
            family_cap2=family_cap2,
        )

    queue = load_priority_queue(config.queue_path)
    if not queue:
        return QUEUE_FALLBACK_PROBLEM

    recent = recent_problems(history, last=QUEUE_RECENT_WINDOW)
    recent_counts = Counter(normalize_problem_name(r) for r in recent)
    our_best = current_best_scores(history)
    problem_runs, family_runs, problem_last_k = _build_problem_stats(history)

    from .problems import parse_problem

    inc_inner, exc_inner, inc_cont, exc_cont = _parse_filter_sets(config.filters)
    scored_candidates = []

    for item in queue:
        raw_p_str = item["problem"]
        p_str = normalize_problem_name(raw_p_str)
        base_density = item["density"]

        if config.exclude_problems and p_str in config.exclude_problems:
            continue

        try:
            p0 = parse_problem(p_str)
        except Exception:
            continue

        if _is_shape_unsupported(item.get("inner_shape", ""), config.filters or {}):
            continue
        if _is_shape_unsupported(item.get("container_shape", ""), config.filters or {}):
            continue

        if config.filters and not _matches_external_filters(
            p0, item, config.filters, inc_inner, exc_inner, inc_cont, exc_cont
        ):
            continue

        score = _calculate_candidate_score(
            item,
            p_str,
            base_density,
            recent_counts,
            our_best,
            problem_runs,
            family_runs,
            problem_last_k,
            config,
        )
        if score is not None:
            scored_candidates.append((p_str, score))

    if not scored_candidates:
        import sys
        print("No candidates matched filters!", file=sys.stderr)
        return QUEUE_FALLBACK_PROBLEM

    scored_candidates.sort(key=lambda x: x[1])
    return scored_candidates[0][0]


def _build_problem_stats(
    history: List[ExperimentResult],
    k: int = 10,
):
    """
    Precompute per-problem stats for fast choose_problem / is_stuck:
    - problem_runs[p] = total count
    - family_runs[family] = total count
    - problem_last_k[p] = last-k ExperimentResults for that problem
    """
    problem_runs: Dict[str, int] = {}
    family_runs: Dict[str, int] = {}
    problem_last_k: Dict[str, List[ExperimentResult]] = {}

    for r in history:
        hp = normalize_problem_name(r.problem)
        problem_runs[hp] = problem_runs.get(hp, 0) + 1
        hf = extract_problem_family(hp)
        family_runs[hf] = family_runs.get(hf, 0) + 1

        lst = problem_last_k.setdefault(hp, [])
        if len(lst) < k:
            lst.append(r)
        else:
            lst.pop(0)
            lst.append(r)

    return problem_runs, family_runs, problem_last_k


def is_stuck(
    history_or_stats,
    problem: str,
    threshold_no_improve: int = 5,
) -> bool:
    """
    Check if problem is stuck.

    Can be called two ways:
      - is_stuck(problem_last_k_dict, problem)
      - is_stuck(history_list, problem)  (for backward compatibility in tests)
    """
    if isinstance(history_or_stats, dict):
        # new style: problem_last_k dict
        window = history_or_stats.get(problem)
        if not window:
            return False
    else:
        # fallback: raw history list (backward compat)
        window = last_experiments_for(history_or_stats, problem, last=10)
        if len(window) < threshold_no_improve:
            return False

    if len(window) < threshold_no_improve:
        return False
        return False

    # All must be non-crash.
    if any(r.status == "crash" for r in window):
        return False

    # Check no strict improvement.
    if has_improved(window):
        return False

    return True


def should_switch_radically(
    total_experiments: int,
    last_n: int = 30,
    no_improve_threshold: int = 7,
) -> bool:
    """
    Signal that it is time to try something more radical:
    - Every ~20-30 total experiments.
    - Or if we see many recent non-improvements.

    This is a simple, global heuristic, not problem-specific.
    """
    if total_experiments <= 0:
        return False

    # Periodic radical switch.
    if 20 <= total_experiments <= 30 and total_experiments % 10 in (0, 1):
        return True
    if total_experiments > 30 and total_experiments % 30 in (0, 1, 2):
        return True

    return False


# --------------- Logging / decision ---------------


@dataclass
class ExperimentLogContext:
    """Context information for logging an experiment result to results.tsv."""
    problem: str
    score: float
    seconds: float = 0.0
    description: str = ""
    commit: str = "HEAD"
    memory_gb: float = 0.0
    path: str = RESULTS_TSV_PATH
    history: Optional[List[ExperimentResult]] = None


def log_result(
    history: Optional[List[ExperimentResult]] = None,
    problem: Optional[str] = None,
    score: Optional[float] = None,
    seconds: float = 0.0,
    description: str = "",
    commit: str = "HEAD",
    memory_gb: float = 0.0,
    path: str = RESULTS_TSV_PATH,
    context: Optional[ExperimentLogContext] = None,
) -> str:
    """
    Log result to results.tsv and decide status:
    - "keep"     if improved best for that problem
    - "discard"  if no improvement
    - "crash"    if score <= 0 or missing

    Accepts either a structured ExperimentLogContext object or individual keyword arguments.
    """
    if context is None:
        if problem is None or score is None:
            raise ValueError("Must provide either an ExperimentLogContext object or problem and score arguments.")
        context = ExperimentLogContext(
            history=history,
            problem=problem,
            score=score,
            seconds=seconds,
            description=description,
            commit=commit,
            memory_gb=memory_gb,
            path=path,
        )

    hist = context.history
    if hist is None:
        hist = load_history(context.path)

    best = current_best_scores(hist)
    current_best = best.get(context.problem, float("inf"))

    log_score = context.score
    if log_score is None or log_score <= 0:
        status = "crash"
        log_score = 0.0
    elif log_score < current_best:
        status = "keep"
    else:
        status = "discard"

    result = ExperimentResult(
        problem=context.problem,
        score=log_score,
        status=status,
        description=context.description or "",
        seconds=context.seconds,
        commit=context.commit,
        memory_gb=context.memory_gb,
    )

    append_result(context.path, result)
    return status


# --------------- Convenience: run-loop skeleton ---------------
# Not used by default; for reference and future automation.


def make_loop_candidate(
    history: Optional[List[ExperimentResult]] = None,
    current: Optional[str] = None,
    experiments_count: int = 0,
) -> Tuple[str, bool]:
    """
    Given current context, suggest:
    - which problem to run next
    - whether to be radical

    Returns (problem, be_radical).
    """
    if history is None:
        history = load_history()

    total = len(history) + experiments_count
    radically = should_switch_radically(total)

    problem_last_k = _build_problem_stats(history)[2]

    if current and radically:
        # If radical time, force diversity.
        problem = choose_problem(history, prefer_different=True)
    elif is_stuck(problem_last_k, current or ""):
        problem = choose_problem(history, prefer_different=True)
    else:
        # Optionally switch even if not stuck for diversity.
        problem = choose_problem(history) or (current or "8_3_in_5")

    return problem, radically


# End of agent_loop.py