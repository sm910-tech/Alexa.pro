"""
tools/calculator.py — Safe arithmetic evaluator

Uses Python's AST (Abstract Syntax Tree) to parse and evaluate
mathematical expressions without calling eval() on arbitrary code.

Supported: +, -, *, /, //, **, %, unary minus, parentheses,
           percentage expressions like "15% of 240"
"""

import ast
import math
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── Allowed AST node types ────────────────────────────────────────
_ALLOWED_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.USub, ast.UAdd,
}


def safe_calculate(expression: str) -> Optional[str]:
    """
    Evaluate a mathematical expression string safely.

    Returns the result as a formatted string, or None if the
    expression cannot be parsed.

    Examples:
        safe_calculate("15% of 240")  → "36"
        safe_calculate("(12 + 8) * 3") → "60"
        safe_calculate("2 ** 10")     → "1024"
    """
    if not expression:
        return None

    normalized = _normalize(expression)
    if normalized is None:
        return None

    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        log.debug("Calculator: parse error for %r", normalized)
        return None

    if not _is_safe(tree):
        log.warning("Calculator: unsafe expression rejected: %r", normalized)
        return None

    try:
        result = _evaluate(tree.body)
    except (ZeroDivisionError, OverflowError, ValueError) as exc:
        log.debug("Calculator: evaluation error: %s", exc)
        return str(exc)

    return _format_result(result)


# ── Normalization ─────────────────────────────────────────────────

def _normalize(expr: str) -> Optional[str]:
    """Convert natural-language math patterns to valid Python expressions."""
    expr = expr.strip()

    # "X% of Y" → "(X/100)*Y"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)$", expr, re.I)
    if m:
        return f"({m.group(1)}/100)*{m.group(2)}"

    # "X percent of Y"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*percent\s+of\s+(\d+(?:\.\d+)?)$", expr, re.I)
    if m:
        return f"({m.group(1)}/100)*{m.group(2)}"

    # Remove stray words that aren't operators or numbers
    cleaned = re.sub(r"[^\d\+\-\*\/\%\^\(\)\.\s]", "", expr)
    cleaned = cleaned.replace("^", "**")    # caret → exponent
    cleaned = cleaned.strip()
    return cleaned if cleaned else None


# ── Safety check ──────────────────────────────────────────────────

def _is_safe(tree: ast.AST) -> bool:
    """Return True only if every AST node is in the allowed set."""
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            return False
    return True


# ── Evaluation ────────────────────────────────────────────────────

def _evaluate(node: ast.expr) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")

    if isinstance(node, ast.BinOp):
        left  = _evaluate(node.left)
        right = _evaluate(node.right)
        op    = node.op
        if isinstance(op, ast.Add):      return left + right
        if isinstance(op, ast.Sub):      return left - right
        if isinstance(op, ast.Mult):     return left * right
        if isinstance(op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left / right
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left // right
        if isinstance(op, ast.Mod):      return left % right
        if isinstance(op, ast.Pow):
            if left == 0 and right < 0:
                raise ZeroDivisionError("0 cannot be raised to a negative power")
            return left ** right

    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand)
        if isinstance(node.op, ast.USub): return -operand
        if isinstance(node.op, ast.UAdd): return +operand

    raise ValueError(f"Unexpected node type: {type(node).__name__}")


# ── Formatting ────────────────────────────────────────────────────

def _format_result(value: float) -> str:
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    # Show up to 6 significant digits, strip trailing zeros
    formatted = f"{value:.6g}"
    return formatted
