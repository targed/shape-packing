import sys
import re

with open("packer_rs/src/main.rs", "r") as f:
    code = f.read()

# 1. Replace run_attempt signature and call
code = code.replace(
"""fn run_attempt<R: Rng>(
    rng: &mut R,
    N_f64: f64,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &[(f64, f64)],
    unit_polygon_vectors: &[(f64, f64)],
    unit_container_vectors: &[(f64, f64)],
    unit_container_apothem: f64,
    penalty_tolerance: f64,
    final_step_size: f64,
    start: &Instant,
    stop_flag: &AtomicBool,""",
"""fn run_attempt<R: Rng>(
    rng: &mut R,
    N_f64: f64,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &[(f64, f64)],
    unit_polygon_vectors: &[(f64, f64)],
    unit_container_vectors: &[(f64, f64)],
    unit_container_apothem: f64,
    penalty_tolerance: f64,
    final_step_size: f64,
    start: &Instant,
    stop_flag: &AtomicBool,
    time_limit: Option<f64>,""")

code = code.replace(
"""                let (s, x) = run_attempt(
                    &mut rng,
                    *N_f64,
                    nsi,
                    nsc,
                    upv,
                    upvectors,
                    ucv,
                    **uap,
                    penalty_tolerance,
                    final_step_size,
                    start,
                    stop,
                );""",
"""                let (s, x) = run_attempt(
                    &mut rng,
                    *N_f64,
                    nsi,
                    nsc,
                    upv,
                    upvectors,
                    ucv,
                    **uap,
                    penalty_tolerance,
                    final_step_size,
                    start,
                    stop,
                    args.time_limit,
                );""")

code = code.replace(
"""        if stop_flag.load(Ordering::Relaxed)
            || (start.elapsed().as_secs_f64() > 280.0 && N > 1)
        {
            break;
        }""",
"""        if stop_flag.load(Ordering::Relaxed)
            || start.elapsed().as_secs_f64() > time_limit.unwrap_or(280.0)
        {
            break;
        }""")

# 2. Update minimize_gradient
minimize_body_old = """    let n = x0.len();
    let mut x = x0.to_vec();
    let mut best_x = x.clone();
    let mut best_fun = penalty_function(
        &x,
        S,
        N,
        nsi,
        nsc,
        unit_polygon_vertices,
        unit_polygon_vectors,
        unit_container_vectors,
        unit_container_apothem,
    );

    let mut m = vec![0.0f64; n];
    let mut v = vec![0.0f64; n];
    let beta1 = 0.9f64;
    let beta2 = 0.999f64;
    let epsilon = 1e-8f64;
    let alpha = 0.02f64; // learning rate

    for iter in 1..=800 {
        let grad = gradient_numerical(
            &x,
            S,
            N,
            nsi,
            nsc,
            unit_polygon_vertices,
            unit_polygon_vectors,
            unit_container_vectors,
            unit_container_apothem,
        );

        let mut new_x = vec![0.0f64; n];
        for i in 0..n {
            m[i] = beta1 * m[i] + (1.0 - beta1) * grad[i];
            v[i] = beta2 * v[i] + (1.0 - beta2) * grad[i] * grad[i];

            let m_hat = m[i] / (1.0 - beta1.powi(iter as i32));
            let v_hat = v[i] / (1.0 - beta2.powi(iter as i32));

            new_x[i] = x[i] - alpha * m_hat / (v_hat.sqrt() + epsilon);
        }

        let new_fx = penalty_function(
            &new_x,
            S,
            N,
            nsi,
            nsc,
            unit_polygon_vertices,
            unit_polygon_vectors,
            unit_container_vectors,
            unit_container_apothem,
        );

        x = new_x;
        if new_fx < best_fun {
            best_fun = new_fx;
            best_x = x.clone();
        }
    }

    OptResult { x: best_x, fun: best_fun }
}"""

