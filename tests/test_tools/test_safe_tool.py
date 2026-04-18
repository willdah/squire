"""Tests for the safe_tool decorator."""

import asyncio
import inspect

import pytest

from squire.tools._safe import safe_tool


async def example_tool(host: str = "local", lines: int = 50) -> str:
    """An example tool docstring."""
    return f"ok: {host} {lines}"


async def raising_tool(host: str = "local") -> str:
    """A tool that always raises."""
    raise RuntimeError("something broke")


class TestPreservesMetadata:
    def test_name(self):
        wrapped = safe_tool(example_tool)
        assert wrapped.__name__ == "example_tool"

    def test_doc(self):
        wrapped = safe_tool(example_tool)
        assert wrapped.__doc__ == "An example tool docstring."

    def test_signature(self):
        wrapped = safe_tool(example_tool)
        sig = inspect.signature(wrapped)
        params = list(sig.parameters.keys())
        assert params == ["host", "lines"]
        assert sig.parameters["host"].default == "local"
        assert sig.parameters["lines"].default == 50

    def test_is_coroutine(self):
        wrapped = safe_tool(example_tool)
        assert asyncio.iscoroutinefunction(wrapped)


class TestExceptionCatching:
    @pytest.mark.asyncio
    async def test_catches_runtime_error(self):
        wrapped = safe_tool(raising_tool)
        result = await wrapped()
        assert result.startswith("Error: RuntimeError:")
        assert "something broke" in result

    @pytest.mark.asyncio
    async def test_catches_arbitrary_exception(self):
        async def bad_tool() -> str:
            raise ValueError("nope")

        wrapped = safe_tool(bad_tool)
        result = await wrapped()
        assert "ValueError" in result
        assert "nope" in result


class TestNormalPassthrough:
    @pytest.mark.asyncio
    async def test_returns_normal_value(self):
        wrapped = safe_tool(example_tool)
        result = await wrapped(host="remote", lines=10)
        assert result == "[host=remote]\nok: remote 10"

    @pytest.mark.asyncio
    async def test_default_args(self):
        wrapped = safe_tool(example_tool)
        result = await wrapped()
        assert result == "[host=local]\nok: local 50"

    @pytest.mark.asyncio
    async def test_no_host_parameter_no_prefix(self):
        async def hostless_tool(name: str) -> str:
            return f"ok: {name}"

        wrapped = safe_tool(hostless_tool)
        result = await wrapped(name="foo")
        assert result == "ok: foo"
