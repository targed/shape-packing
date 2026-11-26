#![allow(non_snake_case)]

use rand::Rng;
use rand_chacha::{ChaCha8Rng, rand_core::SeedableRng};
use rayon::prelude::*;
use std::f64::consts::PI;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
#[cfg(not(target_arch = "wasm32"))]
use std::time::Duration;

#[cfg(not(target_arch = "wasm32"))]
use std::time::Instant;

#[cfg(target_arch = "wasm32")]
#[derive(Debug, Clone, Copy)]
pub struct Instant(f64);

#[cfg(target_arch = "wasm32")]
impl Instant {
    pub fn now() -> Self {
        Instant(js_sys::Date::now())
    }
    pub fn elapsed(&self) -> Elapsed {
        Elapsed((js_sys::Date::now() - self.0) / 1000.0)
    }
}

#[cfg(target_arch = "wasm32")]
#[derive(Debug, Clone, Copy)]
pub struct Elapsed(f64);

#[cfg(target_arch = "wasm32")]
impl Elapsed {
    pub fn as_secs_f64(&self) -> f64 {
        self.0
    }
}

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

    let timer_state = Arc::new((std::sync::Mutex::new(false), std::sync::Condvar::new()));
    let mut timer_handle: Option<std::thread::JoinHandle<()>> = None;

    if let Some(limit) = config.time_limit.filter(|l| l.is_finite() && *l > 0.0) {
        let flag = Arc::clone(&stop_flag);
        let t_state = Arc::clone(&timer_state);
        #[cfg(not(target_arch = "wasm32"))]
        {
            timer_handle = Some(std::thread::spawn(move || {
                let (lock, cvar) = &*t_state;
                let mut finished = lock.lock().unwrap();
                let deadline = std::time::Instant::now() + Duration::from_secs_f64(limit);
                while !*finished {
                    let now = std::time::Instant::now();
                    if now >= deadline {
                        flag.store(true, Ordering::Relaxed);
                        break;
                    }
                    let (guard, wait_res) = cvar.wait_timeout(finished, deadline - now).unwrap();
                    finished = guard;
                    if wait_res.timed_out() && !*finished {
                        flag.store(true, Ordering::Relaxed);
                        break;
                    }
                }
            }));
        }
        #[cfg(target_arch = "wasm32")]
        let _ = (limit, flag, t_state);
    }

    let inner_norm = normalize_shape_token(&config.inner_shape);
    let container_norm = normalize_shape_token(&config.container_shape);
    if !is_supported_pair(&inner_norm, &container_norm) {
        return SolveResult {
            success: false,
            best_s: f64::INFINITY,
            final_metric: f64::INFINITY,
            values: Vec::new(),
            inner_token: config.inner_shape.clone(),
            container_token: config.container_shape.clone(),
        };
    }

    let is_inner_circle = inner_norm == "CIRCLE";
    let is_container_circle = container_norm == "CIRCLE";
    let is_inner_l = inner_norm == "L";
    let is_container_l = container_norm == "L";
    let container_mode: u8 = if is_container_circle {
        1
    } else if is_container_l {
        2
    } else if container_norm == "SEMICIRCLE" {
        3
    } else if container_norm == "QUADRANT" {
        4
    } else {
        0
    };

    let (nsi, unit_polygon_vertices, unit_polygon_vectors, _) = get_shape_geometry(&inner_norm);
    let (nsc, _, unit_container_vectors, unit_container_apothem) = if container_mode == 3 || container_mode == 4 {
        (0, Vec::new(), Vec::new(), Vec::new())
    } else {
        get_shape_geometry(&container_norm)
    };

    let best_s = Arc::new(Mutex::new(f64::INFINITY));
    let best_x = Arc::new(Mutex::new(None::<Vec<f64>>));

    let N_f64 = config.inner_polygons as f64;

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
                container_mode,
            ),
            |(stop, start, upv, upvectors, ucv, uap, best_s, best_x, N_f64, initial_positions, target_s, is_inner_circle, is_container_circle, is_inner_l, is_container_l, container_mode), seed| {
                let mut rng = ChaCha8Rng::seed_from_u64(seed as u64);
                let (s, x) = run_attempt_with_mode(
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
                    *container_mode,
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

    if let Some(handle) = timer_handle {
        let (lock, cvar) = &*timer_state;
        {
            let mut finished = lock.lock().unwrap();
            *finished = true;
        }
        cvar.notify_all();
        let _ = handle.join();
    }

    let bx = best_x.lock().unwrap();
    if let Some(ref bx) = *bx {
        let best = best_s.lock().unwrap();
        let final_metric = compute_friedman_metric(*best, &config.inner_shape, &config.container_shape);
        let success = config.target_s.map_or(true, |ts| *best < ts);
        SolveResult {
            success,
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

/// Normalize any shape alias to its canonical uppercase token.
pub fn normalize_shape_token(token: &str) -> String {
    match token.trim().to_uppercase().as_str() {
        "3" | "TRIANGLE" | "TRI" => "3".to_string(),
        "4" | "SQUARE" | "SQU" => "4".to_string(),
        "5" | "PENTAGON" | "PEN" => "5".to_string(),
        "6" | "HEXAGON" | "HEX" => "6".to_string(),
        "7" | "HEPTAGON" | "HEP" => "7".to_string(),
        "8" | "OCTAGON" | "OCT" => "8".to_string(),
        "9" | "NONAGON" | "NON" | "ENNEAGON" => "9".to_string(),
        "10" | "DECAGON" | "DEC" => "10".to_string(),
        "CIRCLE" | "CIR" | "CIRC" | "0" => "CIRCLE".to_string(),
        "DOMINO" | "DOM" => "DOMINO".to_string(),
        "TAN" | "TANGRAM" => "TAN".to_string(),
        "L" | "LTROMINO" | "L-TROMINO" | "L_TROMINO" => "L".to_string(),
        "SEMICIRCLE" | "SEMI" | "SEMIDISK" => "SEMICIRCLE".to_string(),
        "QUADRANT" | "QUAD" | "QUARTERCIRCLE" | "CIRCULAR_QUADRANT" => "QUADRANT".to_string(),
        "RHOMBUS" | "RHOM" | "DIAMOND" => "RHOMBUS".to_string(),
        "PARALLELOGRAM" | "PARA" | "PARALLELOGRAM_TAN" => "PARALLELOGRAM".to_string(),
        "TRAPEZOID" | "TRAP" | "TRAPEZIUM" => "TRAPEZOID".to_string(),
        other => other.to_string(),
    }
}

fn is_valid_single_shape(norm: &str) -> bool {
    matches!(
        norm,
        "CIRCLE"
            | "DOMINO"
            | "TAN"
            | "L"
            | "SEMICIRCLE"
            | "QUADRANT"
            | "RHOMBUS"
            | "PARALLELOGRAM"
            | "TRAPEZOID"
    ) || norm.parse::<usize>().map_or(false, |n| n >= 3)
}

pub fn is_supported_pair(inner_norm: &str, container_norm: &str) -> bool {
    if !is_valid_single_shape(inner_norm) || !is_valid_single_shape(container_norm) {
        return false;
    }
    if inner_norm == "SEMICIRCLE" || inner_norm == "QUADRANT" {
        return false;
    }
    if container_norm == "SEMICIRCLE" || container_norm == "QUADRANT" {
        return inner_norm == "CIRCLE";
    }
    true
}

/// Parses a polygon token (e.g., "TRIANGLE", "3", "HEPTAGON", "ENNEAGON") into its side count.
pub fn parse_polygon_sides(token: &str) -> usize {
    match normalize_shape_token(token).as_str() {
        "3" => 3,
        "4" => 4,
        "5" => 5,
        "6" => 6,
        "7" => 7,
        "8" => 8,
        "9" => 9,
        "10" => 10,
        other => other.parse().unwrap_or(3),
    }
}

/// Computes the published Erich Friedman metric s given the solver container circumradius S.
pub fn compute_friedman_metric(circumradius_s: f64, inner_shape: &str, container_shape: &str) -> f64 {
    let container_upper = normalize_shape_token(container_shape);
    let inner_upper = normalize_shape_token(inner_shape);

    // LinL special case: container L and inner L
    if container_upper == "L" && inner_upper == "L" {
        return circumradius_s;
    }

    let c_metric = match container_upper.as_str() {
        "CIRCLE" | "TAN" | "DOMINO" | "SEMICIRCLE" | "QUADRANT" | "RHOMBUS" | "PARALLELOGRAM" | "TRAPEZOID" => circumradius_s,
        "L" => 2.0 * circumradius_s,
        _ => 2.0 * circumradius_s * (PI / parse_polygon_sides(&container_upper) as f64).sin(),
    };

    let i_scale = match inner_upper.as_str() {
        "CIRCLE" | "TAN" | "DOMINO" | "L" | "SEMICIRCLE" | "QUADRANT" | "RHOMBUS" | "PARALLELOGRAM" | "TRAPEZOID" => 1.0,
        _ => 2.0 * (PI / parse_polygon_sides(&inner_upper) as f64).sin(),
    };

    c_metric / i_scale
}

/// Converts a published Erich Friedman metric s into the solver container circumradius S.
pub fn inverse_friedman_metric(friedman_s: f64, inner_shape: &str, container_shape: &str) -> f64 {
    let container_upper = normalize_shape_token(container_shape);
    let inner_upper = normalize_shape_token(inner_shape);

    // LinL special case: container L and inner L
    if container_upper == "L" && inner_upper == "L" {
        return friedman_s;
    }

    let i_scale = match inner_upper.as_str() {
        "CIRCLE" | "TAN" | "DOMINO" | "L" | "SEMICIRCLE" | "QUADRANT" | "RHOMBUS" | "PARALLELOGRAM" | "TRAPEZOID" => 1.0,
        _ => 2.0 * (PI / parse_polygon_sides(&inner_upper) as f64).sin(),
    };

    let c_metric = friedman_s * i_scale;

    match container_upper.as_str() {
        "CIRCLE" | "TAN" | "DOMINO" | "SEMICIRCLE" | "QUADRANT" | "RHOMBUS" | "PARALLELOGRAM" | "TRAPEZOID" => c_metric,
        "L" => c_metric / 2.0,
        _ => c_metric / (2.0 * (PI / parse_polygon_sides(&container_upper) as f64).sin()),
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
    let norm = normalize_shape_token(token);
    if norm == "DOMINO" {
        let n = 4;
        let vertices = vec![(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5)];
        let vectors = vec![(0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)];
        let apothem = vec![0.5, 1.0, 0.5, 1.0];
        return (n, vertices, vectors, apothem);
    }

    if norm == "TAN" {
        let n = 3;
        let r = 1.0 - (2.0f64).sqrt() / 2.0;
        let vertices = vec![(-r, -r), (1.0 - r, -r), (-r, 1.0 - r)];
        let vectors = vec![(0.0, -1.0), ((2.0f64).sqrt() / 2.0, (2.0f64).sqrt() / 2.0), (-1.0, 0.0)];
        let apothem = vec![r, r, r];
        return (n, vertices, vectors, apothem);
    }

    if norm == "L" {
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

    if norm == "RHOMBUS" {
        let s3_2 = 3.0f64.sqrt() / 2.0;
        let s3_4 = 3.0f64.sqrt() / 4.0;
        let vertices = vec![(s3_2, 0.0), (0.0, 0.5), (-s3_2, 0.0), (0.0, -0.5)];
        let vectors = vec![(0.5, s3_2), (-0.5, s3_2), (-0.5, -s3_2), (0.5, -s3_2)];
        let apothem = vec![s3_4, s3_4, s3_4, s3_4];
        return (4, vertices, vectors, apothem);
    }

    if norm == "PARALLELOGRAM" {
        let s2_2 = 2.0f64.sqrt() / 2.0;
        let s2_4 = 2.0f64.sqrt() / 4.0;
        let vertices = vec![(-3.0 * s2_4, -s2_4), (s2_4, -s2_4), (3.0 * s2_4, s2_4), (-s2_4, s2_4)];
        let vectors = vec![(0.0, -1.0), (s2_2, -s2_2), (0.0, 1.0), (-s2_2, s2_2)];
        let apothem = vec![s2_4, 0.5, s2_4, 0.5];
        return (4, vertices, vectors, apothem);
    }

    if norm == "TRAPEZOID" {
        let s3_2 = 3.0f64.sqrt() / 2.0;
        let s3_4 = 3.0f64.sqrt() / 4.0;
        let leg_ap = 3.0 * 3.0f64.sqrt() / 8.0;
        let vertices = vec![(-1.0, -s3_4), (1.0, -s3_4), (0.5, s3_4), (-0.5, s3_4)];
        let vectors = vec![(0.0, -1.0), (s3_2, 0.5), (0.0, 1.0), (-s3_2, 0.5)];
        let apothem = vec![s3_4, leg_ap, s3_4, leg_ap];
        return (4, vertices, vectors, apothem);
    }

    if norm == "CIRCLE" {
        let sides = 32;
        let radius = 1.0;
        let vertices = regular_polygon(radius, sides);
        let vectors = regular_polygon_vectors(radius, sides);
        let apothem = vec![(PI / sides as f64).cos(); sides];
        return (sides, vertices, vectors, apothem);
    }

    let sides: usize = norm.parse().unwrap_or(3).max(3);
    let radius = 1.0;
    let vertices = regular_polygon(radius, sides);
    let vectors = regular_polygon_vectors(radius, sides);
    let apothem = vec![(PI / sides as f64).cos(); sides];

    (sides, vertices, vectors, apothem)
}

pub fn run_attempt<R: Rng>(
    rng: &mut R,
    N_f64: f64,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &[(f64, f64)],
    unit_polygon_vectors: &[(f64, f64)],
    unit_container_vectors: &[(f64, f64)],
    unit_container_apothem: &[f64],
    penalty_tolerance: f64,
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
    let container_mode: u8 = if is_container_circle {
        1
    } else if is_container_l {
        2
    } else {
        0
    };
    run_attempt_with_mode(
        rng,
        N_f64,
        nsi,
        nsc,
        unit_polygon_vertices,
        unit_polygon_vectors,
        unit_container_vectors,
        unit_container_apothem,
        penalty_tolerance,
        final_step_size,
        start,
        stop_flag,
        time_limit,
        initial_positions,
        target_s,
        is_inner_circle,
        is_container_circle,
        is_inner_l,
        is_container_l,
        container_mode,
    )
}

pub fn run_attempt_with_mode<R: Rng>(
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
    container_mode: u8,
) -> (f64, Option<Vec<f64>>) {
    if stop_flag.load(Ordering::Relaxed) {
        return (f64::INFINITY, None);
    }

    let mut dynamic_s = N_f64.sqrt() * (2.0 + rng.gen::<f64>() * 2.0);
    if container_mode == 3 || container_mode == 4 {
        dynamic_s = N_f64.sqrt() * (2.5 + rng.gen::<f64>() * 2.5);
    }
    if initial_positions.is_some() {
        if let Some(ts) = target_s {
            dynamic_s = ts * 1.05;
        }
    }

    let lowest_s = (dynamic_s * 0.2).min(N_f64.sqrt().max(0.1));
    let range_val = (dynamic_s - lowest_s).max(0.01);

    let N = N_f64 as usize;

    let mut polygon_array = vec![(0.0, 0.0); N * nsi];
    let mut vector_array = vec![(0.0, 0.0); N * nsi];
    let mut grad_buffer = vec![0.0f64; N * 3];
    let mut bbox_array = vec![(0.0f64, 0.0f64, 0.0f64, 0.0f64); N];
    let mut sort_indices = vec![0usize; N];

    let mut x0: Vec<f64> = if let Some(init_pos) = initial_positions {
        init_pos.iter().map(|&v| v + (rng.gen::<f64>() - 0.5) * 1e-5).collect()
    } else if is_container_l {
        // L-container spans [-5/6 S, 7/6 S] x [-5/6 S, 7/6 S] with cutout at [1/6 S, 7/6 S]^2.
        let mut out = vec![0.0f64; N * 3];
        let pad = (1.0f64).min(dynamic_s * 0.1);
        for i in 0..N {
            let sq = i % 3;
            let (x_min, x_max, y_min, y_max) = match sq {
                1 => (-5.0 / 6.0 * dynamic_s + pad, 1.0 / 6.0 * dynamic_s - pad, 1.0 / 6.0 * dynamic_s + pad, 7.0 / 6.0 * dynamic_s - pad),
                2 => (1.0 / 6.0 * dynamic_s + pad, 7.0 / 6.0 * dynamic_s - pad, -5.0 / 6.0 * dynamic_s + pad, 1.0 / 6.0 * dynamic_s - pad),
                _ => (-5.0 / 6.0 * dynamic_s + pad, 1.0 / 6.0 * dynamic_s - pad, -5.0 / 6.0 * dynamic_s + pad, 1.0 / 6.0 * dynamic_s - pad),
            };
            let x = if x_max > x_min { x_min + (x_max - x_min) * rng.gen::<f64>() } else { (x_min + x_max) / 2.0 };
            let y = if y_max > y_min { y_min + (y_max - y_min) * rng.gen::<f64>() } else { (y_min + y_max) / 2.0 };
            out[i * 3] = x;
            out[i * 3 + 1] = y;
            out[i * 3 + 2] = 2.0 * PI * rng.gen::<f64>();
        }
        out
    } else if container_mode == 3 {
        // Semicircle: sample in upper half [-S/2, S/2] x [1.0, S*0.8]
        let mut out = vec![0.0f64; N * 3];
        let y_hi = (dynamic_s * 0.8).max(1.0);
        for i in 0..N {
            out[i * 3] = -dynamic_s * 0.5 + dynamic_s * rng.gen::<f64>();
            out[i * 3 + 1] = 1.0 + (y_hi - 1.0) * rng.gen::<f64>();
            out[i * 3 + 2] = 0.0;
        }
        out
    } else if container_mode == 4 {
        // Quadrant: sample in first quadrant [1.0, S*0.8] x [1.0, S*0.8]
        let mut out = vec![0.0f64; N * 3];
        let hi = (dynamic_s * 0.8).max(1.0);
        for i in 0..N {
            out[i * 3] = 1.0 + (hi - 1.0) * rng.gen::<f64>();
            out[i * 3 + 1] = 1.0 + (hi - 1.0) * rng.gen::<f64>();
            out[i * 3 + 2] = 0.0;
        }
        out
    } else if rng.gen_bool(0.5) {
        (0..(N * 3))
            .map(|idx| {
                if idx % 3 == 2 {
                    2.0 * PI * rng.gen::<f64>()
                } else {
                    let lo = -dynamic_s / 2.0;
                    let hi = dynamic_s / 2.0;
                    lo + (hi - lo) * rng.gen::<f64>()
                }
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
            container_mode,
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
                .enumerate()
                .map(|(idx, &v)| if idx % 3 != 2 { v * multiplier } else { v })
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
                    container_mode,
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
                        .enumerate()
                        .map(|(idx, &v)| if idx % 3 != 2 { v * multiplier } else { v })
                        .collect::<Vec<_>>();
                    current_s *= multiplier;
                    resolved = true;
                    break;
                }
            }
            if !resolved {
                if let Some(ts) = target_s {
                    if current_s >= ts {
                        return (last_valid_s, last_valid_x);
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

struct LbfgsHistory {
    m: usize,
    s_history: Vec<Vec<f64>>,
    y_history: Vec<Vec<f64>>,
    rho_history: Vec<f64>,
}

impl LbfgsHistory {
    fn new(m: usize) -> Self {
        Self {
            m,
            s_history: Vec::with_capacity(m),
            y_history: Vec::with_capacity(m),
            rho_history: Vec::with_capacity(m),
        }
    }

    fn push(&mut self, s: Vec<f64>, y: Vec<f64>) {
        let ys: f64 = s.iter().zip(y.iter()).map(|(a, b)| a * b).sum();
        let s_norm_sq: f64 = s.iter().map(|a| a * a).sum();
        // Curvature safeguard (Powell damping / positive definiteness condition)
        if ys > 1e-10 * (s_norm_sq + 1e-12) {
            if self.s_history.len() == self.m {
                self.s_history.remove(0);
                self.y_history.remove(0);
                self.rho_history.remove(0);
            }
            let rho = 1.0 / ys;
            self.s_history.push(s);
            self.y_history.push(y);
            self.rho_history.push(rho);
        }
    }

    fn compute_direction(&self, grad: &[f64]) -> Vec<f64> {
        let k = self.s_history.len();
        let n = grad.len();
        if k == 0 {
            return grad.iter().map(|g| -g).collect();
        }

        let mut q = grad.to_vec();
        let mut alphas = vec![0.0f64; k];

        // First loop (backward)
        for i in (0..k).rev() {
            let s = &self.s_history[i];
            let y = &self.y_history[i];
            let rho = self.rho_history[i];

            let sq: f64 = s.iter().zip(q.iter()).map(|(a, b)| a * b).sum();
            let alpha = rho * sq;
            alphas[i] = alpha;

            for j in 0..n {
                q[j] -= alpha * y[j];
            }
        }

        // Initial Hessian scaling gamma = (s_last . y_last) / (y_last . y_last)
        let s_last = &self.s_history[k - 1];
        let y_last = &self.y_history[k - 1];
        let sy: f64 = s_last.iter().zip(y_last.iter()).map(|(a, b)| a * b).sum();
        let yy: f64 = y_last.iter().map(|a| a * a).sum();
        let gamma = if yy > 1e-12 { sy / yy } else { 1.0 };

        let mut r: Vec<f64> = q.iter().map(|qi| gamma * qi).collect();

        // Second loop (forward)
        for i in 0..k {
            let s = &self.s_history[i];
            let y = &self.y_history[i];
            let rho = self.rho_history[i];

            let yr: f64 = y.iter().zip(r.iter()).map(|(a, b)| a * b).sum();
            let beta = rho * yr;

            for j in 0..n {
                r[j] += s[j] * (alphas[i] - beta);
            }
        }

        r.iter().map(|ri| -ri).collect()
    }
}

struct Evaluator<'a> {
    S: f64,
    N: usize,
    nsi: usize,
    nsc: usize,
    unit_polygon_vertices: &'a [(f64, f64)],
    unit_polygon_vectors: &'a [(f64, f64)],
    unit_container_vectors: &'a [(f64, f64)],
    unit_container_apothem: &'a [f64],
    is_inner_circle: bool,
    is_container_circle: bool,
    is_inner_l: bool,
    is_container_l: bool,
    container_mode: u8,
    polygon_array: &'a mut [(f64, f64)],
    vector_array: &'a mut [(f64, f64)],
    grad_buffer: &'a mut [f64],
    bbox_array: &'a mut [(f64, f64, f64, f64)],
    sort_indices: &'a mut [usize],
}

impl<'a> Evaluator<'a> {
    #[inline(always)]
    fn eval(&mut self, x: &[f64], compute_grad: bool) -> (f64, f64) {
        penalty_and_gradient_with_mode(
            x,
            self.S,
            self.N,
            self.nsi,
            self.nsc,
            self.unit_polygon_vertices,
            self.unit_polygon_vectors,
            self.unit_container_vectors,
            self.unit_container_apothem,
            self.is_inner_circle,
            self.is_container_circle,
            self.is_inner_l,
            self.is_container_l,
            self.container_mode,
            compute_grad,
            self.polygon_array,
            self.vector_array,
            self.grad_buffer,
            self.bbox_array,
            self.sort_indices,
        )
    }
}

/// Stage 1: Coarse Adam untangling for escaping deep overlaps.
fn adam_untangle(
    evaluator: &mut Evaluator,
    x0: &[f64],
    initial_fun: f64,
    initial_max_v: f64,
) -> (Vec<f64>, f64, f64) {
    let n = x0.len();
    let mut x = x0.to_vec();
    let mut best_x = x.clone();
    let mut best_fun = initial_fun;
    let mut best_max_violation = initial_max_v;

    let mut m = vec![0.0f64; n];
    let mut v = vec![0.0f64; n];
    let beta1 = 0.9f64;
    let beta2 = 0.999f64;
    let epsilon = 1e-8f64;
    let alpha = 0.02f64;

    let mut no_improve: u32 = 0;
    let mut best_fun_iter = best_fun;
    let mut beta1_t = beta1;
    let mut beta2_t = beta2;

    for _iter in 1..=250 {
        let (fun, max_violation) = evaluator.eval(&x, true);

        if max_violation <= 1e-15 {
            return (x, fun, max_violation);
        }

        if fun < best_fun_iter * 0.9999 {
            no_improve = 0;
            best_fun_iter = fun;
        } else {
            no_improve += 1;
        }

        // If shapes are coarse-untangled or plateaued, transition directly to L-BFGS
        if fun < 1e-3 || no_improve >= 40 {
            break;
        }

        let mut new_x = vec![0.0f64; n];
        for i in 0..n {
            m[i] = beta1 * m[i] + (1.0 - beta1) * evaluator.grad_buffer[i];
            v[i] = beta2 * v[i] + (1.0 - beta2) * evaluator.grad_buffer[i] * evaluator.grad_buffer[i];

            let m_hat = m[i] / (1.0 - beta1_t);
            let v_hat = v[i] / (1.0 - beta2_t);

            new_x[i] = x[i] - alpha * m_hat / (v_hat.sqrt() + epsilon);
        }

        beta1_t *= beta1;
        beta2_t *= beta2;

        let (new_fx, new_max_violation) = evaluator.eval(&new_x, false);

        x = new_x;
        if new_fx < best_fun {
            best_fun = new_fx;
            best_x = x.clone();
            best_max_violation = new_max_violation;
        }
    }

    (best_x, best_fun, best_max_violation)
}

/// Stage 2: L-BFGS Quasi-Newton polish with Armijo line search.
fn lbfgs_polish(
    evaluator: &mut Evaluator,
    x_init: Vec<f64>,
    best_fun_init: f64,
    best_max_v_init: f64,
) -> OptResult {
    let n = x_init.len();
    let mut x = x_init;
    let mut best_x = x.clone();
    let mut best_fun = best_fun_init;
    let mut best_max_violation = best_max_v_init;

    let mut lbfgs_history = LbfgsHistory::new(8);
    let (mut current_fx, mut current_max_violation) = evaluator.eval(&x, true);
    let mut current_grad = evaluator.grad_buffer[..n].to_vec();

    for _lbfgs_iter in 0..60 {
        if current_max_violation <= 1e-15 {
            return OptResult { x, _fun: current_fx, max_violation: current_max_violation };
        }

        let mut d = lbfgs_history.compute_direction(&current_grad);
        let mut dir_deriv: f64 = current_grad.iter().zip(d.iter()).map(|(g, di)| g * di).sum();

        // Ensure descent direction
        if dir_deriv >= 0.0 {
            d = current_grad.iter().map(|g| -g).collect();
            dir_deriv = current_grad.iter().zip(d.iter()).map(|(g, di)| g * di).sum();
        }

        if dir_deriv.abs() < 1e-14 {
            break;
        }

        // Backtracking Armijo Line Search
        let c1 = 1e-4;
        let mut step = 1.0;
        let mut trial_x = vec![0.0f64; n];
        let mut step_accepted = false;
        let mut trial_fx = current_fx;
        let mut trial_max_violation = current_max_violation;

        for _ls_step in 0..10 {
            for j in 0..n {
                trial_x[j] = x[j] + step * d[j];
            }

            let (f_trial, max_v_trial) = evaluator.eval(&trial_x, false);

            if f_trial <= current_fx + c1 * step * dir_deriv {
                trial_fx = f_trial;
                trial_max_violation = max_v_trial;
                step_accepted = true;
                break;
            }
            step *= 0.5;
        }

        if !step_accepted {
            break;
        }

        // Compute gradient at trial_x
        let (_f_eval, _max_v_eval) = evaluator.eval(&trial_x, true);

        let new_grad = evaluator.grad_buffer[..n].to_vec();
        let s_k: Vec<f64> = trial_x.iter().zip(x.iter()).map(|(tx, xk)| tx - xk).collect();
        let y_k: Vec<f64> = new_grad.iter().zip(current_grad.iter()).map(|(ng, cg)| ng - cg).collect();

        lbfgs_history.push(s_k, y_k);

        x = trial_x;
        current_fx = trial_fx;
        current_max_violation = trial_max_violation;
        current_grad = new_grad;

        if current_fx < best_fun {
            best_fun = current_fx;
            best_x = x.clone();
            best_max_violation = current_max_violation;
        }

        let max_grad_norm = current_grad.iter().fold(0.0f64, |acc, g| acc.max(g.abs()));
        if max_grad_norm < 1e-6 {
            break;
        }
    }

    OptResult { x: best_x, _fun: best_fun, max_violation: best_max_violation }
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
    container_mode: u8,
    polygon_array: &mut [(f64, f64)],
    vector_array: &mut [(f64, f64)],
    grad_buffer: &mut [f64],
    bbox_array: &mut [(f64, f64, f64, f64)],
    sort_indices: &mut [usize],
) -> OptResult {
    let mut evaluator = Evaluator {
        S,
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
        container_mode,
        polygon_array,
        vector_array,
        grad_buffer,
        bbox_array,
        sort_indices,
    };

    let (initial_fun, initial_max_violation) = evaluator.eval(x0, false);
    if initial_max_violation <= 1e-15 {
        return OptResult {
            x: x0.to_vec(),
            _fun: initial_fun,
            max_violation: initial_max_violation,
        };
    }

    // STAGE 1: Coarse Adam Untangling
    let (adam_x, adam_fun, adam_max_v) = adam_untangle(&mut evaluator, x0, initial_fun, initial_max_violation);
    if adam_max_v <= 1e-15 {
        return OptResult {
            x: adam_x,
            _fun: adam_fun,
            max_violation: adam_max_v,
        };
    }

    // STAGE 2: L-BFGS Quasi-Newton Polish
    lbfgs_polish(&mut evaluator, adam_x, adam_fun, adam_max_v)
}


pub fn penalty_and_gradient(
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
    let container_mode: u8 = if is_container_circle {
        1
    } else if is_container_l {
        2
    } else {
        0
    };
    penalty_and_gradient_with_mode(
        values,
        S,
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
        container_mode,
        compute_grad,
        polygon_array,
        vector_array,
        grad,
        bbox_array,
        sort_indices,
    )
}

pub fn penalty_and_gradient_with_mode(
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
    container_mode: u8,
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

        if container_mode == 3 {
            // Closed-form Semicircle bounds for unit circle: y >= 1.0, ||c|| <= S - 1.0
            if posy < 1.0 {
                let diff = 1.0 - posy;
                penalty += diff * diff;
                if diff > max_violation { max_violation = diff; }
                if compute_grad {
                    grad[i * 3 + 1] -= 2.0 * diff;
                }
            }
            let dist = (posx * posx + posy * posy).sqrt();
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
        } else if container_mode == 4 {
            // Closed-form Circular Quadrant bounds for unit circle: x >= 1.0, y >= 1.0, ||c|| <= S - 1.0
            if posx < 1.0 {
                let diff = 1.0 - posx;
                penalty += diff * diff;
                if diff > max_violation { max_violation = diff; }
                if compute_grad {
                    grad[i * 3] -= 2.0 * diff;
                }
            }
            if posy < 1.0 {
                let diff = 1.0 - posy;
                penalty += diff * diff;
                if diff > max_violation { max_violation = diff; }
                if compute_grad {
                    grad[i * 3 + 1] -= 2.0 * diff;
                }
            }
            let dist = (posx * posx + posy * posy).sqrt();
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
        } else if is_container_circle {
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
                            if compute_grad { grad[i * 3 + 1] += 2.0 * diff; }
                        }
                    } else if posy > cut_min_y {
                        let dist = cut_min_x - posx;
                        if dist < r {
                            let diff = r - dist;
                            penalty += diff * diff;
                            if diff > max_violation { max_violation = diff; }
                            if compute_grad { grad[i * 3] += 2.0 * diff; }
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
                    let mut best_axis_idx = 0usize;
                    let mut best_v1_min = 0usize;
                    let mut best_v1_max = 0usize;
                    let mut best_v2_min = 0usize;
                    let mut best_v2_max = 0usize;

                    for (ax_idx, &(ax, ay)) in axes.iter().enumerate() {
                        let mut min_1 = 1e30f64;
                        let mut max_1 = -1e30f64;
                        let mut v1_min = 0usize;
                        let mut v1_max = 0usize;
                        for (v_idx, &(px, py)) in sub_pts.iter().enumerate() {
                            let dot = px * ax + py * ay;
                            if dot < min_1 { min_1 = dot; v1_min = v_idx; }
                            if dot > max_1 { max_1 = dot; v1_max = v_idx; }
                        }

                        let mut min_2 = 1e30f64;
                        let mut max_2 = -1e30f64;
                        let mut v2_min = 0usize;
                        let mut v2_max = 0usize;
                        for (v_idx, &(px, py)) in r_cutout_pts.iter().enumerate() {
                            let dot = px * ax + py * ay;
                            if dot < min_2 { min_2 = dot; v2_min = v_idx; }
                            if dot > max_2 { max_2 = dot; v2_max = v_idx; }
                        }

                        let overlap = max_1.min(max_2) - min_1.max(min_2);
                        if overlap <= 0.0 {
                            obstacle_collision = false;
                            break;
                        }
                        if overlap < min_overlap {
                            min_overlap = overlap;
                            best_axis_idx = ax_idx;
                            best_v1_min = v1_min;
                            best_v1_max = v1_max;
                            best_v2_min = v2_min;
                            best_v2_max = v2_max;
                        }
                    }

                    if obstacle_collision {
                        penalty += min_overlap * min_overlap;
                        if min_overlap > max_violation {
                            max_violation = min_overlap;
                        }
                        if compute_grad {
                            let term = 2.0 * min_overlap;
                            let (ax, ay) = axes[best_axis_idx];
                            let p1_max = sub_pts[best_v1_max];
                            let p2_max = r_cutout_pts[best_v2_max];
                            let max_1 = p1_max.0 * ax + p1_max.1 * ay;
                            let max_2 = p2_max.0 * ax + p2_max.1 * ay;

                            let p1_min = sub_pts[best_v1_min];
                            let p2_min = r_cutout_pts[best_v2_min];
                            let min_1 = p1_min.0 * ax + p1_min.1 * ay;
                            let min_2 = p2_min.0 * ax + p2_min.1 * ay;

                            let (p_upper, upper_is_sub) = if max_1 < max_2 { (p1_max, true) } else { (p2_max, false) };
                            let (p_lower, lower_is_sub) = if min_1 > min_2 { (p1_min, true) } else { (p2_min, false) };

                            if upper_is_sub {
                                let drot = -(p_upper.1 - posy) * ax + (p_upper.0 - posx) * ay;
                                grad[i * 3] += term * ax;
                                grad[i * 3 + 1] += term * ay;
                                grad[i * 3 + 2] += term * drot;
                            }
                            if lower_is_sub {
                                let drot = -(p_lower.1 - posy) * ax + (p_lower.0 - posx) * ay;
                                grad[i * 3] -= term * ax;
                                grad[i * 3 + 1] -= term * ay;
                                grad[i * 3 + 2] -= term * drot;
                            }
                            // Derivative wrt rotating axis when axis comes from sub_normals (idx < n_sub_axes)
                            if best_axis_idx < axes.len() - 2 {
                                let d_overlap_drot_axis = (p_upper.0 - p_lower.0) * (-ay) + (p_upper.1 - p_lower.1) * ax;
                                grad[i * 3 + 2] += term * d_overlap_drot_axis;
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

                                let axis_poly_idx = if sub_best_axis_idx < 2 { i } else { j };
                                let delta_x = p_upper.0 - p_lower.0;
                                let delta_y = p_upper.1 - p_lower.1;
                                let d_axis_drot_x = -ay;
                                let d_axis_drot_y = ax;
                                let d_overlap_drot_axis = delta_x * d_axis_drot_x + delta_y * d_axis_drot_y;
                                grad[axis_poly_idx * 3 + 2] += term * d_overlap_drot_axis;
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

#[cfg(test)]
mod tests {
    use super::*;
    use rand_chacha::rand_core::SeedableRng;

    #[test]
    fn test_lbfgs_history_descent_direction() {
        let mut history = LbfgsHistory::new(4);
        let grad = vec![1.0, 2.0, -1.0];
        let d = history.compute_direction(&grad);
        assert_eq!(d, vec![-1.0, -2.0, 1.0]);

        // Push step
        let s = vec![-0.1, -0.2, 0.1];
        let y = vec![-0.5, -1.0, 0.5];
        history.push(s, y);

        let d2 = history.compute_direction(&grad);
        let dot: f64 = grad.iter().zip(d2.iter()).map(|(a, b)| a * b).sum();
        assert!(dot < 0.0, "Direction d must be a descent direction (dot product < 0)");
    }

    #[test]
    fn test_hybrid_optimizer_convergence() {
        let (nsi, upv, upvectors, _) = get_shape_geometry("6");
        let (nsc, _, ucv, uap) = get_shape_geometry("5");
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let start = Instant::now();
        let stop_flag = AtomicBool::new(false);

        let result = run_attempt(
            &mut rng,
            3.5,
            nsi,
            nsc,
            &upv,
            &upvectors,
            &ucv,
            &uap,
            1e-5,
            0.001,
            &start,
            &stop_flag,
            Some(5.0),
            None,
            None,
            false,
            false,
            false,
            false,
        );

        assert!(result.1.is_some(), "Hybrid optimizer must find valid packing for 4_6_in_5 at S=3.5");
        let final_s = result.0;
        assert!(final_s < 3.5, "Final scale S should be shrunk and feasible");
    }

    #[test]
    fn test_compute_and_inverse_friedman_metric_roundtrip() {
        // Regular polygon: triangle in square
        let f_val = compute_friedman_metric(3.0, "3", "4");
        let s_inv = inverse_friedman_metric(f_val, "3", "4");
        assert!((s_inv - 3.0).abs() < 1e-9);

        // Regular polygon: hexagon in triangle (14_hexintri problem)
        // For hexagon (inner=6): i_scale = 2 * sin(PI / 6) = 1.0
        // For triangle (container=3): c_factor = 2 * sin(PI / 3) = sqrt(3)
        // S = 6.00128299 => final_metric s = 6.00128299 * sqrt(3) ~= 10.39453
        let s_hexintri = 6.00128299;
        let metric = compute_friedman_metric(s_hexintri, "6", "3");
        let expected_metric = s_hexintri * 3.0f64.sqrt();
        assert!((metric - expected_metric).abs() < 1e-9);
        let s_back = inverse_friedman_metric(metric, "6", "3");
        assert!((s_back - s_hexintri).abs() < 1e-9);

        // Special shapes: TAN in CIRCLE
        let f_val2 = compute_friedman_metric(2.0, "TAN", "CIRCLE");
        assert!((inverse_friedman_metric(f_val2, "TAN", "CIRCLE") - 2.0).abs() < 1e-9);

        // Circle in L
        let s_cirinl = compute_friedman_metric(1.70710678, "CIRCLE", "L");
        assert!((s_cirinl - 3.41421356).abs() < 1e-6);
        assert!((inverse_friedman_metric(3.41421356, "CIRCLE", "L") - 1.70710678).abs() < 1e-6);

        // Square in L
        let s_squinl = compute_friedman_metric(2.0f64.sqrt(), "4", "L");
        assert!((s_squinl - 2.0).abs() < 1e-9);
        assert!((inverse_friedman_metric(2.0, "4", "L") - 2.0f64.sqrt()).abs() < 1e-9);

        // LinL (L-in-L)
        assert_eq!(compute_friedman_metric(1.0, "L", "L"), 1.0);
        assert_eq!(compute_friedman_metric(2.5, "L", "L"), 2.5);
        assert_eq!(inverse_friedman_metric(1.0, "L", "L"), 1.0);
        assert_eq!(inverse_friedman_metric(2.5, "L", "L"), 2.5);

        // Named polygon aliases
        assert_eq!(parse_polygon_sides("triangle"), 3);
        assert_eq!(parse_polygon_sides("SQUARE"), 4);
        assert_eq!(parse_polygon_sides("PENTAGON"), 5);
        assert_eq!(parse_polygon_sides("HEXAGON"), 6);
        assert_eq!(
            compute_friedman_metric(2.0f64.sqrt(), "square", "L"),
            compute_friedman_metric(2.0f64.sqrt(), "4", "L")
        );
    }

    #[test]
    fn test_expanded_shapes_metrics_and_quad_geometry() {
        // Heptagon, Nonagon (including Enneagon alias), Decagon
        assert_eq!(parse_polygon_sides("heptagon"), 7);
        assert_eq!(parse_polygon_sides("enneagon"), 9);
        assert_eq!(parse_polygon_sides("nonagon"), 9);
        assert_eq!(parse_polygon_sides("decagon"), 10);

        for tok in ["7", "9", "10", "RHOMBUS", "PARALLELOGRAM", "TRAPEZOID", "SEMICIRCLE", "QUADRANT"] {
            let f = compute_friedman_metric(2.5, "CIRCLE", tok);
            let s_back = inverse_friedman_metric(f, "CIRCLE", tok);
            assert!((s_back - 2.5).abs() < 1e-9, "Roundtrip failed for {}", tok);
        }

        // Canonical quad vertices and positive interior apothems
        for tok in ["RHOMBUS", "PARALLELOGRAM", "TRAPEZOID"] {
            let (sides, verts, vecs, apothems) = get_shape_geometry(tok);
            assert_eq!(sides, 4);
            assert_eq!(verts.len(), 4);
            assert_eq!(vecs.len(), 4);
            for k in 0..4 {
                assert!(apothems[k] > 0.0);
                let dot_a = verts[k].0 * vecs[k].0 + verts[k].1 * vecs[k].1;
                let dot_b = verts[(k + 1) % 4].0 * vecs[k].0 + verts[(k + 1) % 4].1 * vecs[k].1;
                assert!((dot_a - apothems[k]).abs() < 1e-12);
                assert!((dot_b - apothems[k]).abs() < 1e-12);
            }
        }
    }

    #[test]
    fn test_curved_containers_solve_and_validation() {
        // Strict capability guard: non-CIRCLE inside SEMICIRCLE must return success=false
        let invalid_cfg = SolveConfig {
            inner_polygons: 1,
            inner_shape: "4".to_string(),
            container_shape: "SEMICIRCLE".to_string(),
            attempts: 4,
            tolerance: 1e-15,
            finalstep: 0.001,
            time_limit: Some(2.0),
            initial_positions: None,
            target_s: None,
        };
        assert!(!solve(&invalid_cfg).success);

        // N=1 CIRCLE in SEMICIRCLE => optimal s = 2.0
        let semi_cfg = SolveConfig {
            inner_polygons: 1,
            inner_shape: "CIRCLE".to_string(),
            container_shape: "SEMICIRCLE".to_string(),
            attempts: 16,
            tolerance: 1e-15,
            finalstep: 0.0005,
            time_limit: Some(5.0),
            initial_positions: None,
            target_s: None,
        };
        let res_semi = solve(&semi_cfg);
        assert!(res_semi.success);
        assert!((res_semi.final_metric - 2.0).abs() < 0.02, "Got semi s={}", res_semi.final_metric);

        // N=1 CIRCLE in QUADRANT => optimal s = 1 + sqrt(2) ~= 2.4142
        let quad_cfg = SolveConfig {
            inner_polygons: 1,
            inner_shape: "CIRCLE".to_string(),
            container_shape: "QUADRANT".to_string(),
            attempts: 16,
            tolerance: 1e-15,
            finalstep: 0.0005,
            time_limit: Some(5.0),
            initial_positions: None,
            target_s: None,
        };
        let res_quad = solve(&quad_cfg);
        assert!(res_quad.success);
        assert!((res_quad.final_metric - (1.0 + 2.0f64.sqrt())).abs() < 0.02, "Got quad s={}", res_quad.final_metric);
    }

    #[test]
    fn test_l_shape_analytic_gradient_matches_finite_difference() {
        let (nsi, upv, upvectors, _) = get_shape_geometry("L");
        let ucv = vec![(1.0, 0.0)];
        let uap = vec![1.0];
        let mut poly_arr = vec![(0.0, 0.0); 2 * nsi];
        let mut vec_arr = vec![(0.0, 0.0); 2 * nsi];
        let mut grad = vec![0.0; 6];
        let mut bbox = vec![(0.0, 0.0, 0.0, 0.0); 2];
        let mut sort_idx = vec![0usize; 2];

        // Two overlapping/tilted L shapes inside L container touching cutout corner
        let vals = vec![0.15, 0.25, 0.42, 0.55, -0.10, 1.15];
        let (_, _) = penalty_and_gradient(
            &vals, 1.5, 2, nsi, 1, &upv, &upvectors, &ucv, &uap,
            false, false, true, true, true,
            &mut poly_arr, &mut vec_arr, &mut grad, &mut bbox, &mut sort_idx,
        );

        let eps = 1e-6;
        for k in 0..6 {
            let mut v_plus = vals.clone();
            v_plus[k] += eps;
            let mut g_dummy = vec![0.0; 6];
            let (f_plus, _) = penalty_and_gradient(
                &v_plus, 1.5, 2, nsi, 1, &upv, &upvectors, &ucv, &uap,
                false, false, true, true, false,
                &mut poly_arr, &mut vec_arr, &mut g_dummy, &mut bbox, &mut sort_idx,
            );

            let mut v_minus = vals.clone();
            v_minus[k] -= eps;
            let (f_minus, _) = penalty_and_gradient(
                &v_minus, 1.5, 2, nsi, 1, &upv, &upvectors, &ucv, &uap,
                false, false, true, true, false,
                &mut poly_arr, &mut vec_arr, &mut g_dummy, &mut bbox, &mut sort_idx,
            );

            let fd = (f_plus - f_minus) / (2.0 * eps);
            assert!(
                (grad[k] - fd).abs() < 1e-4,
                "Gradient mismatch at idx {}: analytic={}, fd={}",
                k, grad[k], fd
            );
        }
    }
}