minimize_body_new = """    let n = x0.len();
    let mut x = x0.to_vec();
    let mut best_x = x.clone();
    let (mut best_fun, _) = penalty_and_gradient(
        &x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, false
    );

    let mut m = vec![0.0f64; n];
    let mut v = vec![0.0f64; n];
    let beta1 = 0.9f64;
    let beta2 = 0.999f64;
    let epsilon = 1e-8f64;
    let alpha = 0.02f64; // learning rate

    for iter in 1..=800 {
        let (_, grad) = penalty_and_gradient(
            &x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, true
        );

        let mut new_x = vec![0.0f64; n];
        for i in 0..n {
            m[i] = beta1 * m[i] + (1.0 - beta1) * grad[i];
            v[i] = beta2 * v[i] + (1.0 - beta2) * grad[i] * grad[i];

            let m_hat = m[i] / (1.0 - beta1.powi(iter as i32));
            let v_hat = v[i] / (1.0 - beta2.powi(iter as i32));

            new_x[i] = x[i] - alpha * m_hat / (v_hat.sqrt() + epsilon);
        }

        let (new_fx, _) = penalty_and_gradient(
            &new_x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, false
        );

        x = new_x;
        if new_fx < best_fun {
            best_fun = new_fx;
            best_x = x.clone();
        }
    }

    OptResult { x: best_x, fun: best_fun }
}"""
code = code.replace(minimize_body_old, minimize_body_new)

# 3. Add penalty_and_gradient function and remove the old ones
code = re.sub(r"fn penalty_function\(.*?fn gradient_numerical\(.*?\n}", "", code, flags=re.DOTALL)

