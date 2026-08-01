#![allow(non_snake_case)]

use clap::Parser;
use rand::Rng;
use rand_chacha::{ChaCha8Rng, rand_core::SeedableRng};
use rayon::prelude::*;
use std::f64::consts::PI;
use std::fs;
use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Parser, Debug)]
#[command(name = "packer_rs", about = "Fast polygon packing solver")]
struct Args {
    inner_polygons: usize,
    inner_shape: String,
    container_shape: String,

    #[arg(long, default_value_t = 1000)]
    attempts: usize,

    #[arg(long, default_value_t = 1e-30)]
    tolerance: f64,

    #[arg(long, default_value_t = 0.0001)]
    finalstep: f64,

    #[arg(long)]
    time_limit: Option<f64>,

    /// If provided, write best solution (S, values) as JSON to this path.
    #[arg(long)]
    solution_file: Option<String>,

    /// If provided, use these initial positions for optimization
    #[arg(long)]
    initial_positions: Option<String>,

    /// Optional target S to aggressively short-circuit optimization runs
    #[arg(long)]
    target_s: Option<f64>,
}

fn main() {
    let args = Args::parse();
    let inner_token = args.inner_shape;
    let container_token = args.container_shape;
    let attempts = args.attempts;
    let _penalty_tolerance = args.tolerance;
    let final_step_size = args.finalstep;
    let solution_file = args.solution_file.clone();

    let start = Instant::now();
    let stop_flag = Arc::new(AtomicBool::new(false));

    if let Some(limit) = args.time_limit {
        let flag = Arc::clone(&stop_flag);
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs_f64(limit));
            flag.store(true, Ordering::Relaxed);
        });
    }

    let (nsi, unit_polygon_vertices, unit_polygon_vectors, _) = get_shape_geometry(&inner_token);
    let (nsc, _, unit_container_vectors, unit_container_apothem) = get_shape_geometry(&container_token);

    let best_s = Arc::new(Mutex::new(f64::INFINITY));
    let best_x = Arc::new(Mutex::new(None::<Vec<f64>>));

    let N_f64 = args.inner_polygons as f64;

    let initial_positions = if let Some(path) = &args.initial_positions {
        let contents = fs::read_to_string(path).expect("Failed to read initial positions file");
        let positions: Vec<f64> = serde_json::from_str(&contents).expect("Invalid JSON in initial positions");
        if positions.len() != args.inner_polygons * 3 {
            panic!("initial_positions must have length N * 3 (expected {}, got {})", args.inner_polygons * 3, positions.len());
        }
        Some(positions)
    } else {
        None
    };

    let target_s = args.target_s;

    (0..attempts)
        .into_par_iter()
        .for_each_with(
            (
                &stop_flag,
                &start,
                &unit_polygon_vertices,
                &unit_polygon_vectors,
                &unit_container_vectors,
                &unit_container_apothem,
                &best_s,
                &best_x,
                N_f64,
                &initial_positions,
                &target_s,
            ),
            |(stop, start, upv, upvectors, ucv, uap, best_s, best_x, N_f64, initial_positions, target_s), seed| {
                let mut rng = ChaCha8Rng::seed_from_u64(seed as u64);
                let (s, x) = run_attempt(
                    &mut rng,
                    *N_f64,
                    nsi,
                    nsc,
                    upv,
                    upvectors,
                    ucv,
                    **uap,
                    _penalty_tolerance,
                    final_step_size,
                    start,
                    stop,
                    args.time_limit,
                    (*initial_positions).as_ref(),
                    **target_s,
                );
                if s.is_finite() && x.is_some() {
                    loop {
                        let current = {
                            let cur = best_s.lock().unwrap();
                            *cur
                        };
                        if s >= current {
                            break;
                        }
                        {
                            let mut best = best_s.lock().unwrap();
                            if s >= *best {
                                break;
                            }
                            *best = s;
                        }
                        {
                            let mut bx = best_x.lock().unwrap();
                            *bx = x.clone();
                        }
                        break;
                    }
                }
            },
        );

    let bx = best_x.lock().unwrap();
    if let Some(ref bx) = *bx {
        let best = best_s.lock().unwrap();
        let container_upper = container_token.trim().to_uppercase();
        let inner_upper = inner_token.trim().to_uppercase();
        
        let c_metric = match container_upper.as_str() {
            "CIRCLE" | "CIR" | "TAN" | "DOMINO" | "L" => *best,
            _ => {
                if let Ok(nsc) = container_upper.parse::<usize>() {
                    2.0 * *best * (PI / nsc as f64).sin()
                } else {
                    2.0 * *best * (PI / 3.0).sin()
                }
            }
        };

        let i_scale = match inner_upper.as_str() {
            "CIRCLE" | "CIR" | "TAN" | "DOMINO" | "L" => 1.0,
            _ => {
                if let Ok(nsi) = inner_upper.parse::<usize>() {
                    2.0 * (PI / nsi as f64).sin()
                } else {
                    2.0 * (PI / 3.0).sin()
                }
            }
        };

        let final_metric = c_metric / i_scale;
        println!("Final side length: {}", final_metric);

        // Write solution JSON if requested
        if let Some(path) = &solution_file {
            let json = serde_json_to_string(bx, *best, &inner_token, &container_token, final_metric);
            if let Ok(mut f) = fs::File::create(path) {
                let _ = f.write_all(json.as_bytes());
            }
        }
    } else {
        println!("No valid packing found.");
    }
}

