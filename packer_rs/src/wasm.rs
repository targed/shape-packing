use wasm_bindgen::prelude::*;
use crate::solver::{inverse_friedman_metric, solve, SolveConfig};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct WasmSolveOutput {
    pub success: bool,
    pub best_s: f64,
    pub circumradius_s: f64,
    pub final_metric: f64,
    pub values: Vec<f64>,
}

#[wasm_bindgen]
pub fn solve_attempt_wasm(
    inner_shape: &str,
    container_shape: &str,
    n: usize,
    attempts: usize,
    target_s: Option<f64>,
) -> String {
    if n == 0 || n > 200 || attempts == 0 {
        return r#"{"success":false,"best_s":0,"circumradius_s":0,"final_metric":0,"values":[]}"#.to_string();
    }
    let bounded_attempts = attempts.min(100_000);
    let target_circumradius = target_s
        .filter(|ts| ts.is_finite() && *ts > 0.0)
        .map(|ts| inverse_friedman_metric(ts, inner_shape, container_shape));

    let config = SolveConfig {
        inner_polygons: n,
        inner_shape: inner_shape.to_string(),
        container_shape: container_shape.to_string(),
        attempts: bounded_attempts,
        tolerance: 1e-15,
        finalstep: 0.0001,
        time_limit: None,
        initial_positions: None,
        target_s: target_circumradius,
    };

    let result = solve(&config);
    let output = WasmSolveOutput {
        success: result.success,
        best_s: result.final_metric,
        circumradius_s: result.best_s,
        final_metric: result.final_metric,
        values: result.values,
    };

    serde_json::to_string(&output).unwrap_or_else(|_| "{}".to_string())
}
