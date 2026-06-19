import numpy as np
from scipy.optimize import basinhopping, minimize
from numba import njit
from joblib import Parallel, delayed
import argparse
import os
import time

# Use non-interactive backend; only import matplotlib if we actually save a plot.
os.environ.setdefault("MPLBACKEND", "Agg")

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("inner_polygons", type=int, help="Number of inner polygons")
arg_parser.add_argument("inner_sides", type=int, help="Number of sides of the inner polygons")
arg_parser.add_argument("container_sides", type=int, help="Number of sides of the container polygon")
arg_parser.add_argument("--attempts", type=int, default=1000, help="Number of attempts to run")
arg_parser.add_argument("--tolerance", type=float, default=1e-8, help="Overlap penalty tolerance. Probably best left at default")
arg_parser.add_argument("--finalstep", type=float, default=0.0001, help="How small the last theoretical step in container size decrease will be (it gets smaller over time)")
arg_parser.add_argument("--output_format", type=str, default="none", help="Output image format: png, svg, or none (default: none)")
arg_parser.add_argument("--time_limit", type=float, default=None,
                        help="Hard time limit in seconds for entire run (optional)")
arg_parser.add_argument("--output_dir", type=str, default=".", help="Directory to save output images")
arg_parser.add_argument("--output_prefix", type=str, default="", help="Prefix for output filenames")
args = arg_parser.parse_args()

N = args.inner_polygons
nsi = args.inner_sides
nsc = args.container_sides
attempts = args.attempts
penalty_tolerance = args.tolerance
final_step_size = args.finalstep
output_dir = args.output_dir
output_prefix = args.output_prefix

unit_polygon_angles = np.linspace(0, 2 * np.pi, nsi, endpoint=False)
unit_polygon_vertices = np.column_stack((np.cos(unit_polygon_angles), np.sin(unit_polygon_angles)))
unit_polygon_vectors = np.column_stack((np.cos(unit_polygon_angles + np.pi / nsi), np.sin(unit_polygon_angles + np.pi / nsi)))
unit_container_angles = np.linspace(0, 2 * np.pi, nsc, endpoint=False)
unit_container_vertices = np.column_stack((np.cos(unit_container_angles), np.sin(unit_container_angles)))
unit_container_vectors = np.column_stack((np.cos(unit_container_angles + np.pi / nsc), np.sin(unit_container_angles + np.pi / nsc)))
unit_container_apothem = np.cos(np.pi / nsc)

@njit(cache=True)
def transform_polygon(x, y, a, vertices):
    n_vertices = vertices.shape[0]
    transformed = np.empty_like(vertices)
    sina = np.sin(a)
    cosa = np.cos(a)
    for i in range(n_vertices):
        vx = vertices[i, 0]
        vy = vertices[i, 1]
        transformed[i, 0] = x + (vx * cosa - vy * sina)
        transformed[i, 1] = y + (vx * sina + vy * cosa)
    return transformed

@njit(cache=True)
def rotate_vectors(a, vectors):
    n_vectors = vectors.shape[0]
    rotated = np.empty_like(vectors)
    sina = np.sin(a)
    cosa = np.cos(a)
    for i in range(n_vectors):
        vecx = vectors[i, 0]
        vecy = vectors[i, 1]
        rotated[i, 0] = vecx * cosa - vecy * sina
        rotated[i, 1] = vecx * sina + vecy * cosa
    return rotated
         
@njit(cache=True)
def poking_penalty(vertices, S):
    penalty = 0.0
    limit = unit_container_apothem * S
    for v in range(vertices.shape[0]):
        vx = vertices[v, 0]
        vy = vertices[v, 1]
        for i in range(nsc):
            distance = vx * unit_container_vectors[i, 0] + vy * unit_container_vectors[i, 1]
            if distance > limit:
                diff = distance - limit
                penalty += diff * diff
    return penalty

