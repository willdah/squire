# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`agent-risk-engine` is a zero-dependency, framework-agnostic Python library that evaluates whether an AI agent's tool call should be allowed, require user approval, or be denied. It operates entirely on primitives (`tool_name: str`, `args: dict`, `tool_risk: int`).

## Build & Development

- **Python**: Requires 3.12+
- **Build system**: Hatchling (`pyproject.toml`)
- **Package manager**: uv
- **Install for development**: `uv pip install -e ".[test]"`
- **Run all tests**: `uv run pytest`
- **Run a single test file**: `uv run pytest tests/test_rule_gate.py`
- **Run a single test**: `uv run pytest tests/test_rule_gate.py::TestEvaluationOrder::test_denied_always_denied`
- **Test deps**: pytest, pytest-asyncio (async tests use `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed)

## Architecture

The evaluation pipeline has four layers, orchestrated by `RiskEvaluator` (`assessment.py`):

1. **RuleGate** (`rule_gate.py`) — Fast static rules. Compares tool risk (1-5) against a threshold with per-tool override sets (allowed/approve/denied). Fully implemented. Evaluation order: denied_tools → allowed_tools → approve_tools → threshold comparison.
2. **ToolAnalyzer** (`analyzer.py`) — Protocol interface for argument-aware risk analysis. Ships as `PassthroughAnalyzer` stub.
3. **StateMonitor** (`state_monitor.py`) — Protocol interface for system health context (loop detection, rate limits). Ships as `NullStateMonitor` stub.
4. **ActionGate** (`action_gate.py`) — Protocol interface for final go/no-go decision integrating all signals. Ships as `PassthroughActionGate` stub.

`RiskEvaluator.evaluate()` is async. Layer 1 short-circuits on DENIED before running layers 2-4.

All data models are frozen dataclasses in `models.py`. Three possible outcomes: `GateResult.ALLOWED`, `GateResult.NEEDS_APPROVAL`, `GateResult.DENIED`.
