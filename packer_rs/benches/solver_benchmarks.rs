#![allow(non_snake_case)]

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use packer_rs::solver::{get_shape_geometry, penalty_and_gradient, run_attempt};
use rand_chacha::rand_core::SeedableRng;
use rand_chacha::ChaCha8Rng;
use std::sync::atomic::AtomicBool;
use std::time::Instant;


fn bench_penalty_and_gradient(c: &mut Criterion) {
    let mut group = c.benchmark_group("penalty_and_gradient");

    // Case 1: 4_6_in_5 (Regular polygon)
    {
        let N = 4;
        let S = 3.0;
        let (nsi, upv, upvectors, _) = get_shape_geometry("6");
        let (nsc, _, ucv, uap) = get_shape_geometry("5");

        let values = vec![
            -0.5, -0.5, 0.1,
             0.5, -0.5, 0.2,
            -0.5,  0.5, 0.3,
             0.5,  0.5, 0.4,
        ];

        let mut polygon_array = vec![(0.0, 0.0); N * nsi];
        let mut vector_array = vec![(0.0, 0.0); N * nsi];
        let mut grad = vec![0.0f64; N * 3];
        let mut bbox_array = vec![(0.0, 0.0, 0.0, 0.0); N];
        let mut sort_indices = vec![0usize; N];

        group.bench_function("4_6_in_5_with_grad", |b| {
            b.iter(|| {
                penalty_and_gradient(
                    black_box(&values),
                    black_box(S),
                    black_box(N),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(true),
                    black_box(&mut polygon_array),
                    black_box(&mut vector_array),
                    black_box(&mut grad),
                    black_box(&mut bbox_array),
                    black_box(&mut sort_indices),
                )
            });
        });
    }

    // Case 2: 12_3_in_circle (Circle container)
    {
        let N = 12;
        let S = 4.0;
        let (nsi, upv, upvectors, _) = get_shape_geometry("3");
        let (nsc, _, ucv, uap) = get_shape_geometry("CIRCLE");

        let mut values = vec![0.0f64; N * 3];
        for i in 0..N {
            let angle = (i as f64) * 2.0 * std::f64::consts::PI / (N as f64);
            values[i * 3] = 1.5 * angle.cos();
            values[i * 3 + 1] = 1.5 * angle.sin();
            values[i * 3 + 2] = angle;
        }

        let mut polygon_array = vec![(0.0, 0.0); N * nsi];
        let mut vector_array = vec![(0.0, 0.0); N * nsi];
        let mut grad = vec![0.0f64; N * 3];
        let mut bbox_array = vec![(0.0, 0.0, 0.0, 0.0); N];
        let mut sort_indices = vec![0usize; N];

        group.bench_function("12_3_in_circle_with_grad", |b| {
            b.iter(|| {
                penalty_and_gradient(
                    black_box(&values),
                    black_box(S),
                    black_box(N),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(false),
                    black_box(true),
                    black_box(false),
                    black_box(false),
                    black_box(true),
                    black_box(&mut polygon_array),
                    black_box(&mut vector_array),
                    black_box(&mut grad),
                    black_box(&mut bbox_array),
                    black_box(&mut sort_indices),
                )
            });
        });
    }

    // Case 3: 25_4_in_4 (Large N broadphase)
    {
        let N = 25;
        let S = 6.0;
        let (nsi, upv, upvectors, _) = get_shape_geometry("4");
        let (nsc, _, ucv, uap) = get_shape_geometry("4");

        let mut values = vec![0.0f64; N * 3];
        for y in 0..5 {
            for x in 0..5 {
                let idx = y * 5 + x;
                values[idx * 3] = -2.0 + (x as f64);
                values[idx * 3 + 1] = -2.0 + (y as f64);
                values[idx * 3 + 2] = 0.0;
            }
        }

        let mut polygon_array = vec![(0.0, 0.0); N * nsi];
        let mut vector_array = vec![(0.0, 0.0); N * nsi];
        let mut grad = vec![0.0f64; N * 3];
        let mut bbox_array = vec![(0.0, 0.0, 0.0, 0.0); N];
        let mut sort_indices = vec![0usize; N];

        group.bench_function("25_4_in_4_broadphase", |b| {
            b.iter(|| {
                penalty_and_gradient(
                    black_box(&values),
                    black_box(S),
                    black_box(N),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(true),
                    black_box(&mut polygon_array),
                    black_box(&mut vector_array),
                    black_box(&mut grad),
                    black_box(&mut bbox_array),
                    black_box(&mut sort_indices),
                )
            });
        });
    }

    // Case 4: 6_L_in_4 (Compound Non-Convex L-Tromino)
    {
        let N = 6;
        let S = 4.0;
        let (nsi, upv, upvectors, _) = get_shape_geometry("L");
        let (nsc, _, ucv, uap) = get_shape_geometry("4");

        let values = vec![
            -1.0, -1.0, 0.0,
             1.0, -1.0, 1.57,
            -1.0,  1.0, 3.14,
             1.0,  1.0, 0.5,
             0.0,  0.0, 0.0,
             0.5, -0.5, 0.8,
        ];

        let mut polygon_array = vec![(0.0, 0.0); N * nsi];
        let mut vector_array = vec![(0.0, 0.0); N * nsi];
        let mut grad = vec![0.0f64; N * 3];
        let mut bbox_array = vec![(0.0, 0.0, 0.0, 0.0); N];
        let mut sort_indices = vec![0usize; N];

        group.bench_function("6_L_in_4_compound_sat", |b| {
            b.iter(|| {
                penalty_and_gradient(
                    black_box(&values),
                    black_box(S),
                    black_box(N),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(false),
                    black_box(false),
                    black_box(true),
                    black_box(false),
                    black_box(true),
                    black_box(&mut polygon_array),
                    black_box(&mut vector_array),
                    black_box(&mut grad),
                    black_box(&mut bbox_array),
                    black_box(&mut sort_indices),
                )
            });
        });
    }

    // Case 5: 6_TAN_in_L (Non-Convex L-Container Confinement)
    {
        let N = 6;
        let S = 1.5;
        let (nsi, upv, upvectors, _) = get_shape_geometry("TAN");
        let (nsc, _, ucv, uap) = get_shape_geometry("L");

        let values = vec![
            -0.5, -0.5, 0.0,
            -0.5,  0.5, 0.5,
             0.5, -0.5, 1.0,
            -0.2, -0.2, 0.3,
            -0.4,  0.8, 0.7,
             0.8, -0.4, 1.2,
        ];

        let mut polygon_array = vec![(0.0, 0.0); N * nsi];
        let mut vector_array = vec![(0.0, 0.0); N * nsi];
        let mut grad = vec![0.0f64; N * 3];
        let mut bbox_array = vec![(0.0, 0.0, 0.0, 0.0); N];
        let mut sort_indices = vec![0usize; N];

        group.bench_function("6_TAN_in_L_container_confinement", |b| {
            b.iter(|| {
                penalty_and_gradient(
                    black_box(&values),
                    black_box(S),
                    black_box(N),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(true),
                    black_box(true),
                    black_box(&mut polygon_array),
                    black_box(&mut vector_array),
                    black_box(&mut grad),
                    black_box(&mut bbox_array),
                    black_box(&mut sort_indices),
                )
            });
        });
    }

    group.finish();
}