@njit(cache=True)
def bh_function(values, S):
    penalty = 0.0
    polygon_array = np.zeros((N, nsi, 2))
    vector_array = np.zeros((N, nsi, 2))
    for i in range(N):
        posx = values[i * 3]
        posy = values[i * 3 + 1]
        rot = values[i * 3 + 2]
        polygon_array[i] = transform_polygon(posx, posy, rot, unit_polygon_vertices)
        vector_array[i] = rotate_vectors(rot, unit_polygon_vectors)

        penalty += poking_penalty(polygon_array[i], S)

    for i in range(N):
        for j in range(i + 1, N):
            collision = True
            min_overlap = 1e30
            for vec in range(nsi * 2):
                if vec < nsi:
                    x_axis = vector_array[i][vec, 0]
                    y_axis = vector_array[i][vec, 1]
                else:
                    x_axis = vector_array[j][vec - nsi, 0]
                    y_axis = vector_array[j][vec - nsi, 1]

                min_1 = 1e30
                max_1 = -1e30
                for vert in range(nsi):
                    dotp = polygon_array[i][vert, 0] * x_axis + polygon_array[i][vert, 1] * y_axis
                    if dotp < min_1:
                        min_1 = dotp
                    if dotp > max_1:
                        max_1 = dotp

                min_2 = 1e30
                max_2 = -1e30
                for vert in range(nsi):
                    dotp = polygon_array[j][vert, 0] * x_axis + polygon_array[j][vert, 1] * y_axis
                    if dotp < min_2:
                        min_2 = dotp
                    if dotp > max_2:
                        max_2 = dotp

                overlap = min(max_1, max_2) - max(min_1, min_2)
                if overlap <= 0:
                    collision = False
                    break
                if overlap < min_overlap:
                    min_overlap = overlap

            if collision:
                penalty += min_overlap * min_overlap
            
    return penalty

run_start_time = time.time()
time_limit = args.time_limit

def repetition(seed):
    # Check time limit
    if time_limit and time.time() - run_start_time > time_limit - 5:
        return float("inf"), None

    # Quiet: only print attempt count periodically
    if seed % 100 == 0:
        print("Attempt", seed, flush=True)

    np.random.seed(seed)
    dynamic_S = np.sqrt(N) * (2 + np.random.rand() * 2)
    initial_S = dynamic_S
    lowest_S = np.sqrt(N)
    range_val = initial_S - lowest_S

    if np.random.rand() < 0.5:
        x0 = np.random.uniform(-dynamic_S/2, dynamic_S/2, N * 3)
    else:
        grid_linspace = np.linspace(-dynamic_S/2 * 0.9, dynamic_S/2 * 0.9, int(np.ceil(np.sqrt(N))))
        xx, yy = np.meshgrid(grid_linspace, grid_linspace)
        grid_points = np.column_stack((xx.flatten(), yy.flatten()))[:N]
        x0 = np.zeros(N * 3)
        x0[0::3] = grid_points[:, 0]
        x0[1::3] = grid_points[:, 1]
        x0[2::3] = np.random.uniform(0, 2 * np.pi, N)
    
    last_valid_x = x0.copy()
    last_valid_S = dynamic_S

    while True:
        # Respect global time limit
        if time_limit and time.time() - run_start_time > time_limit - 5:
            break

        minimized = minimize(bh_function, x0, args=(dynamic_S,), method="L-BFGS-B", tol=1e-7)
        multiplier = 1 - final_step_size - (dynamic_S - lowest_S) * (0.01 - final_step_size) / (range_val)
        if minimized.fun < penalty_tolerance:
            last_valid_x = minimized.x.copy()
            last_valid_S = dynamic_S.copy()
            x0 = minimized.x * multiplier
            dynamic_S *= multiplier
        else:
            # Lighter basin-hopping to keep runtime in 5-min budget
            bh_result = basinhopping(
                lambda x, s: bh_function(x, s),
                x0,
                minimizer_kwargs={'method': 'L-BFGS-B', 'args': (dynamic_S,), 'tol': 1e-7},
                niter=30,
                T=0.2,
                stepsize=0.12
            )
            if bh_result.fun < penalty_tolerance:
                last_valid_x = bh_result.x.copy()
                last_valid_S = dynamic_S
                x0 = bh_result.x * multiplier
                dynamic_S *= multiplier
            else:
                break
    return last_valid_S, last_valid_x

best_S = float("inf")
best_values = None
results = Parallel(n_jobs=-1, prefer="processes")(delayed(repetition)(i) for i in range(attempts))

for s, values in results:
    if s < best_S and values is not None:
        best_S = s
        best_values = values

