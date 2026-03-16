"""Defense-in-depth decorator for ADK tool functions.

Catches any uncaught exception from a tool and returns it as a string so
the LLM can reason about the failure instead of crashing the event loop.
"""

import functools
import inspect
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def safe_tool(func: Callable) -> Callable:
    """Wrap an async tool function so exceptions become error strings.

    Preserves ``__name__``, ``__doc__``, and ``__signature__`` so ADK
    schema discovery continues to work.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> str:
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            logger.exception("Tool %s raised %s", func.__name__, type(exc).__name__)
            return f"Error: {type(exc).__name__}: {exc}"

    # functools.wraps copies __name__ and __doc__ but not __signature__
    wrapper.__signature__ = inspect.signature(func)
    return wrapper
