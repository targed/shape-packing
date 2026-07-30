"""
Tests for src/shape_packing/problems.py

Covers:
- parse_problem
- shape_token_to_sides
- is_special_shape
- validate_problem
- problem_to_packer_args
"""
import pytest
from shape_packing.problems import (
    parse_problem,
    shape_token_to_sides,
    is_special_shape,
    validate_problem,
    problem_to_packer_args,
    Problem,
)


class TestParseProblem:
    def test_basic_regular(self):
        p = parse_problem("8_3_in_5")
        assert p.name == "8_3_in_5"
        assert p.N == 8
        assert p.inner_token == "3"
        assert p.container_token == "5"

    def test_circle_container(self):
        p = parse_problem("10_4_in_CIRCLE")
        assert p.N == 10
        assert p.inner_token == "4"
        assert p.container_token == "CIRCLE"

    def test_special_inner(self):
        p = parse_problem("12_DOMINO_in_4")
        assert p.N == 12
        assert p.inner_token == "DOMINO"
        assert p.container_token == "4"

    def test_l_shape(self):
        p = parse_problem("10_L_in_6")
        assert p.N == 10
        assert p.inner_token == "L"
        assert p.container_token == "6"

    def test_invalid_format_too_short(self):
        with pytest.raises(ValueError, match="Invalid problem format"):
            parse_problem("8_3")

    def test_invalid_format_missing_in(self):
        with pytest.raises(ValueError, match="Invalid problem format"):
            parse_problem("8_3_on_5")

    def test_invalid_format_non_int_N(self):
        with pytest.raises(ValueError, match="Invalid problem format"):
            parse_problem("abc_3_in_5")


class TestShapeTokenToSides:
    def test_numeric_tokens(self):
        assert shape_token_to_sides("3") == 3
        assert shape_token_to_sides("4") == 4
        assert shape_token_to_sides("8") == 8

    def test_large_numeric(self):
        assert shape_token_to_sides("12") == 12

    def test_circle_from_config(self):
        # CIRCLE mapped via SHAPE_TO_SIDES
        s = shape_token_to_sides("CIRCLE")
        assert s is not None and s >= 3

    def test_square_alias(self):
        s = shape_token_to_sides("SQUARE")
        assert s == 4

    def test_special_shape_returns_none(self):
        assert shape_token_to_sides("TAN") is None
        assert shape_token_to_sides("DOMINO") is None
        assert shape_token_to_sides("L") is None

    def test_unknown_token_raises(self):
        with pytest.raises(ValueError, match="Cannot map shape token"):
            shape_token_to_sides("UNKNOWN")

    def test_too_small_numeric_raises(self):
        with pytest.raises(ValueError, match="Cannot map shape token"):
            shape_token_to_sides("2")


class TestIsSpecialShape:
    def test_tan(self):
        assert is_special_shape("TAN") is True
        assert is_special_shape("tan") is True

    def test_domino(self):
        assert is_special_shape("DOMINO") is True
        assert is_special_shape("domino") is True

    def test_l(self):
        assert is_special_shape("L") is True

    def test_regular_not_special(self):
        assert is_special_shape("3") is False
        assert is_special_shape("CIRCLE") is False


class TestValidateProblem:
    def test_valid_regular(self):
        p = parse_problem("5_3_in_5")
        # Should not raise
        validate_problem(p)

    def test_valid_circle(self):
        p = parse_problem("10_4_in_CIRCLE")
        validate_problem(p)

    def test_valid_special_inner(self):
        p = parse_problem("8_TAN_in_4")
        validate_problem(p)

    def test_invalid_N_zero(self):
        p = Problem(name="0_3_in_4", N=0, inner_token="3", container_token="4")
        with pytest.raises(ValueError, match="N must be > 0"):
            validate_problem(p)

    def test_invalid_N_negative(self):
        p = Problem(name="-1_3_in_4", N=-1, inner_token="3", container_token="4")
        with pytest.raises(ValueError, match="N must be > 0"):
            validate_problem(p)

    def test_unknown_inner_token(self):
        p = Problem(name="5_UNKNOWN_in_4", N=5, inner_token="UNKNOWN", container_token="4")
        with pytest.raises(ValueError, match="unknown inner token"):
            validate_problem(p)


class TestProblemToPackerArgs:
    def test_regular_polygon(self):
        p = parse_problem("6_4_in_8")
        N, inner, container = problem_to_packer_args(p)
        assert N == 6
        assert inner == 4
        assert container == 8

    def test_circle_container(self):
        p = parse_problem("10_3_in_CIRCLE")
        N, inner, container = problem_to_packer_args(p)
        assert N == 10
        assert inner == 3
        assert container is not None
        assert container >= 3

    def test_special_inner_returns_none(self):
        p = parse_problem("12_DOMINO_in_4")
        N, inner, container = problem_to_packer_args(p)
        assert N == 12
        assert inner is None
        assert container == 4


class TestValidateEdgeCases:
    def test_numeric_token_less_than_3(self):
        # _validate_token: int("2") succeeds but < 3 triggers raise.
        # However shape_token_to_sides already intercepts "2" with a generic
        # ValueError; here we test validate_problem with a token that is
        # numeric-like but <3 and not in SHAPE_TO_SIDES -> unknown token path.
        p = Problem(name="5_2_in_4", N=5, inner_token="2", container_token="4")
        with pytest.raises(ValueError):
            validate_problem(p)


class TestListProblemFamilies:
    def test_returns_list(self):
        from shape_packing.problems import list_problem_families
        families = list_problem_families()
        assert isinstance(families, list)
        assert len(families) > 10
