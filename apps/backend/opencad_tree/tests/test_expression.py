"""Tests for the safe expression evaluator."""

from __future__ import annotations

import math

import pytest

from opencad_tree.expression import ExpressionError, evaluate, extract_symbols


# ── Basic arithmetic ────────────────────────────────────────────────


def test_literal_int() -> None:
    assert evaluate("42") == 42.0


def test_literal_float() -> None:
    assert evaluate("3.14") == pytest.approx(3.14)


def test_addition() -> None:
    assert evaluate("1 + 2") == 3.0


def test_subtraction() -> None:
    assert evaluate("10 - 3") == 7.0


def test_multiplication() -> None:
    assert evaluate("4 * 5") == 20.0


def test_division() -> None:
    assert evaluate("10 / 4") == 2.5


def test_power() -> None:
    assert evaluate("2 ** 10") == 1024.0


def test_unary_neg() -> None:
    assert evaluate("-7") == -7.0


def test_complex_expression() -> None:
    assert evaluate("(2 + 3) * 4 - 1") == 19.0


# ── Variables ───────────────────────────────────────────────────────


def test_variable_resolution() -> None:
    assert evaluate("x + 1", {"x": 10}) == 11.0


def test_multiple_variables() -> None:
    assert evaluate("a * b + c", {"a": 2, "b": 3, "c": 4}) == 10.0


def test_unknown_variable_raises() -> None:
    with pytest.raises(ExpressionError, match="Unknown symbol 'z'"):
        evaluate("z + 1")


# ── Functions ───────────────────────────────────────────────────────


def test_sqrt() -> None:
    assert evaluate("sqrt(16)") == 4.0


def test_sin_cos() -> None:
    assert evaluate("sin(0)") == pytest.approx(0.0)
    assert evaluate("cos(0)") == pytest.approx(1.0)


def test_min_max() -> None:
    assert evaluate("min(3, 7)") == 3.0
    assert evaluate("max(3, 7)") == 7.0


def test_atan2() -> None:
    assert evaluate("atan2(1, 1)") == pytest.approx(math.atan2(1, 1))


def test_disallowed_function_raises() -> None:
    with pytest.raises(ExpressionError, match="not allowed"):
        evaluate("__import__('os')")


# ── Constants ───────────────────────────────────────────────────────


def test_pi_constant() -> None:
    assert evaluate("pi") == pytest.approx(math.pi)


def test_e_constant() -> None:
    assert evaluate("e") == pytest.approx(math.e)


# ── Safety ──────────────────────────────────────────────────────────


def test_attribute_access_rejected() -> None:
    with pytest.raises(ExpressionError):
        evaluate("x.__class__", {"x": 1})


def test_string_literal_rejected() -> None:
    with pytest.raises(ExpressionError):
        evaluate("'hello'")


def test_keyword_arg_rejected() -> None:
    with pytest.raises(ExpressionError, match="Keyword arguments"):
        evaluate("round(3.7, ndigits=1)")


# ── Symbol extraction ──────────────────────────────────────────────


def test_extract_simple() -> None:
    syms = extract_symbols("x + y * 2")
    assert syms == {"x", "y"}


def test_extract_ignores_constants_and_functions() -> None:
    syms = extract_symbols("sqrt(pi * r ** 2)")
    assert syms == {"r"}


def test_extract_syntax_error_raises() -> None:
    with pytest.raises(ExpressionError, match="syntax"):
        extract_symbols("1 +")