fn serde_json_to_string(
    values: &[f64],
    S: f64,
    inner_token: &str,
    container_token: &str,
    final_metric: f64,
) -> String {
    let N = values.len() / 3;
    let mut buf = String::new();
    buf.push_str("{\n");
    buf.push_str(&format!("  \"S\": {},\n", S));
    buf.push_str(&format!("  \"inner_token\": \"{}\",\n", inner_token));
    buf.push_str(&format!("  \"container_token\": \"{}\",\n", container_token));
    buf.push_str(&format!("  \"final_metric\": {},\n", final_metric));
    buf.push_str(&format!("  \"N\": {},\n", N));
    buf.push_str("  \"values\": [");
    for v in values.iter() {
        buf.push_str(&format!("{}", v));
        buf.push(',');
    }
    // Remove last comma
    if buf.ends_with(',') {
        buf.pop();
    }
    buf.push_str("]\n}\n");
    buf
}

// NOTE: Module alignment with Python optimization.py and geometry.py (design only)
//
// This Rust crate currently keeps optimization+geometry in one file.
// As optimization logic deepens, align structure to the Python modules:
//
// - geometry.py:
//   - regular_polygon          -> regular_polygon_vertices
//   - regular_polygon_vectors  -> regular_polygon_outward_normals
//   - transform + penalty internals
//                             -> _transform_polygon_nb, _rotate_vectors_nb, _poking_penalty_nb, bh_objective
//
// - optimization.py:
//   - PackingProblem              -> (inner_polygons, inner_sides, container_sides)
//   - OptConfig                   -> (attempts, tolerance, finalstep, time_limit)
//   - build_objective(problem)    -> objective + geometry constants
//   - run_single_attempt(...)     -> run_attempt(...)
//   - run_all_attempts(...)       -> parallel loop in main + best-S/x tracking
//
// For future unification, keep:
// - same formulas
// - same tolerance/SAT approach (see sat_check_overlap in geometry.py)
// - same semantic meaning of S, N, nsi, nsc

fn regular_polygon(radius: f64, sides: usize) -> Vec<(f64, f64)> {
    (0..sides)
        .map(|i| {
            let theta = 2.0 * PI * i as f64 / sides as f64;
            (radius * theta.cos(), radius * theta.sin())
        })
        .collect()
}

fn regular_polygon_vectors(radius: f64, sides: usize) -> Vec<(f64, f64)> {
    (0..sides)
        .map(|i| {
            let theta = 2.0 * PI * i as f64 / sides as f64 + PI / sides as f64;
            (radius * theta.cos(), radius * theta.sin())
        })
        .collect()
}

