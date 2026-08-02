import csv
import json
import math
import os
import glob

def polygon_area(sides: int, side_length: float) -> float:
    # Area = (1/4) * n * s^2 * cot(pi/n)
    return 0.25 * sides * (side_length ** 2) / math.tan(math.pi / sides)

def get_shape_area(shape_token: str, size: float) -> float:
    """
    Calculate the area of a shape given its token and a size parameter.
    For inner shapes (which are 'unit' shapes), size is typically 1.0.
    For container shapes, size is the 'best_value' (which might be side length s, or radius r).
    """
    t = shape_token.strip().lower()
    
    # Check for polygons first (e.g. "3", "4", "5", "square", "hexagon")
    if t in ("3", "triangle"):
        return polygon_area(3, size)
    elif t in ("4", "square"):
        return polygon_area(4, size)
    elif t in ("5", "pentagon"):
        return polygon_area(5, size)
    elif t in ("6", "hexagon"):
        return polygon_area(6, size)
    elif t in ("7", "heptagon"):
        return polygon_area(7, size)
    elif t in ("8", "octagon"):
        return polygon_area(8, size)
    elif t in ("9", "nonagon"):
        return polygon_area(9, size)
    elif t in ("10", "decagon"):
        return polygon_area(10, size)
    elif t in ("circle", "cir"):
        # area of circle = pi * r^2
        # Erich Friedman sets often report 's' (side) or 'r' (radius). We assume 'best_value' is radius for circles.
        return math.pi * (size ** 2)
    elif t in ("tan",):
        # A unit tan is a right isosceles triangle with legs 1, 1, hypotenuse sqrt(2).
        # Area = 0.5 * leg * leg
        return 0.5 * (size ** 2)
    elif t in ("dom", "domino"):
        # A unit domino is composed of two unit squares. Side 'size' usually refers to the shorter edge.
        # Area = 2 * (size^2)
        return 2.0 * (size ** 2)
    elif t in ("l", "l-tromino", "l_tromino"):
        # An L-tromino is composed of three unit squares.
        # Area = 3 * (size^2)
        return 3.0 * (size ** 2)
    
    try:
        sides = int(t)
        if sides >= 3:
            return polygon_area(sides, size)
    except ValueError:
        pass
        
    return None

def generate_queue(verif_dir="packingVerification", out_path="priority_queue.json"):
    queue = []
    
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
