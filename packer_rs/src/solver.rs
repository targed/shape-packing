#![allow(non_snake_case)]

use rand::Rng;
use rand_chacha::{ChaCha8Rng, rand_core::SeedableRng};
use rayon::prelude::*;
use std::f64::consts::PI;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct SolveConfig {
    pub inner_polygons: usize,
    pub inner_shape: String,
    pub container_shape: String,
    pub attempts: usize,
    pub tolerance: f64,
    pub finalstep: f64,
    pub time_limit: Option<f64>,
    pub initial_positions: Option<Vec<f64>>,
    pub target_s: Option<f64>,
}

impl Default for SolveConfig {
    fn default() -> Self {
        Self {
            inner_polygons: 5,
            inner_shape: "3".to_string(),
            container_shape: "4".to_string(),
            attempts: 1000,
            tolerance: 1e-30,
            finalstep: 0.0001,
            time_limit: None,
            initial_positions: None,
            target_s: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct SolveResult {
    pub success: bool,
    pub best_s: f64,
    pub final_metric: f64,
    pub values: Vec<f64>,
    pub inner_token: String,
    pub container_token: String,
}

pub fn solve(config: &SolveConfig) -> SolveResult {
    let start = Instant::now();
    let stop_flag = Arc::new(AtomicBool::new(false));

    if let Some(limit) = config.time_limit {
        let flag = Arc::clone(&stop_flag);
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs_f64(limit));
            flag.store(true, Ordering::Relaxed);
        });
    }

    let (nsi, unit_polygon_vertices, unit_polygon_vectors, _) = get_shape_geometry(&config.inner_shape);
    let (nsc, _, unit_container_vectors, unit_container_apothem) = get_shape_geometry(&config.container_shape);

    let best_s = Arc::new(Mutex::new(f64::INFINITY));
    let best_x = Arc::new(Mutex::new(None::<Vec<f64>>));

    let N_f64 = config.inner_polygons as f64;
    let is_inner_circle = config.inner_shape.to_uppercase() == "CIRCLE" || config.inner_shape.to_uppercase() == "CIR";
    let is_container_circle = config.container_shape.to_uppercase() == "CIRCLE" || config.container_shape.to_uppercase() == "CIR";
    let is_inner_l = config.inner_shape.to_uppercase() == "L";
    let is_container_l = config.container_shape.to_uppercase() == "L";

    (0..config.attempts)
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
                &config.initial_positions,
                &config.target_s,
                is_inner_circle,
                is_container_circle,
                is_inner_l,
                is_container_l,
            ),
            |(stop, start, upv, upvectors, ucv, uap, best_s, best_x, N_f64, initial_positions, target_s, is_inner_circle, is_container_circle, is_inner_l, is_container_l), seed| {
                let mut rng = ChaCha8Rng::seed_from_u64(seed as u64);
                let (s, x) = run_attempt(
                    &mut rng,
                    *N_f64,
                    nsi,
                    nsc,
                    upv,
                    upvectors,
                    ucv,
                    uap,
                    config.tolerance,
                    config.finalstep,
                    start,
                    stop,
                    config.time_limit,
                    (*initial_positions).as_ref(),
                    **target_s,
                    *is_inner_circle,
                    *is_container_circle,
                    *is_inner_l,
                    *is_container_l,
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
        let container_upper = config.container_shape.trim().to_uppercase();
        let inner_upper = config.inner_shape.trim().to_uppercase();
        
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
        SolveResult {
            success: true,
            best_s: *best,
            final_metric,
            values: bx.clone(),
            inner_token: config.inner_shape.clone(),
            container_token: config.container_shape.clone(),
        }
    } else {
        SolveResult {
            success: false,
            best_s: f64::INFINITY,
            final_metric: f64::INFINITY,
            values: Vec::new(),
            inner_token: config.inner_shape.clone(),
            container_token: config.container_shape.clone(),
        }
    }
}

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

