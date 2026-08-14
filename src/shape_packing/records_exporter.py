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
