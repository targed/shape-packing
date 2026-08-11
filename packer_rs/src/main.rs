#![allow(non_snake_case)]

use clap::Parser;
use std::fs;
use std::io::Write;
use packer_rs::solver::{solve, SolveConfig};

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

    #[arg(long)]
    solution_file: Option<String>,

    #[arg(long)]
    initial_positions: Option<String>,

    #[arg(long)]
    target_s: Option<f64>,
}

fn main() {
    let args = Args::parse();

    let initial_positions = if let Some(path) = &args.initial_positions {
        let contents = fs::read_to_string(path).expect("Failed to read initial positions file");
        let positions: Vec<f64> = serde_json::from_str(&contents).expect("Invalid JSON in initial positions");
        Some(positions)
    } else {
        None
    };

    let config = SolveConfig {
        inner_polygons: args.inner_polygons,
        inner_shape: args.inner_shape.clone(),
        container_shape: args.container_shape.clone(),
        attempts: args.attempts,
        tolerance: args.tolerance,
        finalstep: args.finalstep,
        time_limit: args.time_limit,
        initial_positions,
        target_s: args.target_s,
    };

    let result = solve(&config);

    if result.success {
        println!("Final side length: {}", result.final_metric);

        if let Some(path) = &args.solution_file {
            let mut buf = String::new();
            buf.push_str("{\n");
            buf.push_str(&format!("  \"S\": {},\n", result.best_s));
            buf.push_str(&format!("  \"inner_token\": \"{}\",\n", result.inner_token));
            buf.push_str(&format!("  \"container_token\": \"{}\",\n", result.container_token));
            buf.push_str(&format!("  \"final_metric\": {},\n", result.final_metric));
            buf.push_str(&format!("  \"N\": {},\n", result.values.len() / 3));
            buf.push_str("  \"values\": [");
            for (i, v) in result.values.iter().enumerate() {
                buf.push_str(&format!("{}", v));
                if i < result.values.len() - 1 {
                    buf.push(',');
                }
            }
            buf.push_str("]\n}\n");

            if let Ok(mut f) = fs::File::create(path) {
                let _ = f.write_all(buf.as_bytes());
            }
        }
    } else {
        println!("No valid packing found.");
    }
}