fn bench_run_attempt(c: &mut Criterion) {
    let mut group = c.benchmark_group("run_attempt");
    group.sample_size(10);
    group.measurement_time(std::time::Duration::from_secs(12));


    // Benchmark 1: 4_6_in_5 single attempt
    {
        let (nsi, upv, upvectors, _) = get_shape_geometry("6");
        let (nsc, _, ucv, uap) = get_shape_geometry("5");
        let stop_flag = AtomicBool::new(false);

        group.bench_function("4_6_in_5_single_attempt", |b| {
            let mut seed = 100u64;
            b.iter(|| {
                let mut rng = ChaCha8Rng::seed_from_u64(seed);
                seed += 1;
                let start = Instant::now();
                run_attempt(
                    black_box(&mut rng),
                    black_box(4.0),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(1e-5),
                    black_box(0.001),
                    black_box(&start),
                    black_box(&stop_flag),
                    black_box(Some(10.0)),
                    black_box(None),
                    black_box(None),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                )
            });
        });
    }

    // Benchmark 2: 6_TAN_in_L single attempt
    {
        let (nsi, upv, upvectors, _) = get_shape_geometry("TAN");
        let (nsc, _, ucv, uap) = get_shape_geometry("L");
        let stop_flag = AtomicBool::new(false);

        group.bench_function("6_TAN_in_L_single_attempt", |b| {
            let mut seed = 200u64;
            b.iter(|| {
                let mut rng = ChaCha8Rng::seed_from_u64(seed);
                seed += 1;
                let start = Instant::now();
                run_attempt(
                    black_box(&mut rng),
                    black_box(6.0),
                    black_box(nsi),
                    black_box(nsc),
                    black_box(&upv),
                    black_box(&upvectors),
                    black_box(&ucv),
                    black_box(&uap),
                    black_box(1e-5),
                    black_box(0.001),
                    black_box(&start),
                    black_box(&stop_flag),
                    black_box(Some(10.0)),
                    black_box(None),
                    black_box(None),
                    black_box(false),
                    black_box(false),
                    black_box(false),
                    black_box(true),
                )
            });
        });
    }

    group.finish();
}

criterion_group!(benches, bench_penalty_and_gradient, bench_run_attempt);
criterion_main!(benches);
