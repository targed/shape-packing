from __future__ import annotations

import json
import math
import os
import glob
from typing import Any, Dict, List, Optional, Tuple, Set, Union
from .packing_config import PACKING_VERIFICATION_DIR, PRIORITY_QUEUE_PATH
from .catalog import shape_area, list_frontier_families

def polygon_area(sides: int, side_length: float) -> float:
    # Area = (1/4) * n * s^2 * cot(pi/n)
    return 0.25 * sides * (side_length ** 2) / math.tan(math.pi / sides)

def get_shape_area(shape_token: str, size: float) -> Optional[float]:
    """
    Calculate the area of a shape given its token and a size parameter.
    Delegates to shared shape catalog for consistent coverage across all shapes.
    """
    return shape_area(shape_token, size)

def generate_queue(verif_dir=None, out_path=None):
    queue = []
    
    if verif_dir is None:
        verif_dir = PACKING_VERIFICATION_DIR
        if not os.path.exists(verif_dir):
            if os.path.exists(os.path.join("data", "packingVerification")):
                verif_dir = os.path.join("data", "packingVerification")
            elif os.path.exists("packingVerification"):
                verif_dir = "packingVerification"
    if out_path is None:
        out_path = PRIORITY_QUEUE_PATH
        
    if not os.path.exists(verif_dir):
        print(f"Verification directory not found: {verif_dir}")
        return
        
    json_files = glob.glob(os.path.join(verif_dir, "*.json"))
    
    for filepath in json_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    continue
                
                for item in data:
                    our_problem = (item.get("our_problem") or "").strip()
                    if not our_problem:
                        continue
                        
                    status = (item.get("status") or "").strip().lower()
                    if status in ("trivial", "proved_optimal"):
                        continue
                        
                    best_value = item.get("best_value")
                    if best_value is None:
                        continue
                    try:
                        best_value = float(best_value)
                    except (ValueError, TypeError):
                        continue
                        
                    inner_shape = item.get("inner_shape", "")
                    container_shape = item.get("container_shape", "").replace(" (covering)", "")
                    N = item.get("N")
                    
                    if not inner_shape or not container_shape or N is None:
                        continue
                        
                    inner_area_unit = get_shape_area(inner_shape, 1.0)
                    container_area_val = get_shape_area(container_shape, best_value)
                    
                    if inner_area_unit is None or container_area_val is None:
                        # Cannot compute mathematical density for this shape pair (e.g. minrect, rigid)
                        # Push to a default priority or skip.
                        continue
                        
                    total_inner_area = N * inner_area_unit
                    
                    # For packing, density = inner / container.
                    # For covering, density = container / inner.
                    # We will use density relative to container for both, but note that 
                    # covering sets have 'cov' or '(covering)' in their name/container.
                    is_covering = "cov" in our_problem.lower() or "cov" in item.get("problem_family", "").lower()
                    
                    if is_covering:
                        # Wasted space in covering is overlapping. Lower density = higher overlap = more room to improve
                        # Actually covering density is total_inner_area / container_area.
                        # Efficient covering means density approaches 1.0 from above.
                        # We want highest density to be prioritized if we want to improve covering.
                        # But to keep sorting consistent (lowest first), we'll do 1.0 / density.
                        density = container_area_val / total_inner_area if total_inner_area > 0 else float('inf')
                    else:
                        # Packing: efficient means density approaches 1.0 from below.
                        # Lowest density = most wasted space = prioritize first.
                        density = total_inner_area / container_area_val if container_area_val > 0 else 0
                        
                    queue.append({
                        "problem": our_problem,
                        "density": density,
                        "N": N,
                        "status": status,
                        "tier": item.get("tier", "benchmark"),
                        "inner_shape": inner_shape,
                        "container_shape": container_shape,
                        "best_value": best_value
                    })
        except Exception as e:
            print(f"Failed to process {filepath}: {e}")
            continue
            
    # Sort lowest density first. (For packing: most wasted space. For covering: highest overlap).
    queue.sort(key=lambda x: x["density"])
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
    print(f"Generated priority queue with {len(queue)} items.")

if __name__ == "__main__":
    generate_queue()
