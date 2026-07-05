import csv
import json
import math
import os

def polygon_area(sides: int, side_length: float) -> float:
    # Area = (1/4) * n * s^2 * cot(pi/n)
    return 0.25 * sides * (side_length ** 2) / math.tan(math.pi / sides)

def generate_queue(ref_path="PACKING_REFERENCE.tsv", out_path="priority_queue.json"):
    from .problems import parse_problem, shape_token_to_sides
    
    queue = []
    if not os.path.exists(ref_path):
        print(f"Reference file not found: {ref_path}")
        return
        
    with open(ref_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            our_problem = (row.get("our_problem") or "").strip()
            if not our_problem:
                continue
                
            status = (row.get("status") or "").strip().lower()
            if status in ("trivial", "proved_optimal"):
                continue
                
            best_val_str = (row.get("best_value") or "").strip()
            if not best_val_str:
                continue
                
            try:
                best_value = float(best_val_str)
                p = parse_problem(our_problem)
                inner_sides = shape_token_to_sides(p.inner_token)
                container_sides = shape_token_to_sides(p.container_token)
                
                inner_area = p.N * polygon_area(inner_sides, 1.0)
                container_area = polygon_area(container_sides, best_value)
                density = inner_area / container_area
                
                queue.append({
                    "problem": our_problem,
                    "density": density
                })
            except Exception:
                continue
                
    queue.sort(key=lambda x: x["density"])
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

if __name__ == "__main__":
    generate_queue()
