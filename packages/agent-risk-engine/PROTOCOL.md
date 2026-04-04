# Agent Risk Protocol

A language-agnostic protocol for codifying risk in autonomous agent actions.

This document defines the portable data model and evaluation semantics. Implementations may use any language, any number of evaluation layers, and any analysis method — as long as they respect the core semantics defined here.

## Core Concepts

### Risk Levels

A 5-point integer scale with fixed semantics:

| Level | Name     | Meaning                          |
|-------|----------|----------------------------------|
| 1     | Info     | Read-only, no side effects       |
| 2     | Low      | Reads potentially sensitive data |
| 3     | Moderate | Reversible mutations             |
| 4     | High     | Hard-to-reverse mutations        |
| 5     | Critical | Destructive or irreversible      |

Implementations MUST use this 1-5 scale. The semantic meanings are normative — a "Level 3" action in one implementation should carry the same implications as in another.

### Gate Results

Three possible outcomes, in escalation order:

1. **allowed** — action may proceed without intervention
2. **needs_approval** — action requires human or system approval before proceeding
3. **denied** — action must not proceed

Escalation order is fixed: `allowed < needs_approval < denied`.

### Action Envelope

The input to risk evaluation. Every action is described by:

```json
{
  "kind": "tool_call",
  "name": "delete_file",
  "parameters": {"path": "/etc/config"},
  "risk": 4,
  "metadata": {"actor": "autonomous", "target": "production"}
}
```

| Field        | Type              | Required | Description |
|--------------|-------------------|----------|-------------|
| `kind`       | string            | yes      | Action category (see recommended kinds below) |
| `name`       | string            | yes      | Specific action identifier |
| `parameters` | object            | no       | Action-specific arguments |
| `risk`       | integer (1-5)     | yes      | Developer-assigned static risk level |
| `metadata`   | object            | no       | Contextual information (see recommended keys below) |

### Utility Score

An optional caller-provided signal indicating how valuable an action is to the agent's goals:

```json
{
  "level": 4,
  "reasoning": "User explicitly requested file creation"
}
```

Utility is an **input**, not computed by the engine. The calling framework understands agent goals and provides utility on the same 1-5 scale as risk.

## Evaluation Semantics

These rules are normative — all conforming implementations MUST respect them:

1. **Escalation only.** Later evaluation stages can only escalate decisions (allowed → needs_approval → denied), never relax them.

2. **Denied is final.** Once any stage produces a `denied` result, no subsequent stage may override it. Implementations SHOULD short-circuit remaining evaluation.

3. **Stateless evaluation.** The engine evaluates a single action in isolation. It does not track call history, session state, or temporal patterns internally. Temporal context is the framework's responsibility and flows in via `metadata`.

4. **Developer rules take precedence.** Explicitly codified rules (deny lists, allow lists, thresholds) cannot be overridden by agent reasoning or utility scores.

5. **Secure by default.** Unknown actions (those without explicit risk assignments) SHOULD default to the highest risk level.

## Recommended Action Kinds

These are advisory conventions, not a closed set:

| Kind              | Description                          |
|-------------------|--------------------------------------|
| `tool_call`       | Invoking an agent tool or function   |
| `file_write`      | Writing or modifying a file          |
| `file_delete`     | Deleting a file                      |
| `api_request`     | Making an HTTP/API call              |
| `code_execution`  | Executing code or shell commands     |
| `message_send`    | Sending a message (email, chat, etc) |
| `database_query`  | Executing a database operation       |

Implementations MAY define additional kinds.

## Recommended Metadata Keys

These are advisory conventions for interoperability:

| Key                   | Type    | Description                                  |
|-----------------------|---------|----------------------------------------------|
| `target`              | string  | Where the action is directed (host, endpoint)|
| `actor`               | string  | Who/what initiated the action                |
| `provenance`          | string  | How the action was initiated ("user_requested", "autonomous", "tool_chain") |
| `consecutive_repeats` | integer | How many times this action has been called consecutively |
| `session_duration`    | number  | Seconds since the session started            |

Implementations MAY define additional metadata keys.

## Conformance

An implementation conforms to this protocol if:

1. It uses the 1-5 risk level scale with the defined semantics
2. It produces one of the three gate results (allowed, needs_approval, denied)
3. It accepts the action envelope shape (or a language-idiomatic equivalent)
4. It respects all evaluation semantics (escalation-only, denied-is-final, stateless, developer-rules-first, secure-by-default)

The number of evaluation layers, the analysis method (regex, LLM, heuristic), how utility is computed, and how temporal context is tracked are implementation choices, not protocol requirements.

## Reference Implementation

The Python `agent-risk-engine` package is the reference implementation of this protocol. See [README.md](README.md) for usage.
