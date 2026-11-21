use wasm_bindgen::prelude::*;
use crate::solver::{solve, SolveConfig};
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

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
    let target_circumradius = target_s.map(|ts| {
        let container_upper = container_shape.trim().to_uppercase();
        let inner_upper = inner_shape.trim().to_uppercase();

        let parse_sides = |s: &str| -> usize {
            match s {
                "TRIANGLE" => 3,
                "SQUARE" => 4,
                "PENTAGON" => 5,
                "HEXAGON" => 6,
                "HEPTAGON" => 7,
                "OCTAGON" => 8,
                "NONAGON" => 9,
                "DECAGON" => 10,
                other => other.parse().unwrap_or(3),
            }
        };

        if container_upper == "L" && inner_upper == "L" {
            return ts;
        }

        let i_scale = match inner_upper.as_str() {
            "CIRCLE" | "CIR" | "TAN" | "DOMINO" | "L" => 1.0,
            _ => 2.0 * (PI / parse_sides(&inner_upper) as f64).sin(),
        };
        let c_metric = ts * i_scale;
        match container_upper.as_str() {
            "CIRCLE" | "CIR" | "TAN" | "DOMINO" => c_metric,
            "L" => c_metric / 2.0,
            _ => c_metric / (2.0 * (PI / parse_sides(&container_upper) as f64).sin()),
        }
    });

    let config = SolveConfig {
        inner_polygons: n,
        inner_shape: inner_shape.to_string(),
        container_shape: container_shape.to_string(),
        attempts,
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
