import pytest
from src.shape_packing.cli import handle_run

class DummyArgs:
    pass

def test_cli_handle_run_with_solver_interface(tmp_path):
    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = None
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert "success" in res


def test_cli_handle_run_invalid_init_script_nonexistent():
    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = "nonexistent_script_xyz.py"
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert res.get("success") is False
    assert "does not exist" in res.get("error", "")


def test_cli_handle_run_invalid_init_script_wrong_extension(tmp_path):
    invalid_file = tmp_path / "bad_script.txt"
    invalid_file.write_text("echo hello")

    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = str(invalid_file)
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert res.get("success") is False
    assert "must be a Python (.py) file" in res.get("error", "")


def test_cli_handle_run_valid_init_script(tmp_path):
    record_file = tmp_path / "passed_path.txt"
    script_file = tmp_path / "my_init.py"
    record_path_str = str(record_file).replace("\\", "/")
    script_file.write_text(f"""
import sys, json
out_path = sys.argv[1]
with open("{record_path_str}", "w") as rf:
    rf.write(out_path)
with open(out_path, "w") as f:
    json.dump([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [-0.5, 0.0, 0.0]], f)
""")

    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = str(script_file)
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert "success" in res

    # Verify that predictable file was not created in cwd
    import os
    assert not os.path.exists("initial_positions.json")
    # Verify temporary file was used and cleaned up
    passed_temp_path = record_file.read_text().strip()
    assert not passed_temp_path.endswith("initial_positions.json")
    assert not os.path.exists(passed_temp_path)


def test_cli_handle_run_failing_init_script(tmp_path):
    script_file = tmp_path / "failing_init.py"
    script_file.write_text("""
raise RuntimeError("Custom initialization error")
""")

    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = str(script_file)
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert res.get("success") is False
    assert "Custom initialization error" in res.get("error", "")


def test_cli_handle_run_tan(tmp_path):
    args = DummyArgs()
    args.problem = "2_tan_in_4"
    args.attempts = 2
    args.init_script = None
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert "success" in res


def test_cli_handle_run_init_script_timeout(tmp_path, monkeypatch):
    import subprocess
    script_file = tmp_path / "timeout_init.py"
    script_file.write_text("import time\ntime.sleep(10)")

    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = str(script_file)
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    def mock_subprocess_run(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=120)

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    res = handle_run(args, direct_call=True)
    assert res.get("success") is False
    assert "timed out" in res.get("error", "")


def test_cli_handle_run_init_script_exit_code(tmp_path):
    script_file = tmp_path / "exit_code_init.py"
    script_file.write_text("import sys\nsys.exit(42)")

    args = DummyArgs()
    args.problem = "3_3_in_4"
    args.attempts = 10
    args.init_script = str(script_file)
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert res.get("success") is False
    assert res.get("returncode") == 42

