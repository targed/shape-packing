import sys
import json
import math
import os

TOLERANCE = 1e-12

def regular_vertices(sides: int, radius: float):
    return [
        (radius * math.cos(2 * math.pi * i / sides),
         radius * math.sin(2 * math.pi * i / sides))
        for i in range(sides)
    ]

def regular_normals(sides: int):
    return [
        (math.cos(2 * math.pi * i / sides + math.pi / sides),
         math.sin(2 * math.pi * i / sides + math.pi / sides))
        for i in range(sides)
    ]

def transform(vertices, cx, cy, a):
    sa = math.sin(a)
    ca = math.cos(a)
    out = []
    for (vx, vy) in vertices:
        x = cx + (vx * ca - vy * sa)
        y = cy + (vx * sa + vy * ca)
        out.append((x, y))
    return out

def get_normals_of_polygon(vertices):
    normals = []
    n = len(vertices)
    for i in range(n):
        p1 = vertices[i]
        p2 = vertices[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        normals.append((dy / length, -dx / length))
    return normals

def project_polygon(normal, vertices):
    min_proj = float('inf')
    max_proj = float('-inf')
    for v in vertices:
        proj = normal[0] * v[0] + normal[1] * v[1]
        if proj < min_proj: min_proj = proj
        if proj > max_proj: max_proj = proj
    return min_proj, max_proj

def sat_overlap(poly1, poly2, normals1, normals2):
    axes = normals1 + normals2
    max_overlap = float('inf')
    
    for axis in axes:
        min1, max1 = project_polygon(axis, poly1)
        min2, max2 = project_polygon(axis, poly2)
        
        # Separating axis found: no overlap
        if max1 <= min2 + TOLERANCE or max2 <= min1 + TOLERANCE:
            return False, 0.0 
            
        # Penetration depth on this axis
        overlap = min(max1 - min2, max2 - min1)
        if overlap < max_overlap:
            max_overlap = overlap
            
    return True, max_overlap

def load_best_value(problem_str):
    tsv_path = "PACKING_REFERENCE.tsv"
    if not os.path.exists(tsv_path):
        return None
    with open(tsv_path, "r") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 6:
                our_prob = parts[5]
                if our_prob == problem_str:
                    try:
                        return float(parts[2])
                    except ValueError:
                        return None
    return None

def verify(solution_path, problem_str=None):
    with open(solution_path, "r") as f:
        sol = json.load(f)
        
    N = sol["N"]
    nsi = sol["inner_sides"]
    nsc = sol["container_sides"]
    S = sol["S"]
    values = sol["values"]
    
    # 1. Scale Verification
    calc_metric = S * math.sin(math.pi / nsc) / math.sin(math.pi / nsi)
    diff = abs(calc_metric - sol["final_metric"])
    if diff > 1e-10:
        print(f"[FAIL] Metric scaling is incorrect. Computed: {calc_metric}, JSON says: {sol['final_metric']}")
        return False
        
    unit_inner = regular_vertices(nsi, 1.0)
    container_normals = regular_normals(nsc)
    container_limit = S * math.cos(math.pi / nsc)
    
    polygons = []
    for i in range(N):
        x = values[i*3]
        y = values[i*3+1]
        a = values[i*3+2]
        poly = transform(unit_inner, x, y, a)
        polygons.append(poly)
        
    # 2. Container Bounds Verification
    for i, poly in enumerate(polygons):
        for v in poly:
            for n in container_normals:
                dist = v[0] * n[0] + v[1] * n[1]
                if dist > container_limit + TOLERANCE:
                    violation = dist - container_limit
                    print(f"[FAIL] Shape {i} is out of bounds! Violation margin: {violation}")
                    return False
                    
    # 3. Polygon Overlap Verification (SAT)
    poly_normals = [get_normals_of_polygon(p) for p in polygons]
    for i in range(N):
        for j in range(i+1, N):
            overlap, depth = sat_overlap(polygons[i], polygons[j], poly_normals[i], poly_normals[j])
            if overlap:
                print(f"[FAIL] Shapes {i} and {j} overlap! Depth: {depth}")
                return False
                
    print(f"[PASS] Configuration is valid geometrically!")
    print(f"Calculated Metric (s): {calc_metric:.15f}")
    
    # 4. Check Records
    if problem_str:
        best = load_best_value(problem_str)
        if best is not None:
            print(f"Current Record (s):    {best:.15f}")
            if calc_metric < best - TOLERANCE:
                print(f"*** NEW RECORD DISCOVERED! ***")
            else:
                print(f"Valid configuration, but not a new record.")
        else:
            print(f"No current record found for {problem_str}.")
            
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_solution.py <solution.json> [problem_string]")
        sys.exit(1)
    problem = sys.argv[2] if len(sys.argv) > 2 else None
    success = verify(sys.argv[1], problem)
    sys.exit(0 if success else 1)
