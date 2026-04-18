"""Defense-in-depth decorator for ADK tool functions.

Catches any uncaught exception from a tool and returns it as a string so
the LLM can reason about the failure instead of crashing the event loop.

When the wrapped tool declares a ``host`` parameter, the resolved host is
prepended to the result as ``[host=X]\\n…`` so the LLM always sees which
host produced the output without any prompt-side bookkeeping.
"""

import functools
import inspect
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def safe_tool(func: Callable) -> Callable:
    """Wrap an async tool function so exceptions become error strings.

    Preserves ``__name__``, ``__doc__``, and ``__signature__`` so ADK
    schema discovery continues to work. If ``func`` accepts a ``host``
    parameter, the resolved host is echoed back in the result envelope.
    """

    sig = inspect.signature(func)
    has_host = "host" in sig.parameters

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> str:
        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            logger.exception("Tool %s raised %s", func.__name__, type(exc).__name__)
            return f"Error: {type(exc).__name__}: {exc}"

        if not has_host:
            return result

        try:
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            host = bound.arguments.get("host", "local")
        except TypeError:
            host = "local"
        return f"[host={host}]\n{result}"

    wrapper.__signature__ = sig
    return wrapper