fn get_shape_geometry(token: &str) -> (usize, Vec<(f64, f64)>, Vec<(f64, f64)>, f64) {
    if token.to_uppercase() == "DOMINO" {
        let n = 4;
        let vertices = vec![(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5)];
        let vectors = vec![(0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)];
        let apothem = 0.5;
        return (n, vertices, vectors, apothem);
    }
    
    if token.to_uppercase() == "TAN" {
        let n = 3;
        let r = 1.0 - (2.0f64).sqrt() / 2.0;
        let vertices = vec![(-r, -r), (1.0 - r, -r), (-r, 1.0 - r)];
        let vectors = vec![(0.0, -1.0), ((2.0f64).sqrt() / 2.0, (2.0f64).sqrt() / 2.0), (-1.0, 0.0)];
        let apothem = r;
        return (n, vertices, vectors, apothem);
    }
    
    // Fallback to numeric parsing
    let sides: usize = token.parse().unwrap_or(3);
    let radius = 1.0;
    let vertices = regular_polygon(radius, sides);
    let vectors = regular_polygon_vectors(radius, sides);
    let apothem = (PI / sides as f64).cos();
    
    (sides, vertices, vectors, apothem)
}

fn run_attempt<R: Rng>(
    rng: &mut R,
    N_f64: f64,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &[(f64, f64)],
    unit_polygon_vectors: &[(f64, f64)],
    unit_container_vectors: &[(f64, f64)],
    unit_container_apothem: f64,
    _penalty_tolerance: f64,
    final_step_size: f64,
    start: &Instant,
    stop_flag: &AtomicBool,
    time_limit: Option<f64>,
    initial_positions: Option<&Vec<f64>>,
    target_s: Option<f64>,
) -> (f64, Option<Vec<f64>>) {
    if stop_flag.load(Ordering::Relaxed) {
        return (f64::INFINITY, None);
    }

    let mut dynamic_s = N_f64.sqrt() * (2.0 + rng.gen::<f64>() * 2.0);
    if let Some(ts) = target_s {
        // Funnel approach: start 5% larger than the target
        dynamic_s = ts * 1.05;
    }
    
    let lowest_s = N_f64.sqrt();
    let range_val = dynamic_s - lowest_s;

    let N = N_f64 as usize;

    let mut x0: Vec<f64> = if let Some(init_pos) = initial_positions {
        init_pos.iter().map(|&v| v + (rng.gen::<f64>() - 0.5) * 1e-5).collect()
    } else if rng.gen_bool(0.5) {
        (0..(N * 3))
            .map(|_| {
                let lo = -dynamic_s / 2.0;
                let hi = dynamic_s / 2.0;
                lo + (hi - lo) * rng.gen::<f64>()
            })
            .collect()
    } else {
        let grid_size = (N as f64).sqrt().ceil() as usize;
        let grid_size = grid_size.max(1);
        let mut grid = Vec::new();
        for _y in 0..grid_size {
            for _x in 0..grid_size {
                let x = -dynamic_s / 2.0 * 0.9
                    + (dynamic_s * 0.9) * (_x as f64) / (grid_size.max(1) - 1) as f64;
                let y = -dynamic_s / 2.0 * 0.9
                    + (dynamic_s * 0.9) * (_y as f64) / (grid_size.max(1) - 1) as f64;
                grid.push((x, y));
            }
        }
        let mut out = vec![0.0f64; N * 3];
        for i in 0..N {
            out[i * 3] = grid[i].0;
            out[i * 3 + 1] = grid[i].1;
            out[i * 3 + 2] = 2.0 * PI * rng.gen::<f64>();
        }
        out
    };

    let mut last_valid_x = x0.clone();
    let mut last_valid_s = dynamic_s;
    let mut current_s = dynamic_s;

    loop {
        if stop_flag.load(Ordering::Relaxed)
            || start.elapsed().as_secs_f64() > time_limit.unwrap_or(280.0)
        {
            break;
        }

        let minimized = minimize_gradient(
            &x0,
            current_s,
            N,
            nsi,
            nsc,
            unit_polygon_vertices,
            unit_polygon_vectors,
            unit_container_vectors,
            unit_container_apothem,
        );

        // Fix 3: Clamp multiplier so it never exceeds (1 - final_step_size) even when
        // current_s dips below lowest_s (negative term would otherwise inflate multiplier).
        let raw_multiplier = 1.0
            - final_step_size
            - (current_s - lowest_s) * (0.01 - final_step_size) / range_val;
        let multiplier = raw_multiplier.min(1.0 - final_step_size);

        if minimized.max_violation <= 1e-15 {
            let new_x = minimized.x;
            last_valid_x = new_x.clone();
            last_valid_s = current_s;
            x0 = new_x
                .iter()
                .map(|&v| v * multiplier)
                .collect::<Vec<_>>();
            current_s *= multiplier;
        } else {
            // Fix 1: Try up to 10 perturbations before giving up (was 1).
            // Extra retries are critical for tight packings where shapes need
            // many random nudges to escape local minima at small S.
            let mut resolved = false;
            for _ in 0..10 {
                let mut x_pert = x0.clone();
                for v in x_pert.iter_mut() {
                    *v += (rng.gen::<f64>() - 0.5) * 0.12;
                }
                let bh_res = minimize_gradient(
                    &x_pert,
                    current_s,
                    N,
                    nsi,
                    nsc,
                    unit_polygon_vertices,
                    unit_polygon_vectors,
                    unit_container_vectors,
                    unit_container_apothem,
                );
                if bh_res.max_violation <= 1e-15 {
                    let new_x = bh_res.x;
                    last_valid_x = new_x.clone();
                    last_valid_s = current_s;
                    x0 = new_x
                        .iter()
                        .map(|&v| v * multiplier)
                        .collect::<Vec<_>>();
                    current_s *= multiplier;
                    resolved = true;
                    break;
                }
            }
            if !resolved {
                if let Some(ts) = target_s {
                    if current_s >= ts {
                        // Stuck early! Abort without returning a valid packing
                        return (f64::INFINITY, None);
                    }
                }
                break;
            }
        }
    }

    (last_valid_s, Some(last_valid_x))
}