# Final metric
final_metric = best_S * np.sin(np.pi / nsc) / np.sin(np.pi / nsi)
print("Final side length:", final_metric)

# Only plot if explicitly requested via output_format != "none"
if args.output_format in ("png", "svg"):
    if best_values is not None:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        final_positions = best_values.reshape((N, 3))
        fig, ax = plt.subplots()
        container_plot = np.vstack((unit_container_vertices * best_S, unit_container_vertices[0] * best_S))
        ax.plot(container_plot[:,0], container_plot[:,1], color="#000000", linewidth=0.5)
        for i in range(N):
            polygon = transform_polygon(
                best_values[i * 3],
                best_values[i * 3 + 1],
                best_values[i * 3 + 2],
                unit_polygon_vertices
            )
            polygon_plot = np.vstack((polygon, polygon[0]))
            ax.fill(polygon_plot[:,0], polygon_plot[:,1], "#CCCCCC", edgecolor="black", linewidth=0.5)
        ax.set_aspect("equal")
        plt.title(f"Side length: {final_metric}")

        base_name = f"{N}_{nsi}_in_{nsc}"
        # Build output path using --output_dir and --output_prefix if provided
        out_dir = output_dir or "."
        os.makedirs(out_dir, exist_ok=True)

        if output_prefix:
            base_name = f"{output_prefix}_{base_name}"

        if args.output_format == "png":
            candidate = os.path.join(out_dir, f"{base_name}.png")
            if not os.path.exists(candidate):
                path = candidate
            else:
                file_i = 1
                while os.path.exists(os.path.join(out_dir, f"{base_name}_({file_i}).png")):
                    file_i += 1
                path = os.path.join(out_dir, f"{base_name}_({file_i}).png")
            plt.savefig(path)
        elif args.output_format == "svg":
            candidate = os.path.join(out_dir, f"{base_name}.svg")
            if not os.path.exists(candidate):
                path = candidate
            else:
                file_i = 1
                while os.path.exists(os.path.join(out_dir, f"{base_name}_({file_i}).svg")):
                    file_i += 1
                path = os.path.join(out_dir, f"{base_name}_({file_i}).svg")
            plt.savefig(path)
        plt.close(fig)
import numpy as np
from scipy.optimize import basinhopping, minimize
from numba import njit
from joblib import Parallel, delayed
import argparse
import os
import time

# Use non-interactive backend; only import matplotlib if we actually save a plot.
os.environ.setdefault("MPLBACKEND", "Agg")

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("inner_polygons", type=int, help="Number of inner polygons")
arg_parser.add_argument("inner_sides", type=int, help="Number of sides of the inner polygons")
arg_parser.add_argument("container_sides", type=int, help="Number of sides of the container polygon")
arg_parser.add_argument("--attempts", type=int, default=1000, help="Number of attempts to run")
arg_parser.add_argument("--tolerance", type=float, default=1e-8, help="Overlap penalty tolerance. Probably best left at default")
arg_parser.add_argument("--finalstep", type=float, default=0.0001, help="How small the last theoretical step in container size decrease will be (it gets smaller over time)")
arg_parser.add_argument("--output_format", type=str, default="none", help="Output image format: png, svg, or none (default: none)")
arg_parser.add_argument("--time_limit", type=float, default=None,
                        help="Hard time limit in seconds for entire run (optional)")
arg_parser.add_argument("--output_dir", type=str, default=".", help="Directory to save output images")
arg_parser.add_argument("--output_prefix", type=str, default="", help="Prefix for output filenames")
args = arg_parser.parse_args()

N = args.inner_polygons
nsi = args.inner_sides
nsc = args.container_sides
attempts = args.attempts
penalty_tolerance = args.tolerance
final_step_size = args.finalstep
output_dir = args.output_dir
output_prefix = args.output_prefix

unit_polygon_angles = np.linspace(0, 2 * np.pi, nsi, endpoint=False)
unit_polygon_vertices = np.column_stack((np.cos(unit_polygon_angles), np.sin(unit_polygon_angles)))
unit_polygon_vectors = np.column_stack((np.cos(unit_polygon_angles + np.pi / nsi), np.sin(unit_polygon_angles + np.pi / nsi)))
unit_container_angles = np.linspace(0, 2 * np.pi, nsc, endpoint=False)
unit_container_vertices = np.column_stack((np.cos(unit_container_angles), np.sin(unit_container_angles)))
unit_container_vectors = np.column_stack((np.cos(unit_container_angles + np.pi / nsc), np.sin(unit_container_angles + np.pi / nsc)))
unit_container_apothem = np.cos(np.pi / nsc)

