"""Tool effect classification — read vs. write vs. mixed.

`effect` is UI metadata describing what a tool does to system state:
- ``read``  — observes only (no mutation)
- ``write`` — mutates state
- ``mixed`` — both, or depends on arguments (e.g. ``run_command``)

Effect is orthogonal to risk level. A ``write`` can be low risk; a ``read``
can be sensitive. This module is deliberately dependency-free so it can be
imported by both ``squire.tools`` and ``squire.api`` without circular imports.
"""

from typing import Literal

Effect = Literal["read", "write", "mixed"]


def derive_effect(per_action: dict[str, Effect]) -> Effect:
    """Collapse a per-action effect map to a single tool-level effect.

    Returns ``"read"`` if every action reads, ``"write"`` if every action
    writes, and ``"mixed"`` otherwise. Raises ``ValueError`` on empty input.
    """
    if not per_action:
        raise ValueError("per_action must not be empty")
    values = set(per_action.values())
    if values == {"read"}:
        return "read"
    if values == {"write"}:
        return "write"
    return "mixed"
