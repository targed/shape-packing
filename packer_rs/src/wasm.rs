use wasm_bindgen::prelude::*;
use crate::solver::{solve, SolveConfig};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct WasmSolveOutput {
    pub success: bool,
    pub best_s: f64,
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
    let config = SolveConfig {
        inner_polygons: n,
        inner_shape: inner_shape.to_string(),
        container_shape: container_shape.to_string(),
        attempts,
        tolerance: 1e-15,
        finalstep: 0.0001,
        time_limit: None,
        initial_positions: None,
        target_s,
    };

    let result = solve(&config);
    let output = WasmSolveOutput {
        success: result.success,
        best_s: result.best_s,
        final_metric: result.final_metric,
        values: result.values,
    };

    serde_json::to_string(&output).unwrap_or_else(|_| "{}".to_string())
}