struct OptResult {
    x: Vec<f64>,
    _fun: f64,
    max_violation: f64,
}

fn minimize_gradient(
    x0: &[f64],
    S: f64,
    N: usize,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &[(f64, f64)],
    unit_polygon_vectors: &[(f64, f64)],
    unit_container_vectors: &[(f64, f64)],
    unit_container_apothem: f64,
) -> OptResult {
    let n = x0.len();
    let mut x = x0.to_vec();
    let mut best_x = x.clone();
    let (mut best_fun, _, mut best_max_violation) = penalty_and_gradient(
        &x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, false
    );

    let mut m = vec![0.0f64; n];
    let mut v = vec![0.0f64; n];
    let beta1 = 0.9f64;
    let beta2 = 0.999f64;
    let epsilon = 1e-8f64;
    let alpha = 0.02f64; // learning rate

    // Fix 1: Increased from 800 to 3000 iterations. Empirical testing shows the
    // convergence cliff for tight packings (especially sharp shapes like triangles)
    // hits at S~1.6 with 800 iters but resolves consistently with 3000 iters.
    for iter in 1..=3000 {
        let (_, grad, _) = penalty_and_gradient(
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

        let (new_fx, _, new_max_violation) = penalty_and_gradient(
            &new_x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, false
        );

        x = new_x;
        if new_fx < best_fun {
            best_fun = new_fx;
            best_x = x.clone();
            best_max_violation = new_max_violation;
        }
    }

    OptResult { x: best_x, _fun: best_fun, max_violation: best_max_violation }
}


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
) -> (f64, Vec<f64>, f64) {
    let mut penalty = 0.0f64;
    let mut grad = if compute_grad { vec![0.0f64; values.len()] } else { vec![] };
    let mut max_violation = 0.0f64;

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
                    if diff > max_violation {
                        max_violation = diff;
                    }

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
                if min_overlap > max_violation {
                    max_violation = min_overlap;
                }

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

                    let (p_upper, _v_upper_idx, upper_poly_idx) = if max_1 < max_2 {
                        (p1_max, best_v1_max, i)
                    } else {
                        (p2_max, best_v2_max, j)
                    };

                    let (p_lower, _v_lower_idx, lower_poly_idx) = if min_1 > min_2 {
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

    (penalty, grad, max_violation)
}
