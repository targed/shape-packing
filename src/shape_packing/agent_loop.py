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
from typing import List, Dict, Optional, Tuple, Any


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


def load_packing_reference(verif_dir: str = "packingVerification") -> List[Dict[str, Any]]:
    """
    Load all verified JSON datasets in packingVerification as list of dicts.
    Fields per entry:
      id, problem_family, N, inner_shape, container_shape,
      best_value (float|null), status, source_url, source_note, our_problem.
    """
    import glob
    rows = []
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
    filters: dict = None,
    exclude_problems: set = None,
) -> str:
    queue = load_priority_queue(queue_path)
    if not queue:
        return "8_3_in_5"

    recent = recent_problems(history, last=10)
    our_best = current_best_scores(history)
    # We no longer need to load_packing_reference here because queue has the metadata directly.
    # reference_rows = load_packing_reference()

    from .problems import parse_problem, shape_token_to_sides, is_special_shape

    # By default, skip special (non-polygon) shapes not wired into the Rust solver.
    # To allow them, explicitly list them in include_inner / include_container.
    def is_unsupported(token: str, f: dict) -> bool:
        t = token.upper().replace(" (COVERING)", "")
        if t == "CIR": t = "CIRCLE"
        if t == "DOM": t = "DOMINO"
        
        if is_special_shape(t):
            if f.get("include_inner") or f.get("include_container"):
                return False
            return True
        allowed = {"3", "4", "5", "6", "7", "8", "9", "10", "CIRCLE", "SQUARE", "TAN", "DOMINO", "L", "TRIANGLE"}
        if t not in allowed:
            return True
        return False

    scored_candidates = []

    for item in queue:
        p_str = item["problem"]
        base_density = item["density"]

        # Skip problems explicitly excluded (e.g. in-flight parallel jobs).
        if exclude_problems and p_str in exclude_problems:
            continue

        # Parse and basic pre-filter.
        try:
            p0 = parse_problem(p_str)
        except Exception as e:
            # print(f"Error parsing {p_str}: {e}")
            continue

        if is_unsupported(item.get("inner_shape", "").upper(), filters or {}):
            continue
        if is_unsupported(item.get("container_shape", "").upper(), filters or {}):
            continue

        # External filters (filter.json style).
        if filters:
            try:
                inner_token = p0.inner_token.upper()
                container_token = p0.container_token.upper()
                n = p0.N
                
                # Check for standard aliases
                if inner_token == "CIR": inner_token = "CIRCLE"
                if container_token == "CIR": container_token = "CIRCLE"
                if container_token == "TRIANGLE": container_token = "3"
                if inner_token == "TRIANGLE": inner_token = "3"
                
                # Try falling back to p0 entirely if aliases somehow break
                p0_inner = p0.inner_token.upper()
                p0_cont = p0.container_token.upper()
                if p0_inner == "CIR": p0_inner = "CIRCLE"
                if p0_cont == "CIR": p0_cont = "CIRCLE"
                if p0_cont == "TRIANGLE": p0_cont = "3"
                if p0_inner == "TRIANGLE": p0_inner = "3"
                inner_sides = shape_token_to_sides(inner_token)
                container_sides = shape_token_to_sides(container_token)

                if filters.get("min_n") is not None and n < filters["min_n"]:
                    continue
                if filters.get("max_n") is not None and n > filters["max_n"]:
                    continue
                if filters.get("equal_n") is not None and n != filters["equal_n"]:
                    continue

                # Also check aliases from item properties
                item_inner = item.get("inner_shape", "").upper()
                item_container = item.get("container_shape", "").upper().replace(" (COVERING)", "")
                
                if item_inner == "CIR": item_inner = "CIRCLE"
                if item_container == "CIR": item_container = "CIRCLE"
                if item_container == "3": item_container = "TRIANGLE"
                if item_inner == "3": item_inner = "TRIANGLE"
                if item_container == "TRIANGLE": item_container = "3"
                if item_inner == "TRIANGLE": item_inner = "3"

                inc_inner = []
                if filters.get("include_inner"):
                    inc_inner = [t.upper() for t in filters["include_inner"]]
                    # Add aliases to filter
                    if "CIRCLE" in inc_inner: inc_inner.append("CIR")
                    if "CIR" in inc_inner: inc_inner.append("CIRCLE")
                    if "3" in inc_inner: inc_inner.append("TRIANGLE")
                    if "TRIANGLE" in inc_inner: inc_inner.append("3")
                    
                    if inner_token not in inc_inner and p0_inner not in inc_inner and item_inner not in inc_inner:
                        continue
                        
                if filters.get("exclude_inner"):
                    exc_inner = [t.upper() for t in filters["exclude_inner"]]
                    if "CIRCLE" in exc_inner: exc_inner.append("CIR")
                    if "CIR" in exc_inner: exc_inner.append("CIRCLE")
                    if "3" in exc_inner: exc_inner.append("TRIANGLE")
                    if "TRIANGLE" in exc_inner: exc_inner.append("3")
                    if inner_token in exc_inner or p0_inner in exc_inner or item_inner in exc_inner:
                        continue

                inc_cont = []
                if filters.get("include_container"):
                    inc_cont = [t.upper() for t in filters["include_container"]]
                    if "CIRCLE" in inc_cont: inc_cont.append("CIR")
                    if "CIR" in inc_cont: inc_cont.append("CIRCLE")
                    if "3" in inc_cont: inc_cont.append("TRIANGLE")
                    if "TRIANGLE" in inc_cont: inc_cont.append("3")
                    if container_token not in inc_cont and p0_cont not in inc_cont and item_container not in inc_cont:
                        continue
                        
                if filters.get("exclude_container"):
                    exc_cont = [t.upper() for t in filters["exclude_container"]]
                    if "CIRCLE" in exc_cont: exc_cont.append("CIR")
                    if "CIR" in exc_cont: exc_cont.append("CIRCLE")
                    if "3" in exc_cont: exc_cont.append("TRIANGLE")
                    if "TRIANGLE" in exc_cont: exc_cont.append("3")
                    if container_token in exc_cont or p0_cont in exc_cont or item_container in exc_cont:
                        continue

                if inner_sides is None and inner_token == "CIRCLE":
                    inner_sides = 32
                if container_sides is None and container_token == "CIRCLE":
                    container_sides = 32
                    
                if filters.get("min_inner_sides") is not None and (inner_sides is None or inner_sides < filters["min_inner_sides"]):
                    continue
                if filters.get("max_inner_sides") is not None and (inner_sides is None or inner_sides > filters["max_inner_sides"]):
                    continue
                if filters.get("min_container_sides") is not None and (container_sides is None or container_sides < filters["min_container_sides"]):
                    continue
                if filters.get("max_container_sides") is not None and (container_sides is None or container_sides > filters["max_container_sides"]):
                    continue
            except Exception:
                continue

        # Reference-based decisions.
        ref_status = str(item.get("status") or "").strip().lower()
        best_value = item.get("best_value")
        try:
            best_value = float(best_value) if best_value is not None else None
        except ValueError:
            best_value = None

        # Massive penalty for trivial / proved_optimal: essentially block.
        if ref_status in ("trivial", "proved_optimal"):
            continue

        # Diversity / history-based penalties.
        stagnation = sum(1 for r in recent if r == p_str)
        penalty = stagnation * 0.05

        total_runs = sum(1 for r in history if r.problem == p_str)
        penalty += total_runs * 0.01

        # If stuck: strong penalty.
        if is_stuck(history, p_str, threshold_no_improve=5):
            penalty += 10.0

        # Our-best vs reference-best_value: prefer problems with room to improve.
        our = our_best.get(p_str, float("inf"))
        if best_value is not None and our != float("inf"):
            # If we are already within 0.2% of the reference best_value,
            # likely diminishing returns; downrank.
            rel_gap = (our - best_value) / best_value if best_value > 0 else 0.0
            if rel_gap < 0.002:
                # Near reference; add penalty.
                penalty += 5.0
            # If we have never reached close (gap > 10%), slight bonus by reducing effective density (making it more attractive).
            # We do this by a small negative penalty (i.e., a bonus).
            if rel_gap > 0.10:
                penalty -= 1.0  # bonus: prioritize under-achieved problems

        # Soft preference: best_known or human-found problems are interesting.
        if ref_status == "best_known":
            penalty -= 0.5  # mild bonus
        else:
            source_note = (item.get("source_note") or "").strip().lower()
            if "found by" in source_note or "erich friedman" in source_note:
                penalty -= 0.3  # mild bonus

        # Prefer_different: heavier penalty on recent problems.
        if prefer_different:
            if p_str in recent:
                penalty += 3.0

        scored_candidates.append((p_str, base_density + penalty))

    if not scored_candidates:
        print("No candidates matched filters!")
        return "8_3_in_5"

    # Lower is better: density + penalties
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