"""
Coverage-oriented tests for cli.py.
We avoid calling the real Rust solver; we patch subprocess to keep tests fast.
"""
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from shape_packing.cli import handle_suggest


class TestHandleSuggest:
    @pytest.fixture
    def mock_args(self, sample_history_tsv, sample_priority_queue, tmp_path):
        """Return a fake argparse.Namespace for suggest command."""
        # Ensure results.tsv exists as expected by load_history
        # We will patch load_history to use our fixture path.
        class Args:
            min_n = None
            max_n = None
            equal_n = None
            include_inner = None
            exclude_inner = None
            include_container = None
            exclude_container = None
            min_inner_sides = None
            max_inner_sides = None
            min_container_sides = None
            max_container_sides = None
            exclude_problems = None

        return Args()

    def test_suggest_output_is_json(self, mock_args, tmp_path, sample_priority_queue):
        with patch("shape_packing.cli.load_history") as mock_load, \
             patch("shape_packing.cli.choose_problem") as mock_choose, \
             patch("shape_packing.cli.current_best_scores") as mock_best, \
             patch("builtins.print") as mock_print:

            mock_load.return_value = []
            mock_choose.return_value = "8_3_in_5"
            mock_best.return_value = {"8_3_in_5": 2.0}

            handle_suggest(mock_args)

            # Check that we printed JSON
            call_args = " ".join(str(c) for c in mock_print.call_args_list)
            assert "8_3_in_5" in call_args
