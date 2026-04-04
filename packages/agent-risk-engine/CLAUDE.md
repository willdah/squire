# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`agent-risk-engine` is a zero-dependency, framework-agnostic Python package that evaluates whether an autonomous agent's action should be allowed, require approval, or be denied. It implements the Agent Risk Protocol (see `PROTOCOL.md`), operating on an `Action` envelope that describes any agent operation — tool calls, file writes, API requests, code execution, etc.

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

The evaluation pipeline has three layers, orchestrated by `RiskEvaluator` (`assessment.py`):

1. **RuleGate** (`rule_gate.py`) — Fast static rules. Compares action risk (1-5) against a threshold with per-name override sets (allowed/approve/denied) and per-kind threshold routing. Fully implemented. Evaluation order: denied → allowed → approve → threshold comparison.
2. **ActionAnalyzer** (`analyzer.py`) — Protocol interface for argument-aware risk analysis. Ships with `PassthroughAnalyzer` (stub) and `PatternAnalyzer` (regex-based, with kind-scoped patterns).
3. **ActionGate** (`action_gate.py`) — Protocol interface for final go/no-go decision integrating risk and utility signals. Ships with `PassthroughActionGate` (stub) and `RiskUtilityGate` (escalation-only gate).

**CallTracker** (`call_tracker.py`) — Standalone utility for loop/repetition detection. Not part of the pipeline — frameworks use it to build context for `Action.metadata`.

`RiskEvaluator.evaluate()` is async and stateless. Layer 1 short-circuits on DENIED before running layers 2-3.

All data models are frozen dataclasses in `models.py`. The core input is `Action(kind, name, parameters, risk, metadata)`. Three possible outcomes: `GateResult.ALLOWED`, `GateResult.NEEDS_APPROVAL`, `GateResult.DENIED`.
