# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Safe expression language for decision rules.

Rule conditions and outputs are written by business users (``days_to_due <= 3 and
risk_band == 'high'``), stored as data and evaluated many times per second, so they
must never be able to run arbitrary code. Expressions are parsed with Python's own
grammar, then checked against a strict allow-list of node types:

  * literals, lists/tuples, ``and`` / ``or`` / ``not``, comparisons (incl. chained,
    ``in`` / ``not in``), ``+ - * / // %``, unary minus, ``x if c else y``
  * names resolve to fields of the facts mapping; ``a.b`` and ``a['b']`` read nested
    mappings; unknown fields are ``None`` (never an exception)
  * calls only to registered functions (``min``, ``max``, ``abs``, ``round``, ``len``,
    ``lower``, ``upper``, ``coalesce``, ``days_until``, ``days_since``, ``date``)

Attribute access on objects, imports, lambdas, comprehensions, dunder names and any
unlisted call are rejected at compile time. Comparisons involving ``None`` or
incompatible types evaluate to ``False`` instead of raising, so a missing field makes
a rule not match rather than crash a whole evaluation run. Compiled expressions are
cached.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any

MAX_EXPRESSION_CHARS = 2000


class ExpressionError(ValueError):
    """An expression is malformed or uses something outside the allow-list."""


@dataclass(frozen=True)
class EvalContext:
    """Evaluation-time inputs that are not facts (deterministic 'now')."""

    today: date


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                return None
    return None


def _days_until(ctx: EvalContext, value: Any) -> int | None:
    target = _to_date(value)
    return None if target is None else (target - ctx.today).days


def _days_since(ctx: EvalContext, value: Any) -> int | None:
    target = _to_date(value)
    return None if target is None else (ctx.today - target).days


def _coalesce(_ctx: EvalContext, *values: Any) -> Any:
    return next((v for v in values if v is not None), None)


def _safe(fn: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(_ctx: EvalContext, *args: Any) -> Any:
        try:
            return fn(*args)
        except (TypeError, ValueError):
            return None

    return wrapped


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "min": _safe(lambda *a: min(x for x in a if x is not None)),
    "max": _safe(lambda *a: max(x for x in a if x is not None)),
    "abs": _safe(abs),
    "round": _safe(round),
    "len": _safe(len),
    "lower": _safe(lambda s: str(s).lower()),
    "upper": _safe(lambda s: str(s).upper()),
    "date": lambda _ctx, v: _to_date(v),
    "coalesce": _coalesce,
    "days_until": _days_until,
    "days_since": _days_since,
}

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_CMPOPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}
_ALLOWED = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Attribute,
    ast.Subscript,
    ast.Call,
    ast.IfExp,
    *_BINOPS,
    *_CMPOPS,
)


def _validate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExpressionError(f"'{type(node).__name__}' is not allowed in rule expressions")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ExpressionError("names starting with '__' are not allowed")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ExpressionError("private attributes are not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                name = getattr(node.func, "id", ast.unparse(node.func))
                raise ExpressionError(
                    f"function '{name}' is not available; use one of {sorted(FUNCTIONS)}"
                )
            if node.keywords:
                raise ExpressionError("keyword arguments are not supported")


@lru_cache(maxsize=4096)
def compile_expression(source: str) -> ast.Expression:
    """Parse and validate once; raises ExpressionError on anything unsafe or malformed."""
    if not isinstance(source, str) or not source.strip():
        raise ExpressionError("expression is empty")
    if len(source) > MAX_EXPRESSION_CHARS:
        raise ExpressionError(f"expression longer than {MAX_EXPRESSION_CHARS} characters")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression: {exc.msg}") from exc
    _validate(tree)
    return tree


def _lookup(container: Any, key: Any) -> Any:
    if isinstance(container, Mapping):
        return container.get(key)
    if isinstance(container, list | tuple) and isinstance(key, int):
        return container[key] if -len(container) <= key < len(container) else None
    return None


def _eval(node: ast.AST, facts: Mapping[str, Any], ctx: EvalContext) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, facts, ctx)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        return facts.get(node.id)
    if isinstance(node, ast.List | ast.Tuple):
        return [_eval(e, facts, ctx) for e in node.elts]
    if isinstance(node, ast.Attribute):
        return _lookup(_eval(node.value, facts, ctx), node.attr)
    if isinstance(node, ast.Subscript):
        return _lookup(_eval(node.value, facts, ctx), _eval(node.slice, facts, ctx))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = _eval(value, facts, ctx)
                if not result:
                    return result
            return result
        result = False
        for value in node.values:
            result = _eval(value, facts, ctx)
            if result:
                return result
        return result
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, facts, ctx)
        if isinstance(node.op, ast.Not):
            return not operand
        if operand is None:
            return None
        try:
            return -operand if isinstance(node.op, ast.USub) else +operand
        except TypeError:
            return None
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, facts, ctx), _eval(node.right, facts, ctx)
        if left is None or right is None:
            return None
        try:
            return _BINOPS[type(node.op)](left, right)
        except (TypeError, ZeroDivisionError, ValueError):
            return None
    if isinstance(node, ast.Compare):
        left = _eval(node.left, facts, ctx)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, facts, ctx)
            if not isinstance(op, ast.Is | ast.IsNot | ast.Eq | ast.NotEq) and (
                left is None or right is None
            ):
                return False
            try:
                if not _CMPOPS[type(op)](left, right):
                    return False
            except TypeError:
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body if _eval(node.test, facts, ctx) else node.orelse, facts, ctx)
    if isinstance(node, ast.Call):
        args = [_eval(a, facts, ctx) for a in node.args]
        return FUNCTIONS[node.func.id](ctx, *args)  # type: ignore[union-attr]
    raise ExpressionError(
        f"unsupported node {type(node).__name__}"
    )  # pragma: no cover - validated earlier


def evaluate(source: str, facts: Mapping[str, Any], today: date | None = None) -> Any:
    """Evaluate a rule expression against a facts mapping."""
    return _eval(compile_expression(source), facts, EvalContext(today=today or date.today()))


def referenced_fields(source: str) -> set[str]:
    """Top-level fact names an expression reads (for validation and documentation)."""
    tree = compile_expression(source)
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    return {
        n.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id not in called and n.id not in ("True", "False", "None")
    }
