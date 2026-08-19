import os
import json
import subprocess
import importlib.util
from typing import Optional, Dict, Any, List

_LOADED_PYO3_MODULE = None

def _try_import_pyo3_packer():
    global _LOADED_PYO3_MODULE
    if _LOADED_PYO3_MODULE is not None:
        return _LOADED_PYO3_MODULE

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    possible_paths = [
        os.path.join(repo_root, "packer_rs", "target", "release", "packer_rs.pyd"),
        os.path.join(repo_root, "packer_rs", "target", "release", "packer_rs.dll"),
        os.path.join(repo_root, "packer_rs", "target", "release", "libpacker_rs.so"),
        os.path.join(repo_root, "packer_rs", "target", "release", "libpacker_rs.dylib"),
        os.path.join(repo_root, "packer_rs", "target", "release", "packer_rs.so"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                spec = importlib.util.spec_from_file_location("packer_rs", p)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "solve_py"):
                        _LOADED_PYO3_MODULE = mod
                        return mod
            except Exception:
                pass
    return None

def run_solver(
    n_shapes: int,
    inner_shape: str,
    container_shape: str,
    attempts: int = 1000,
    tolerance: float = 1e-30,
    finalstep: float = 0.0001,
    time_limit: Optional[float] = None,
    initial_positions: Optional[List[float]] = None,
    target_s: Optional[float] = None,
    solution_file: Optional[str] = None,
    no_build: bool = True,
) -> Dict[str, Any]:
    pyo3_mod = _try_import_pyo3_packer()
    
    if pyo3_mod is not None and hasattr(pyo3_mod, "solve_py"):
        try:
            res = pyo3_mod.solve_py(
                n_shapes,
                str(inner_shape),
                str(container_shape),
                attempts=attempts,
                tolerance=tolerance,
                finalstep=finalstep,
                time_limit=time_limit,
                initial_positions=initial_positions,
                target_s=target_s,
            )
            if res is not None:
                S = res.get("S", 0.0)
                final_metric = res.get("final_metric", 0.0)
                values = res.get("values", [])
                
                if solution_file:
                    os.makedirs(os.path.dirname(os.path.abspath(solution_file)), exist_ok=True)
                    with open(solution_file, "w") as f:
                        json.dump(res, f, indent=2)
                        
                return {
                    "success": True,
                    "score": final_metric,
                    "S": S,
                    "values": values,
                    "backend": "pyo3",
                    "output": f"Final side length: {final_metric}",
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "S": 0.0,
                    "values": [],
                    "backend": "pyo3",
                    "output": "No valid packing found.",
                }
        except Exception:
            pass

    # Binary Subprocess Fallback
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    rust_binary = os.path.join(repo_root, "packer_rs", "target", "release", "packer_rs.exe")
    if not os.path.exists(rust_binary):
        rust_binary = os.path.join(repo_root, "packer_rs", "target", "release", "packer_rs")

    if not os.path.exists(rust_binary) and not no_build:
        subprocess.run(
            ["cargo", "build", "--release"],
            cwd=os.path.join(repo_root, "packer_rs"),
            check=True,
            stdout=subprocess.DEVNULL,
        )

    cmd = [
        rust_binary,
        str(n_shapes), str(inner_shape), str(container_shape),
        "--attempts", str(attempts),
    ]
    if solution_file:
        cmd.extend(["--solution-file", solution_file])
    if target_s is not None:
        cmd.extend(["--target-s", str(target_s)])
    if time_limit is not None:
        cmd.extend(["--time-limit", str(time_limit)])

    init_json_path = None
    if initial_positions is not None:
        init_json_path = "tmp_init_pos.json"
        with open(init_json_path, "w") as f:
            json.dump(initial_positions, f)
        cmd.extend(["--initial-positions", init_json_path])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if init_json_path and os.path.exists(init_json_path):
            os.remove(init_json_path)

        if proc.returncode != 0:
            return {
                "success": False,
                "error": proc.stderr,
                "backend": "cli",
                "returncode": proc.returncode,
            }

        stdout = proc.stdout.strip()
        if "No valid packing found" in stdout:
            return {
                "success": False,
                "score": 0.0,
                "values": [],
                "backend": "cli",
                "output": stdout,
            }

        score = 0.0
        values = []
        for line in stdout.splitlines():
            if line.startswith("Final side length:"):
                score = float(line.split(":")[-1].strip())

        if solution_file and os.path.exists(solution_file):
            try:
                with open(solution_file, "r") as f:
                    data = json.load(f)
                    values = data.get("values", [])
            except Exception:
                pass

        return {
            "success": True,
            "score": score,
            "values": values,
            "backend": "cli",
            "output": stdout,
        }
    except Exception as e:
        if init_json_path and os.path.exists(init_json_path):
            os.remove(init_json_path)
        return {
            "success": False,
            "error": str(e),
            "backend": "cli",
        }