@njit(cache=True)
def transform_polygon(x, y, a, vertices):
    n_vertices = vertices.shape[0]
    transformed = np.empty_like(vertices)
    sina = np.sin(a)
    cosa = np.cos(a)
    for i in range(n_vertices):
        vx = vertices[i, 0]
        vy = vertices[i, 1]
        transformed[i, 0] = x + (vx * cosa - vy * sina)
        transformed[i, 1] = y + (vx * sina + vy * cosa)
    return transformed

@njit(cache=True)
def rotate_vectors(a, vectors):
    n_vectors = vectors.shape[0]
    rotated = np.empty_like(vectors)
    sina = np.sin(a)
    cosa = np.cos(a)
    for i in range(n_vectors):
        vecx = vectors[i, 0]
        vecy = vectors[i, 1]
        rotated[i, 0] = vecx * cosa - vecy * sina
        rotated[i, 1] = vecx * sina + vecy * cosa
    return rotated
         
@njit(cache=True)
def poking_penalty(vertices, S):
    penalty = 0.0
    limit = unit_container_apothem * S
    for v in range(vertices.shape[0]):
        vx = vertices[v, 0]
        vy = vertices[v, 1]
        for i in range(nsc):
            distance = vx * unit_container_vectors[i, 0] + vy * unit_container_vectors[i, 1]
            if distance > limit:
                diff = distance - limit
                penalty += diff * diff
    return penalty

@njit(cache=True)
def bh_function(values, S):
    penalty = 0.0
    polygon_array = np.zeros((N, nsi, 2))
    vector_array = np.zeros((N, nsi, 2))
    for i in range(N):
        posx = values[i * 3]
        posy = values[i * 3 + 1]
        rot = values[i * 3 + 2]
        polygon_array[i] = transform_polygon(posx, posy, rot, unit_polygon_vertices)
        vector_array[i] = rotate_vectors(rot, unit_polygon_vectors)

        penalty += poking_penalty(polygon_array[i], S)

    for i in range(N):
        for j in range(i + 1, N):
            collision = True
            min_overlap = 1e30
            for vec in range(nsi * 2):
                if vec < nsi:
                    x_axis = vector_array[i][vec, 0]
                    y_axis = vector_array[i][vec, 1]
                else:
                    x_axis = vector_array[j][vec - nsi, 0]
                    y_axis = vector_array[j][vec - nsi, 1]

                min_1 = 1e30
                max_1 = -1e30
                for vert in range(nsi):
                    dotp = polygon_array[i][vert, 0] * x_axis + polygon_array[i][vert, 1] * y_axis
                    if dotp < min_1:
                        min_1 = dotp
                    if dotp > max_1:
                        max_1 = dotp

                min_2 = 1e30
                max_2 = -1e30
                for vert in range(nsi):
                    dotp = polygon_array[j][vert, 0] * x_axis + polygon_array[j][vert, 1] * y_axis
                    if dotp < min_2:
                        min_2 = dotp
                    if dotp > max_2:
                        max_2 = dotp

                overlap = min(max_1, max_2) - max(min_1, min_2)
                if overlap <= 0:
                    collision = False
                    break
                if overlap < min_overlap:
                    min_overlap = overlap

            if collision:
                penalty += min_overlap * min_overlap
            
    return penalty

run_start_time = time.time()
time_limit = args.time_limit

