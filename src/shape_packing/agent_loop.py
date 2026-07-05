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
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple


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


def load_packing_reference(path: str = "PACKING_REFERENCE.tsv") -> List[Dict[str, str]]:
    """
    Load PACKING_REFERENCE.tsv as list of dicts.
    Fields: problem_family, n, best_value, source, status, our_problem.
    """
    if not os.path.exists(path):
        return []

    rows: List[Dict[str, str]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                rows.append(row)
    except Exception:
        return []
    return rows


def is_reference_blocked(
    reference_rows: List[Dict[str, str]],
    problem: str,
) -> bool:
    """
    Decide if a problem is blocked by reference metadata.

    Blocked if:
    - status == "trivial"
    - status == "proved_optimal"

    In the future, we can map our internal problem name to the reference
    via problem_family/n/etc. For now, if 'our_problem' in row matches
    the problem, we use its status.
    """
    for row in reference_rows:
        our = row.get("our_problem", "").strip()
        if not our:
            continue
        if our == problem:
            status = (row.get("status") or "").strip().lower()
            if status in ("trivial", "proved_optimal"):
                return True
    return False


def is_preferred_reference(
    reference_rows: List[Dict[str, str]],
    problem: str,
) -> bool:
    """
    Soft signal: problem is aligned with 'best_known' or human-found source.
    """
    for row in reference_rows:
        our = row.get("our_problem", "").strip()
        if our == problem:
            status = (row.get("status") or "").strip().lower()
            source = (row.get("source") or "").strip().lower()
            if status == "best_known":
                return True
            if "found by" in source:
                return True
    return False


# --------------- Analysis utilities ---------------


def current_best_scores(history: List[ExperimentResult]) -> Dict[str, float]:
    """
    For each problem, return the best (lowest) score we have achieved.
    """
    best: Dict[str, float] = {}
    for r in history:
        if r.score <= 0:
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


def load_priority_queue(path: str = "priority_queue.json") -> List[Dict[str, float]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def choose_problem(
    history: List[ExperimentResult],
    queue_path: str = "priority_queue.json",
    prefer_different: bool = False,
    filters: dict = None
) -> str:
    queue = load_priority_queue(queue_path)
    if not queue:
        # Fallback if queue missing
        return "8_3_in_5"
        
    recent = recent_problems(history, last=10)
    best = current_best_scores(history)
    
    scored_candidates = []
    
    from .problems import parse_problem, shape_token_to_sides
    
    for item in queue:
        p_str = item["problem"]
        base_density = item["density"]
        
        # Apply filters
        if filters:
            try:
                p_obj = parse_problem(p_str)
                n = p_obj.N
                inner_token = p_obj.inner_token
                container_token = p_obj.container_token
                inner_sides = shape_token_to_sides(inner_token)
                container_sides = shape_token_to_sides(container_token)
                
                if filters.get("min_n") is not None and n < filters["min_n"]:
                    continue
                if filters.get("max_n") is not None and n > filters["max_n"]:
                    continue
                if filters.get("equal_n") is not None and n != filters["equal_n"]:
                    continue
                    
                if filters.get("include_inner"):
                    if inner_token not in filters["include_inner"]:
                        continue
                if filters.get("exclude_inner"):
                    if inner_token in filters["exclude_inner"]:
                        continue
                        
                if filters.get("include_container"):
                    if container_token not in filters["include_container"]:
                        continue
                if filters.get("exclude_container"):
                    if container_token in filters["exclude_container"]:
                        continue
                        
                if filters.get("min_inner_sides") is not None and inner_sides < filters["min_inner_sides"]:
                    continue
                if filters.get("max_inner_sides") is not None and inner_sides > filters["max_inner_sides"]:
                    continue
                if filters.get("min_container_sides") is not None and container_sides < filters["min_container_sides"]:
                    continue
                if filters.get("max_container_sides") is not None and container_sides > filters["max_container_sides"]:
                    continue
                    
            except Exception:
                # If parse fails, we might just skip it if filters are on
                continue
        
        # Penalize if it's very recent
        stagnation = sum(1 for r in recent if r == p_str)
        penalty = stagnation * 0.05
        
        scored_candidates.append((p_str, base_density + penalty))
        
    if not scored_candidates:
        return "8_3_in_5"
        
    scored_candidates.sort(key=lambda x: x[1])
    return scored_candidates[0][0]


def is_stuck(
    history: List[ExperimentResult],
    problem: str,
    threshold_no_improve: int = 5,
) -> bool:
    """
    Consider a problem 'stuck' if the last threshold_no_improve experiments
    on this problem had no score improvement and all were non-crash.
    """
    window = last_experiments_for(history, problem, last=max(threshold_no_improve, 5))
    if len(window) < threshold_no_improve:
        return False

    # All must be for this problem and non-crash.
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


def log_result(
    history: Optional[List[ExperimentResult]],
    problem: str,
    score: float,
    seconds: float,
    description: str,
    commit: str = "HEAD",
    memory_gb: float = 0.0,
    path: str = "results.tsv",
) -> str:
    """
    Log result to results.tsv and decide status:
    - "keep"     if improved best for that problem
    - "discard"  if no improvement
    - "crash"    if score <= 0 or missing

    If history is None, it will be loaded from path.
    """
    if history is None:
        history = load_history(path)

    best = current_best_scores(history)
    current_best = best.get(problem, float("inf"))

    if score is None or score <= 0:
        status = "crash"
        score = 0.0
    elif score < current_best:
        status = "keep"
    else:
        status = "discard"

    result = ExperimentResult(
        problem=problem,
        score=score,
        status=status,
        description=description or "",
        seconds=seconds,
        commit=commit,
        memory_gb=memory_gb,
    )

    append_result(path, result)
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

    if current and radically:
        # If radical time, force diversity.
        problem = choose_problem(history, prefer_different=True)
    elif is_stuck(history, current or ""):
        problem = choose_problem(history, prefer_different=True)
    else:
        # Optionally switch even if not stuck for diversity.
        problem = choose_problem(history) or (current or "8_3_in_5")

    return problem, radically


# End of agent_loop.py