pub fn get_shape_geometry(token: &str) -> (usize, Vec<(f64, f64)>, Vec<(f64, f64)>, Vec<f64>) {
    if token.to_uppercase() == "DOMINO" {
        let n = 4;
        let vertices = vec![(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5)];
        let vectors = vec![(0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)];
        let apothem = vec![0.5, 1.0, 0.5, 1.0];
        return (n, vertices, vectors, apothem);
    }
    
    if token.to_uppercase() == "TAN" {
        let n = 3;
        let r = 1.0 - (2.0f64).sqrt() / 2.0;
        let vertices = vec![(-r, -r), (1.0 - r, -r), (-r, 1.0 - r)];
        let vectors = vec![(0.0, -1.0), ((2.0f64).sqrt() / 2.0, (2.0f64).sqrt() / 2.0), (-1.0, 0.0)];
        let apothem = vec![r, r, r];
        return (n, vertices, vectors, apothem);
    }
    
    if token.to_uppercase() == "L" {
        let n = 6;
        let vertices = vec![
            (-5.0/6.0, -5.0/6.0),
            (7.0/6.0, -5.0/6.0),
            (7.0/6.0, 1.0/6.0),
            (1.0/6.0, 1.0/6.0),
            (1.0/6.0, 7.0/6.0),
            (-5.0/6.0, 7.0/6.0),
        ];
        let vectors = vec![
            (0.0, -1.0),
            (1.0, 0.0),
            (0.0, -1.0),
            (1.0, 0.0),
            (0.0, 1.0),
            (-1.0, 0.0),
        ];
        let apothem = vec![5.0/6.0, 7.0/6.0, 1.0/6.0, 1.0/6.0, 7.0/6.0, 5.0/6.0];
        return (n, vertices, vectors, apothem);
    }
    
    if token.to_uppercase() == "CIRCLE" || token.to_uppercase() == "CIR" {
        let sides = 32;
        let radius = 1.0;
        let vertices = regular_polygon(radius, sides);
        let vectors = regular_polygon_vectors(radius, sides);
        let apothem = vec![(PI / sides as f64).cos(); sides];
        return (sides, vertices, vectors, apothem);
    }
    
    let sides: usize = token.parse().unwrap_or(3);
    let radius = 1.0;
    let vertices = regular_polygon(radius, sides);
    let vectors = regular_polygon_vectors(radius, sides);
    let apothem = vec![(PI / sides as f64).cos(); sides];
    
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
    unit_container_apothem: &[f64],
    _penalty_tolerance: f64,
    final_step_size: f64,
    start: &Instant,
    stop_flag: &AtomicBool,
    time_limit: Option<f64>,
    initial_positions: Option<&Vec<f64>>,
    target_s: Option<f64>,
    is_inner_circle: bool,
    is_container_circle: bool,
    is_inner_l: bool,
    is_container_l: bool,
) -> (f64, Option<Vec<f64>>) {
    if stop_flag.load(Ordering::Relaxed) {
        return (f64::INFINITY, None);
    }

    let mut dynamic_s = N_f64.sqrt() * (2.0 + rng.gen::<f64>() * 2.0);
    if let Some(ts) = target_s {
        dynamic_s = ts * 1.05;
    }
    
    let lowest_s = N_f64.sqrt();
    let range_val = dynamic_s - lowest_s;

    let N = N_f64 as usize;

    let mut polygon_array = vec![(0.0, 0.0); N * nsi];
    let mut vector_array = vec![(0.0, 0.0); N * nsi];
    let mut grad_buffer = vec![0.0f64; N * 3];
    let mut bbox_array = vec![(0.0f64, 0.0f64, 0.0f64, 0.0f64); N];
    let mut sort_indices = vec![0usize; N];

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
        let mut grid = Vec::new();
        if grid_size <= 1 {
            grid.push((0.0, 0.0));
        } else {
            for _y in 0..grid_size {
                for _x in 0..grid_size {
                    let x = -dynamic_s / 2.0 * 0.9
                        + (dynamic_s * 0.9) * (_x as f64) / (grid_size - 1) as f64;
                    let y = -dynamic_s / 2.0 * 0.9
                        + (dynamic_s * 0.9) * (_y as f64) / (grid_size - 1) as f64;
                    grid.push((x, y));
                }
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

    let mut last_valid_x: Option<Vec<f64>> = None;
    let mut last_valid_s = f64::INFINITY;
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
            is_inner_circle,
            is_container_circle,
            is_inner_l,
            is_container_l,
            &mut polygon_array,
            &mut vector_array,
            &mut grad_buffer,
            &mut bbox_array,
            &mut sort_indices,
        );

        let raw_multiplier = 1.0
            - final_step_size
            - (current_s - lowest_s) * (0.01 - final_step_size) / range_val;
        let multiplier = raw_multiplier.min(1.0 - final_step_size);

        if minimized.max_violation <= 1e-15 {
            let new_x = minimized.x;
            last_valid_x = Some(new_x.clone());
            last_valid_s = current_s;
            x0 = new_x
                .iter()
                .map(|&v| v * multiplier)
                .collect::<Vec<_>>();
            current_s *= multiplier;
        } else {
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
                    is_inner_circle,
                    is_container_circle,
                    is_inner_l,
                    is_container_l,
                    &mut polygon_array,
                    &mut vector_array,
                    &mut grad_buffer,
                    &mut bbox_array,
                    &mut sort_indices,
                );
                if bh_res.max_violation <= 1e-15 {
                    let new_x = bh_res.x;
                    last_valid_x = Some(new_x.clone());
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
                        return (f64::INFINITY, None);
                    }
                }
                break;
            }
        }
    }

    (last_valid_s, last_valid_x)
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
    unit_container_apothem: &[f64],
    is_inner_circle: bool,
    is_container_circle: bool,
    is_inner_l: bool,
    is_container_l: bool,
    polygon_array: &mut [(f64, f64)],
    vector_array: &mut [(f64, f64)],
    grad_buffer: &mut [f64],
    bbox_array: &mut [(f64, f64, f64, f64)],
    sort_indices: &mut [usize],
) -> OptResult {
    let n = x0.len();
    let mut x = x0.to_vec();
    let mut best_x = x.clone();
    let (mut best_fun, mut best_max_violation) = penalty_and_gradient(
        &x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, is_inner_circle, is_container_circle, is_inner_l, is_container_l, false, polygon_array, vector_array, grad_buffer, bbox_array, sort_indices
    );

    let mut m = vec![0.0f64; n];
    let mut v = vec![0.0f64; n];
    let beta1 = 0.9f64;
    let beta2 = 0.999f64;
    let epsilon = 1e-8f64;
    let alpha = 0.02f64;

    let mut no_improve: u32 = 0;
    let mut best_fun_iter = f64::INFINITY;
    let mut beta1_t = beta1;
    let mut beta2_t = beta2;

    for _iter in 1..=3000 {
        let (fun, _max_violation) = penalty_and_gradient(
            &x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, is_inner_circle, is_container_circle, is_inner_l, is_container_l, true, polygon_array, vector_array, grad_buffer, bbox_array, sort_indices
        );

        if fun < best_fun_iter * 0.9999 {
            no_improve = 0;
            best_fun_iter = fun;
        } else {
            no_improve += 1;
        }
        if no_improve >= 300 {
            break;
        }

        let mut new_x = vec![0.0f64; n];
        for i in 0..n {
            m[i] = beta1 * m[i] + (1.0 - beta1) * grad_buffer[i];
            v[i] = beta2 * v[i] + (1.0 - beta2) * grad_buffer[i] * grad_buffer[i];

            let m_hat = m[i] / (1.0 - beta1_t);
            let v_hat = v[i] / (1.0 - beta2_t);

            new_x[i] = x[i] - alpha * m_hat / (v_hat.sqrt() + epsilon);
        }

        beta1_t *= beta1;
        beta2_t *= beta2;

        let (new_fx, new_max_violation) = penalty_and_gradient(
            &new_x, S, N, nsi, nsc, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem, is_inner_circle, is_container_circle, is_inner_l, is_container_l, false, polygon_array, vector_array, grad_buffer, bbox_array, sort_indices
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
    unit_container_apothem: &[f64],
    is_inner_circle: bool,
    is_container_circle: bool,
    is_inner_l: bool,
    is_container_l: bool,
    compute_grad: bool,
    polygon_array: &mut [(f64, f64)],
    vector_array: &mut [(f64, f64)],
    grad: &mut [f64],
    bbox_array: &mut [(f64, f64, f64, f64)],
    sort_indices: &mut [usize],
) -> (f64, f64) {
    let mut penalty = 0.0f64;
    if compute_grad {
        grad.fill(0.0);
    }
    let mut max_violation = 0.0f64;

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

        if is_container_circle {
            if is_inner_circle {
                let dist_sq = posx * posx + posy * posy;
                let dist = dist_sq.sqrt();
                let limit = S - 1.0;
                if dist > limit {
                    let diff = dist - limit;
                    penalty += diff * diff;
                    if diff > max_violation { max_violation = diff; }
                    if compute_grad {
                        let term = 2.0 * diff;
                        let nx = if dist > 1e-12 { posx / dist } else { 1.0 };
                        let ny = if dist > 1e-12 { posy / dist } else { 0.0 };
                        grad[i * 3] += term * nx;
                        grad[i * 3 + 1] += term * ny;
                    }
                }
            } else {
                let limit = S;
                for v in 0..nsi {
                    let (tx, ty) = polygon_array[i * nsi + v];
                    let dist_sq = tx*tx + ty*ty;
                    let dist = dist_sq.sqrt();
                    if dist > limit {
                        let diff = dist - limit;
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            let term = 2.0 * diff;
                            let dx_drot = -(ty - posy);
                            let dy_drot = tx - posx;
                            let nx = if dist > 1e-12 { tx / dist } else { 1.0 };
                            let ny = if dist > 1e-12 { ty / dist } else { 0.0 };
                            
                            grad[i * 3] += term * nx;
                            grad[i * 3 + 1] += term * ny;
                            grad[i * 3 + 2] += term * (nx * dx_drot + ny * dy_drot);
                        }
                    }
                }
            }
        } else if is_container_l {
            let x_min = -5.0 / 6.0 * S;
            let x_max = 7.0 / 6.0 * S;
            let y_min = -5.0 / 6.0 * S;
            let y_max = 7.0 / 6.0 * S;
            let cut_min_x = 1.0 / 6.0 * S;
            let cut_min_y = 1.0 / 6.0 * S;

            if is_inner_circle {
                let r = 1.0;
                if posx < x_min + r {
                    let diff = (x_min + r) - posx;
                    penalty += diff * diff;
                    if diff > max_violation { max_violation = diff; }
                    if compute_grad { grad[i * 3] -= 2.0 * diff; }
                }
                if posx > x_max - r {
                    let diff = posx - (x_max - r);
                    penalty += diff * diff;
                    if diff > max_violation { max_violation = diff; }
                    if compute_grad { grad[i * 3] += 2.0 * diff; }
                }
                if posy < y_min + r {
                    let diff = (y_min + r) - posy;
                    penalty += diff * diff;
                    if diff > max_violation { max_violation = diff; }
                    if compute_grad { grad[i * 3 + 1] -= 2.0 * diff; }
                }
                if posy > y_max - r {
                    let diff = posy - (y_max - r);
                    penalty += diff * diff;
                    if diff > max_violation { max_violation = diff; }
                    if compute_grad { grad[i * 3 + 1] += 2.0 * diff; }
                }

                if posx > cut_min_x - r && posy > cut_min_y - r {
                    if posx >= cut_min_x && posy >= cut_min_y {
                        let dx = posx - cut_min_x + r;
                        let dy = posy - cut_min_y + r;
                        let (diff, push_x) = if dx < dy { (dx, true) } else { (dy, false) };
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            if push_x { grad[i * 3] += 2.0 * diff; }
                            else { grad[i * 3 + 1] += 2.0 * diff; }
                        }
                    } else if posx > cut_min_x {
                        let dist = cut_min_y - posy;
                        if dist < r {
                            let diff = r - dist;
                            penalty += diff * diff;
                            if diff > max_violation { max_violation = diff; }
                            if compute_grad { grad[i * 3 + 1] -= 2.0 * diff; }
                        }
                    } else if posy > cut_min_y {
                        let dist = cut_min_x - posx;
                        if dist < r {
                            let diff = r - dist;
                            penalty += diff * diff;
                            if diff > max_violation { max_violation = diff; }
                            if compute_grad { grad[i * 3] -= 2.0 * diff; }
                        }
                    } else {
                        let dx = posx - cut_min_x;
                        let dy = posy - cut_min_y;
                        let dist = (dx * dx + dy * dy).sqrt();
                        if dist < r {
                            let diff = r - dist;
                            penalty += diff * diff;
                            if diff > max_violation { max_violation = diff; }
                            if compute_grad {
                                let term = 2.0 * diff;
                                let nx = if dist > 1e-12 { dx / dist } else { 1.0 };
                                let ny = if dist > 1e-12 { dy / dist } else { 0.0 };
                                grad[i * 3] -= term * nx;
                                grad[i * 3 + 1] -= term * ny;
                            }
                        }
                    }
                }
            } else {
                for v in 0..nsi {
                    let (tx, ty) = polygon_array[i * nsi + v];
                    if tx < x_min {
                        let diff = x_min - tx;
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            let term = 2.0 * diff;
                            grad[i * 3] -= term;
                            grad[i * 3 + 2] += term * (ty - posy);
                        }
                    }
                    if tx > x_max {
                        let diff = tx - x_max;
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            let term = 2.0 * diff;
                            grad[i * 3] += term;
                            grad[i * 3 + 2] += term * -(ty - posy);
                        }
                    }
                    if ty < y_min {
                        let diff = y_min - ty;
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            let term = 2.0 * diff;
                            grad[i * 3 + 1] -= term;
                            grad[i * 3 + 2] += term * -(tx - posx);
                        }
                    }
                    if ty > y_max {
                        let diff = ty - y_max;
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            let term = 2.0 * diff;
                            grad[i * 3 + 1] += term;
                            grad[i * 3 + 2] += term * (tx - posx);
                        }
                    }
                }

                let r_cutout_pts = [
                    (cut_min_x, cut_min_y),
                    (x_max, cut_min_y),
                    (x_max, y_max),
                    (cut_min_x, y_max),
                ];

                let num_subparts = if is_inner_l { 2 } else { 1 };
                for sub_idx in 0..num_subparts {
                    let (sub_pts, sub_normals): (Vec<(f64, f64)>, Vec<(f64, f64)>) = if is_inner_l {
                        let rot_i = values[i * 3 + 2];
                        let sin_i = rot_i.sin();
                        let cos_i = rot_i.cos();
                        let p_split_i = (posx + (1.0/6.0 * cos_i - (-5.0/6.0) * sin_i), posy + (1.0/6.0 * sin_i + (-5.0/6.0) * cos_i));
                        let pts = if sub_idx == 0 {
                            vec![polygon_array[i * 6 + 0], p_split_i, polygon_array[i * 6 + 4], polygon_array[i * 6 + 5]]
                        } else {
                            vec![p_split_i, polygon_array[i * 6 + 1], polygon_array[i * 6 + 2], polygon_array[i * 6 + 3]]
                        };
                        let normals = vec![(cos_i, sin_i), (-sin_i, cos_i)];
                        (pts, normals)
                    } else {
                        let pts = (0..nsi).map(|v| polygon_array[i * nsi + v]).collect();
                        let normals = (0..nsi).map(|v| vector_array[i * nsi + v]).collect();
                        (pts, normals)
                    };

                    let mut axes = sub_normals;
                    axes.push((1.0, 0.0));
                    axes.push((0.0, 1.0));

                    let mut obstacle_collision = true;
                    let mut min_overlap = 1e30f64;
                    let mut best_axis = (0.0, 0.0);
                    let mut best_v_min = 0;
                    let mut best_v_max = 0;
                    let mut best_is_max = true;

                    for &(ax, ay) in axes.iter() {
                        let mut min_1 = 1e30f64;
                        let mut max_1 = -1e30f64;
                        let mut v1_min = 0;
                        let mut v1_max = 0;
                        for (v_idx, &(px, py)) in sub_pts.iter().enumerate() {
                            let dot = px * ax + py * ay;
                            if dot < min_1 { min_1 = dot; v1_min = v_idx; }
                            if dot > max_1 { max_1 = dot; v1_max = v_idx; }
                        }

                        let mut min_2 = 1e30f64;
                        let mut max_2 = -1e30f64;
                        for &(px, py) in r_cutout_pts.iter() {
                            let dot = px * ax + py * ay;
                            if dot < min_2 { min_2 = dot; }
                            if dot > max_2 { max_2 = dot; }
                        }

                        let overlap = max_1.min(max_2) - min_1.max(min_2);
                        if overlap <= 0.0 {
                            obstacle_collision = false;
                            break;
                        }
                        if overlap < min_overlap {
                            min_overlap = overlap;
                            best_axis = (ax, ay);
                            best_v_min = v1_min;
                            best_v_max = v1_max;
                            best_is_max = max_1 < max_2;
                        }
                    }

                    if obstacle_collision {
                        penalty += min_overlap * min_overlap;
                        if min_overlap > max_violation {
                            max_violation = min_overlap;
                        }
                        if compute_grad {
                            let term = 2.0 * min_overlap;
                            let (ax, ay) = best_axis;
                            if best_is_max {
                                let p = sub_pts[best_v_max];
                                let drot = -(p.1 - posy) * ax + (p.0 - posx) * ay;
                                grad[i * 3] += term * ax;
                                grad[i * 3 + 1] += term * ay;
                                grad[i * 3 + 2] += term * drot;
                            } else {
                                let p = sub_pts[best_v_min];
                                let drot = -(p.1 - posy) * ax + (p.0 - posx) * ay;
                                grad[i * 3] -= term * ax;
                                grad[i * 3 + 1] -= term * ay;
                                grad[i * 3 + 2] -= term * drot;
                            }
                        }
                    }
                }
            }
        } else {
            if is_inner_circle {
                for j in 0..nsc {
                    let limit = unit_container_apothem[j] * S - 1.0;
                    let (cx, cy) = unit_container_vectors[j];
                    let dist = posx * cx + posy * cy;
                    if dist > limit {
                        let diff = dist - limit;
                        penalty += diff * diff;
                        if diff > max_violation { max_violation = diff; }
                        if compute_grad {
                            let term = 2.0 * diff;
                            grad[i * 3] += term * cx;
                            grad[i * 3 + 1] += term * cy;
                        }
                    }
                }
            } else {
                for v in 0..nsi {
                    let (tx, ty) = polygon_array[i * nsi + v];
                    for j in 0..nsc {
                        let limit = unit_container_apothem[j] * S;
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
        }
    }

    let use_broadphase = N > 20 && !is_inner_circle;
    if use_broadphase {
        for i in 0..N {
            let mut min_x = 1e30f64;
            let mut max_x = -1e30f64;
            let mut min_y = 1e30f64;
            let mut max_y = -1e30f64;
            for v in 0..nsi {
                let (px, py) = polygon_array[i * nsi + v];
                if px < min_x { min_x = px; }
                if px > max_x { max_x = px; }
                if py < min_y { min_y = py; }
                if py > max_y { max_y = py; }
            }
            bbox_array[i] = (min_x, max_x, min_y, max_y);
            sort_indices[i] = i;
        }
        sort_indices.sort_unstable_by(|&a, &b| bbox_array[a].0.partial_cmp(&bbox_array[b].0).unwrap());
    }

    for idx_i in 0..N {
        let i = if use_broadphase { sort_indices[idx_i] } else { idx_i };
        let end_j = N;
        for idx_j in (idx_i + 1)..end_j {
            let j = if use_broadphase { sort_indices[idx_j] } else { idx_j };

            if use_broadphase {
                let b1 = bbox_array[i];
                let b2 = bbox_array[j];
                if b2.0 > b1.1 {
                    break;
                }
                if b1.2 > b2.3 || b1.3 < b2.2 {
                    continue;
                }
            }
            if is_inner_circle {
                let dx = values[j * 3] - values[i * 3];
                let dy = values[j * 3 + 1] - values[i * 3 + 1];
                let dist_sq = dx*dx + dy*dy;
                if dist_sq < 4.0 {
                    let dist = dist_sq.sqrt();
                    let diff = 2.0 - dist;
                    penalty += diff * diff;
                    if diff > max_violation { max_violation = diff; }
                    if compute_grad {
                        let term = 2.0 * diff;
                        let nx = if dist > 1e-12 { dx / dist } else { 1.0 };
                        let ny = if dist > 1e-12 { dy / dist } else { 0.0 };
                        
                        grad[i * 3] += term * nx;
                        grad[i * 3 + 1] += term * ny;
                        
                        grad[j * 3] -= term * nx;
                        grad[j * 3 + 1] -= term * ny;
                    }
                }
                continue;
            }

            if is_inner_l {
                let posx_i = values[i * 3];
                let posy_i = values[i * 3 + 1];
                let rot_i = values[i * 3 + 2];
                let sin_i = rot_i.sin();
                let cos_i = rot_i.cos();

                let posx_j = values[j * 3];
                let posy_j = values[j * 3 + 1];
                let rot_j = values[j * 3 + 2];
                let sin_j = rot_j.sin();
                let cos_j = rot_j.cos();

                let p_split_i = (posx_i + (1.0/6.0 * cos_i - (-5.0/6.0) * sin_i), posy_i + (1.0/6.0 * sin_i + (-5.0/6.0) * cos_i));
                let p_split_j = (posx_j + (1.0/6.0 * cos_j - (-5.0/6.0) * sin_j), posy_j + (1.0/6.0 * sin_j + (-5.0/6.0) * cos_j));

                let rects_i = [
                    [polygon_array[i * 6 + 0], p_split_i, polygon_array[i * 6 + 4], polygon_array[i * 6 + 5]],
                    [p_split_i, polygon_array[i * 6 + 1], polygon_array[i * 6 + 2], polygon_array[i * 6 + 3]],
                ];
                let rects_j = [
                    [polygon_array[j * 6 + 0], p_split_j, polygon_array[j * 6 + 4], polygon_array[j * 6 + 5]],
                    [p_split_j, polygon_array[j * 6 + 1], polygon_array[j * 6 + 2], polygon_array[j * 6 + 3]],
                ];

                let axes = [
                    (cos_i, sin_i),
                    (-sin_i, cos_i),
                    (cos_j, sin_j),
                    (-sin_j, cos_j),
                ];

                for ra in 0..2 {
                    let r1 = &rects_i[ra];
                    for rb in 0..2 {
                        let r2 = &rects_j[rb];
                        let mut sub_collision = true;
                        let mut sub_min_overlap = 1e30f64;
                        let mut sub_best_axis_idx = 0;
                        let mut sub_v1_min = 0;
                        let mut sub_v1_max = 0;
                        let mut sub_v2_min = 0;
                        let mut sub_v2_max = 0;

                        for (ax_idx, &(ax, ay)) in axes.iter().enumerate() {
                            let mut min_1 = 1e30f64;
                            let mut max_1 = -1e30f64;
                            let mut v1_min = 0;
                            let mut v1_max = 0;
                            for (v_idx, &(px, py)) in r1.iter().enumerate() {
                                let dot = px * ax + py * ay;
                                if dot < min_1 { min_1 = dot; v1_min = v_idx; }
                                if dot > max_1 { max_1 = dot; v1_max = v_idx; }
                            }

                            let mut min_2 = 1e30f64;
                            let mut max_2 = -1e30f64;
                            let mut v2_min = 0;
                            let mut v2_max = 0;
                            for (v_idx, &(px, py)) in r2.iter().enumerate() {
                                let dot = px * ax + py * ay;
                                if dot < min_2 { min_2 = dot; v2_min = v_idx; }
                                if dot > max_2 { max_2 = dot; v2_max = v_idx; }
                            }

                            let overlap = max_1.min(max_2) - min_1.max(min_2);
                            if overlap <= 0.0 {
                                sub_collision = false;
                                break;
                            }
                            if overlap < sub_min_overlap {
                                sub_min_overlap = overlap;
                                sub_best_axis_idx = ax_idx;
                                sub_v1_min = v1_min;
                                sub_v1_max = v1_max;
                                sub_v2_min = v2_min;
                                sub_v2_max = v2_max;
                            }
                        }

                        if sub_collision {
                            penalty += sub_min_overlap * sub_min_overlap;
                            if sub_min_overlap > max_violation {
                                max_violation = sub_min_overlap;
                            }

                            if compute_grad {
                                let term = 2.0 * sub_min_overlap;
                                let (ax, ay) = axes[sub_best_axis_idx];

                                let p1_max = r1[sub_v1_max];
                                let max_1 = p1_max.0 * ax + p1_max.1 * ay;
                                let p2_max = r2[sub_v2_max];
                                let max_2 = p2_max.0 * ax + p2_max.1 * ay;
                                let p1_min = r1[sub_v1_min];
                                let min_1 = p1_min.0 * ax + p1_min.1 * ay;
                                let p2_min = r2[sub_v2_min];
                                let min_2 = p2_min.0 * ax + p2_min.1 * ay;

                                let (p_upper, upper_poly_idx) = if max_1 < max_2 {
                                    (p1_max, i)
                                } else {
                                    (p2_max, j)
                                };

                                let (p_lower, lower_poly_idx) = if min_1 > min_2 {
                                    (p1_min, i)
                                } else {
                                    (p2_min, j)
                                };

                                let mut add_grad = |poly_idx: usize, sign: f64, p: (f64, f64)| {
                                    let posx = values[poly_idx * 3];
                                    let posy = values[poly_idx * 3 + 1];
                                    let dp_drot_x = -(p.1 - posy);
                                    let dp_drot_y = p.0 - posx;

                                    grad[poly_idx * 3] += term * sign * ax;
                                    grad[poly_idx * 3 + 1] += term * sign * ay;
                                    grad[poly_idx * 3 + 2] += term * sign * (dp_drot_x * ax + dp_drot_y * ay);
                                };

                                add_grad(upper_poly_idx, 1.0, p_upper);
                                add_grad(lower_poly_idx, -1.0, p_lower);
                            }
                        }
                    }
                }
                continue;
            }

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

    (penalty, max_violation)
}