def repetition(seed):
    # Check time limit
    if time_limit and time.time() - run_start_time > time_limit - 5:
        return float("inf"), None

    # Quiet: only print attempt count periodically
    if seed % 100 == 0:
        print("Attempt", seed, flush=True)

    np.random.seed(seed)
    dynamic_S = np.sqrt(N) * (2 + np.random.rand() * 2)
    initial_S = dynamic_S
    lowest_S = np.sqrt(N)
    range_val = initial_S - lowest_S

    if np.random.rand() < 0.5:
        x0 = np.random.uniform(-dynamic_S/2, dynamic_S/2, N * 3)
    else:
        grid_linspace = np.linspace(-dynamic_S/2 * 0.9, dynamic_S/2 * 0.9, int(np.ceil(np.sqrt(N))))
        xx, yy = np.meshgrid(grid_linspace, grid_linspace)
        grid_points = np.column_stack((xx.flatten(), yy.flatten()))[:N]
        x0 = np.zeros(N * 3)
        x0[0::3] = grid_points[:, 0]
        x0[1::3] = grid_points[:, 1]
        x0[2::3] = np.random.uniform(0, 2 * np.pi, N)
    
    last_valid_x = x0.copy()
    last_valid_S = dynamic_S

    while True:
        # Respect global time limit
        if time_limit and time.time() - run_start_time > time_limit - 5:
            break

        minimized = minimize(bh_function, x0, args=(dynamic_S,), method="L-BFGS-B", tol=1e-7)
        multiplier = 1 - final_step_size - (dynamic_S - lowest_S) * (0.01 - final_step_size) / (range_val)
        if minimized.fun < penalty_tolerance:
            last_valid_x = minimized.x.copy()
            last_valid_S = dynamic_S.copy()
            x0 = minimized.x * multiplier
            dynamic_S *= multiplier
        else:
            # Lighter basin-hopping to keep runtime in 5-min budget
            bh_result = basinhopping(
                lambda x, s: bh_function(x, s),
                x0,
                minimizer_kwargs={'method': 'L-BFGS-B', 'args': (dynamic_S,), 'tol': 1e-7},
                niter=30,
                T=0.2,
                stepsize=0.12
            )
            if bh_result.fun < penalty_tolerance:
                last_valid_x = bh_result.x.copy()
                last_valid_S = dynamic_S
                x0 = bh_result.x * multiplier
                dynamic_S *= multiplier
            else:
                break
    return last_valid_S, last_valid_x

best_S = float("inf")
best_values = None
results = Parallel(n_jobs=-1, prefer="processes")(delayed(repetition)(i) for i in range(attempts))

for s, values in results:
    if s < best_S and values is not None:
        best_S = s
        best_values = values

# Final metric
final_metric = best_S * np.sin(np.pi / nsc) / np.sin(np.pi / nsi)
print("Final side length:", final_metric)

# Only plot if explicitly requested via output_format != "none"
if args.output_format in ("png", "svg"):
    if best_values is not None:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        final_positions = best_values.reshape((N, 3))
        fig, ax = plt.subplots()
        container_plot = np.vstack((unit_container_vertices * best_S, unit_container_vertices[0] * best_S))
        ax.plot(container_plot[:,0], container_plot[:,1], color="#000000", linewidth=0.5)
        for i in range(N):
            polygon = transform_polygon(
                best_values[i * 3],
                best_values[i * 3 + 1],
                best_values[i * 3 + 2],
                unit_polygon_vertices
            )
            polygon_plot = np.vstack((polygon, polygon[0]))
            ax.fill(polygon_plot[:,0], polygon_plot[:,1], "#CCCCCC", edgecolor="black", linewidth=0.5)
        ax.set_aspect("equal")
        plt.title(f"Side length: {final_metric}")

        base_name = f"{N}_{nsi}_in_{nsc}"
        # Build output path using --output_dir and --output_prefix if provided
        out_dir = output_dir or "."
        os.makedirs(out_dir, exist_ok=True)

        if output_prefix:
            base_name = f"{output_prefix}_{base_name}"

        if args.output_format == "png":
            candidate = os.path.join(out_dir, f"{base_name}.png")
            if not os.path.exists(candidate):
                path = candidate
            else:
                file_i = 1
                while os.path.exists(os.path.join(out_dir, f"{base_name}_({file_i}).png")):
                    file_i += 1
                path = os.path.join(out_dir, f"{base_name}_({file_i}).png")
            plt.savefig(path)
        elif args.output_format == "svg":
            candidate = os.path.join(out_dir, f"{base_name}.svg")
            if not os.path.exists(candidate):
                path = candidate
            else:
                file_i = 1
                while os.path.exists(os.path.join(out_dir, f"{base_name}_({file_i}).svg")):
                    file_i += 1
                path = os.path.join(out_dir, f"{base_name}_({file_i}).svg")
            plt.savefig(path)
        plt.close(fig)