penalty_and_gradient_str = """
fn penalty_and_gradient(
    values: &[f64],
    S: f64,
    N: usize,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &[(f64, f64)],
    unit_polygon_vectors: &[(f64, f64)],
    unit_container_vectors: &[(f64, f64)],
    unit_container_apothem: f64,
    compute_grad: bool,
) -> (f64, Vec<f64>) {
    let mut penalty = 0.0f64;
    let mut grad = if compute_grad { vec![0.0f64; values.len()] } else { vec![] };

    let mut polygon_array = vec![(0.0, 0.0); N * nsi];
    let mut vector_array = vec![(0.0, 0.0); N * nsi];

    for i in 0..N {
        let posx = values[i * 3];
        let posy = values[i * 3 + 1];
        let rot = values[i * 3 + 2];
        let sin_a = rot.sin();
        let cos_a = rot.cos();

        for v in 0..nsi {
            let (vx, vy) = unit_polygon_vertices[v];
            let tx = posx + (vx * cos_a - vy * sin_a);
            let ty = posy + (vx * sin_a + vy * cos_a);
            polygon_array[i * nsi + v] = (tx, ty);
        }

        for v in 0..nsi {
            let (vx, vy) = unit_polygon_vectors[v];
            let rx = vx * cos_a - vy * sin_a;
            let ry = vx * sin_a + vy * cos_a;
            vector_array[i * nsi + v] = (rx, ry);
        }

        let limit = unit_container_apothem * S;
        for v in 0..nsi {
            let (tx, ty) = polygon_array[i * nsi + v];
            for j in 0..nsc {
                let (cx, cy) = unit_container_vectors[j];
                let dist = tx * cx + ty * cy;
                if dist > limit {
                    let diff = dist - limit;
                    penalty += diff * diff;

                    if compute_grad {
                        let ddist_dposx = cx;
                        let ddist_dposy = cy;
                        let ddist_drot = -(ty - posy) * cx + (tx - posx) * cy;

                        let term = 2.0 * diff;
                        grad[i * 3] += term * ddist_dposx;
                        grad[i * 3 + 1] += term * ddist_dposy;
                        grad[i * 3 + 2] += term * ddist_drot;
                    }
                }
            }
        }
    }

    for i in 0..N {
        for j in (i + 1)..N {
            let mut collision = true;
            let mut min_overlap = 1e30f64;
            let mut best_axis_idx = 0;
            let mut best_v1_min = 0;
            let mut best_v1_max = 0;
            let mut best_v2_min = 0;
            let mut best_v2_max = 0;

            for vec in 0..(nsi * 2) {
                let (x_axis, y_axis) = if vec < nsi {
                    vector_array[i * nsi + vec]
                } else {
                    vector_array[j * nsi + (vec - nsi)]
                };

                let mut min_1 = 1e30f64;
                let mut max_1 = -1e30f64;
                let mut v1_min = 0;
                let mut v1_max = 0;
                for v in 0..nsi {
                    let (px, py) = polygon_array[i * nsi + v];
                    let dot = px * x_axis + py * y_axis;
                    if dot < min_1 { min_1 = dot; v1_min = v; }
                    if dot > max_1 { max_1 = dot; v1_max = v; }
                }

                let mut min_2 = 1e30f64;
                let mut max_2 = -1e30f64;
                let mut v2_min = 0;
                let mut v2_max = 0;
                for v in 0..nsi {
                    let (px, py) = polygon_array[j * nsi + v];
                    let dot = px * x_axis + py * y_axis;
                    if dot < min_2 { min_2 = dot; v2_min = v; }
                    if dot > max_2 { max_2 = dot; v2_max = v; }
                }

                let overlap = max_1.min(max_2) - min_1.max(min_2);
                if overlap <= 0.0 {
                    collision = false;
                    break;
                }
                if overlap < min_overlap {
                    min_overlap = overlap;
                    best_axis_idx = vec;
                    best_v1_min = v1_min;
                    best_v1_max = v1_max;
                    best_v2_min = v2_min;
                    best_v2_max = v2_max;
                }
            }

            if collision {
                penalty += min_overlap * min_overlap;

                if compute_grad {
                    let term = 2.0 * min_overlap;
                    let (x_axis, y_axis) = if best_axis_idx < nsi {
                        vector_array[i * nsi + best_axis_idx]
                    } else {
                        vector_array[j * nsi + (best_axis_idx - nsi)]
                    };

                    let p1_max = polygon_array[i * nsi + best_v1_max];
                    let max_1 = p1_max.0 * x_axis + p1_max.1 * y_axis;
                    let p2_max = polygon_array[j * nsi + best_v2_max];
                    let max_2 = p2_max.0 * x_axis + p2_max.1 * y_axis;
                    let p1_min = polygon_array[i * nsi + best_v1_min];
                    let min_1 = p1_min.0 * x_axis + p1_min.1 * y_axis;
                    let p2_min = polygon_array[j * nsi + best_v2_min];
                    let min_2 = p2_min.0 * x_axis + p2_min.1 * y_axis;

                    let (p_upper, v_upper_idx, upper_poly_idx) = if max_1 < max_2 {
                        (p1_max, best_v1_max, i)
                    } else {
                        (p2_max, best_v2_max, j)
                    };

                    let (p_lower, v_lower_idx, lower_poly_idx) = if min_1 > min_2 {
                        (p1_min, best_v1_min, i)
                    } else {
                        (p2_min, best_v2_min, j)
                    };

                    let mut add_grad = |poly_idx: usize, sign: f64, p: (f64, f64)| {
                        let posx = values[poly_idx * 3];
                        let posy = values[poly_idx * 3 + 1];
                        let dp_drot_x = -(p.1 - posy);
                        let dp_drot_y = p.0 - posx;
                        grad[poly_idx * 3] += term * sign * x_axis;
                        grad[poly_idx * 3 + 1] += term * sign * y_axis;
                        grad[poly_idx * 3 + 2] += term * sign * (dp_drot_x * x_axis + dp_drot_y * y_axis);
                    };

                    add_grad(upper_poly_idx, 1.0, p_upper);
                    add_grad(lower_poly_idx, -1.0, p_lower);

                    let axis_poly_idx = if best_axis_idx < nsi { i } else { j };
                    let delta_x = p_upper.0 - p_lower.0;
                    let delta_y = p_upper.1 - p_lower.1;
                    let d_axis_drot_x = -y_axis;
                    let d_axis_drot_y = x_axis;
                    let d_overlap_drot_axis = delta_x * d_axis_drot_x + delta_y * d_axis_drot_y;
                    grad[axis_poly_idx * 3 + 2] += term * d_overlap_drot_axis;
                }
            }
        }
    }

    (penalty, grad)
}
"""

code += penalty_and_gradient_str

with open("packer_rs/src/main.rs", "w") as f:
    f.write(code)
print("Rust optimization script generated and run successfully.")
