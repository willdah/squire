"""Alert rule condition evaluator.

Evaluates simple field comparison conditions against snapshot data.
No eval() — conditions are parsed into a structured format and evaluated safely.

Supported format: ``<field> <op> <value>``
  - field: dot-path into the snapshot dict (e.g., ``cpu_percent``, ``memory_used_mb``)
  - op: ``>``, ``<``, ``>=``, ``<=``, ``==``, ``!=``
  - value: number or string literal
"""

import operator
import re

_OPS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

_CONDITION_RE = re.compile(
    r"^\s*(?P<field>[\w.]+)\s*(?P<op>>=|<=|!=|==|>|<)\s*(?P<value>.+?)\s*$"
)


class ConditionError(ValueError):
    """Raised when a condition string is malformed."""


class ParsedCondition:
    """A parsed condition ready for evaluation."""

    __slots__ = ("field", "op_str", "op_fn", "value")

    def __init__(self, field: str, op_str: str, op_fn, value: float | str):
        self.field = field
        self.op_str = op_str
        self.op_fn = op_fn
        self.value = value

    def __repr__(self) -> str:
        return f"{self.field} {self.op_str} {self.value!r}"


def parse_condition(condition: str) -> ParsedCondition:
    """Parse a condition string into a structured representation.

    Args:
        condition: e.g. ``"cpu_percent > 90"`` or ``"memory_used_mb >= 14000"``

    Returns:
        A ParsedCondition ready for evaluation.

    Raises:
        ConditionError: If the condition string is malformed.
    """
    match = _CONDITION_RE.match(condition)
    if not match:
        raise ConditionError(
            f"Invalid condition: {condition!r}. "
            f"Expected format: <field> <op> <value> "
            f"(e.g., 'cpu_percent > 90')"
        )

    field = match.group("field")
    op_str = match.group("op")
    raw_value = match.group("value")

    op_fn = _OPS.get(op_str)
    if op_fn is None:
        raise ConditionError(f"Unknown operator: {op_str!r}")

    # Try to parse value as a number
    value: float | str
    try:
        value = float(raw_value)
        if value == int(value):
            value = int(value)
    except ValueError:
        # Strip quotes from string values
        value = raw_value.strip("'\"")

    return ParsedCondition(field=field, op_str=op_str, op_fn=op_fn, value=value)


def evaluate_condition(condition: ParsedCondition, snapshot: dict) -> bool:
    """Evaluate a parsed condition against a snapshot dict.

    Args:
        condition: A ParsedCondition from ``parse_condition()``.
        snapshot: A flat or nested snapshot dict.

    Returns:
        True if the condition is met, False otherwise.
        Returns False if the field is not found in the snapshot.
    """
    actual = _resolve_field(snapshot, condition.field)
    if actual is None:
        return False

    try:
        # Coerce types for comparison
        if isinstance(condition.value, (int, float)):
            actual = float(actual)
        return condition.op_fn(actual, condition.value)
    except (TypeError, ValueError):
        return False


def _resolve_field(data: dict, field: str):
    """Resolve a dot-path field in a nested dict.

    e.g., ``"containers.nginx.state"`` → ``data["containers"]["nginx"]["state"]``
    """
    parts = field.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            # Try numeric index
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current
