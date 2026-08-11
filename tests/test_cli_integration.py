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
