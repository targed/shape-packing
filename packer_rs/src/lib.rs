pub mod solver;

#[cfg(feature = "python")]
mod python_bindings {
    use pyo3::prelude::*;
    use pyo3::types::PyDict;

    use crate::solver::{solve, SolveConfig};

    #[pyfunction]
    #[pyo3(signature = (
        inner_polygons,
        inner_shape,
        container_shape,
        attempts,
        tolerance,
        finalstep,
        time_limit,
        solution_file,
        initial_positions,
        target_s,
    ))]
    pub fn solve_from_python(
        inner_polygons: usize,
        inner_shape: String,
        container_shape: String,
        attempts: usize,
        tolerance: f64,
        finalstep: f64,
        time_limit: Option<f64>,
        solution_file: Option<String>,
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

        let result = solve(&config);

        Python::with_gil(|py| {
            if result.success {
                let dict = PyDict::new(py);
                dict.set_item("best_s", result.best_s)?;
                dict.set_item("inner_token", result.inner_token)?;
                dict.set_item("container_token", result.container_token)?;
                dict.set_item("final_metric", result.final_metric)?;
                dict.set_item("values", result.values)?;
                Ok(Some(dict.into_any().downcast::<PyDict>().unwrap()))
            } else {
                Ok(None)
            }
        })
    }

    #[pymodule]
    fn packer_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(solve_from_python, m)?)?;
        Ok(())
    }
}