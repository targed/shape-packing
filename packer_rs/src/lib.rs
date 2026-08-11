pub mod solver;

#[cfg(feature = "python")]
use solver as _solver_for_py;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
use pyo3::types::PyDict;

#[cfg(feature = "python")]
use solver::{solve, SolveConfig};

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    inner_polygons,
    inner_shape,
    container_shape,
    attempts = 1000,
    tolerance = 1e-30,
    finalstep = 0.0001,
    time_limit = None,
    initial_positions = None,
    target_s = None
))]
fn solve_py<'py>(
    py: Python<'py>,
    inner_polygons: usize,
    inner_shape: String,
    container_shape: String,
    attempts: usize,
    tolerance: f64,
    finalstep: f64,
    time_limit: Option<f64>,
    initial_positions: Option<Vec<f64>>,
    target_s: Option<f64>,
) -> PyResult<Option<Bound<'py, PyDict>>> {
    let config = SolveConfig {
        inner_polygons,
        inner_shape,
        container_shape,
        attempts,
        tolerance,
        finalstep,
        time_limit,
        initial_positions,
        target_s,
    };

    let result = py.allow_threads(|| solve(&config));

    if result.success {
        let dict = PyDict::new_bound(py);
        dict.set_item("S", result.best_s)?;
        dict.set_item("final_metric", result.final_metric)?;
        dict.set_item("values", result.values)?;
        dict.set_item("N", inner_polygons)?;
        dict.set_item("inner_token", result.inner_token)?;
        dict.set_item("container_token", result.container_token)?;
        Ok(Some(dict))
    } else {
        Ok(None)
    }
}

#[cfg(feature = "python")]
#[pymodule]
fn packer_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_py, m)?)?;
    Ok(())
}
