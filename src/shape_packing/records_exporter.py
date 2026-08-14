from __future__ import annotations

import os
import sys
import json
import math
import glob
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

SIDES_TO_NAME = {
    "3": "tri",
    "4": "squ",
    "5": "pen",
    "6": "hex",
    "7": "hep",
    "8": "oct",
    "9": "non",
    "10": "dec",
}

SPECIAL_NAMES = {
    "circle": "cir",
    "cir": "cir",
    "tan": "tan",
    "domino": "dom",
    "dom": "dom",
    "l": "L",
    "l-tromino": "L",
}

def name_for(token: str) -> str:
    s = str(token).strip().lower()
    if s in SIDES_TO_NAME:
        return SIDES_TO_NAME[s]
    return SPECIAL_NAMES.get(s, s)

def get_family_info(inner_token: str, container_token: str) -> Tuple[str, str]:
    """Return the family code (e.g. dominpen) and official Erich Friedman URL."""
    inner_name = name_for(inner_token)
    container_name = name_for(container_token)
    family_code = f"{inner_name}in{container_name}"
    url = f"https://erich-friedman.github.io/packing/{family_code}/index.html"
    return family_code, url

@dataclass
class RecordCandidate:
    problem: str
    N: int
    inner_token: str
    container_token: str
    solution_path: str
    run_dir: str
    S: float
    metric: float
    friedman_best: float
    improvement: float
    family_code: str = field(init=False)
    family_url: str = field(init=False)

    def __post_init__(self):
        self.family_code, self.family_url = get_family_info(self.inner_token, self.container_token)

@dataclass
class ExportResult:
    problem: str
    success: bool
    output_dir: str
    files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


from .solution_tools import load_solution, compute_friedman_metric
from .packing_config import get_friedman_best_for_problem, _load_friedman_verification_jsons


def find_all_records(
    results_dir: str = "results",
    min_improvement: float = 1e-5,
    family_filter: Optional[str] = None,
) -> List[RecordCandidate]:
    """
    Scans results_dir, identifies the best valid run per problem,
    and returns RecordCandidates that strictly beat Erich Friedman's known benchmarks.
    """
    _load_friedman_verification_jsons()
    if not os.path.exists(results_dir):
        return []

    # Map problem -> best (S, run_dir, solution_path, sol_obj)
    best_per_problem: Dict[str, Tuple[float, str, str, Any]] = {}

    for folder in os.listdir(results_dir):
        p_path = os.path.join(results_dir, folder)
        if not os.path.isdir(p_path):
            continue

        for run in os.listdir(p_path):
            run_dir = os.path.join(p_path, run)
            sol_path = os.path.join(run_dir, "solution.json")
            if not os.path.isfile(sol_path):
                continue

            try:
                sol = load_solution(sol_path)
            except Exception:
                continue

            p_token = f"{sol.N}_{sol.inner_token}_in_{sol.container_token}"
            if p_token not in best_per_problem or sol.S < best_per_problem[p_token][0]:
                best_per_problem[p_token] = (sol.S, run_dir, sol_path, sol)

    candidates: List[RecordCandidate] = []
    for p_token, (best_s, run_dir, sol_path, sol) in best_per_problem.items():
        recalc_metric = compute_friedman_metric(best_s, sol.inner_token, sol.container_token)
        friedman_best = get_friedman_best_for_problem(p_token)

        if friedman_best is None:
            continue

        improvement = recalc_metric - friedman_best
        if improvement < -min_improvement:
            cand = RecordCandidate(
                problem=p_token,
                N=sol.N,
                inner_token=str(sol.inner_token),
                container_token=str(sol.container_token),
                solution_path=sol_path,
                run_dir=run_dir,
                S=best_s,
                metric=recalc_metric,
                friedman_best=friedman_best,
                improvement=improvement,
            )
            if family_filter and family_filter.lower() != "all":
                if cand.family_code.lower() != family_filter.lower():
                    continue
            candidates.append(cand)

    candidates.sort(key=lambda c: (c.family_code, c.N, c.problem))
    return candidates

