"""Chat WebSocket and session creation endpoints."""

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from agent_risk_engine import RiskEvaluator, RuleGate
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from ...agents import create_squire_agent
from ...callbacks.risk_gate import ADK_INTERNAL_TOOLS, build_pattern_analyzer, create_risk_gate
from ...tools import TOOL_RISK_LEVELS
from ...types import RiskGateFactory
from .. import dependencies as deps
from ..dependencies import get_app_config, get_db, get_llm_config, get_registry
from ..schemas import ChatSessionResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Cap persisted tool/error detail length to match WebSocket ``tool_result.output`` (500 chars)
# so Activity does not retain more sensitive command output than live chat clients surface.
_EVENT_LOG_DETAIL_MAX = 500

_SKILL_COMPLETE_RE = re.compile(r"\[SKILL\s+COMPLETE\]", re.IGNORECASE)

_RAW_TOOL_CALL_RE = re.compile(r'\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:\s*\{[^}]*\}\s*\}')


def _is_skill_complete(text: str) -> bool:
    """Check whether [SKILL COMPLETE] marker is present in text."""
    return bool(_SKILL_COMPLETE_RE.search(text))


def _strip_raw_tool_calls(text: str) -> str:
    """Remove tool-call JSON blobs the model sometimes emits as plain text.

    Some models output ``{"name": "...", "parameters": {...}}`` as text
    instead of using structured function calling.  Strip these so they
    don't appear in chat or get persisted to the database.
    """
    cleaned = _RAW_TOOL_CALL_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _extract_token_usage_from_event(event: Any) -> tuple[int | None, int | None, int | None]:
    """Extract provider-reported token usage from an ADK event."""
    usage = getattr(event, "usage_metadata", None)
    if not usage:
        return None, None, None
    return (
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        getattr(usage, "total_token_count", None),
    )


def _accumulate_token_count(current: int | None, event_value: int | None) -> int | None:
    """Accumulate token usage across all events in a single turn."""
    if event_value is None:
        return current
    if current is None:
        return event_value
    return current + event_value


def _should_persist_assistant_turn(
    content: str,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
) -> bool:
    """Persist assistant messages when there is visible content or token usage."""
    return bool(content) or any(value is not None for value in (input_tokens, output_tokens, total_tokens))


class WebApprovalBridge:
    """WebSocket-based approval provider for the risk gate.

    Implements AsyncApprovalProvider so the risk gate can ``await`` the
    approval request without blocking the event loop. The approval dialog
    is sent over the WebSocket and the bridge waits for the client's response
    via an asyncio.Future.
    """

    def __init__(self, websocket: WebSocket):
        self._ws = websocket
        self._pending: dict[str, asyncio.Future[bool]] = {}

    async def request_approval_async(self, tool_name: str, args: dict[str, Any], risk_level: int) -> bool:
        """Request approval — awaited from the async risk gate callback."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        request_id = str(uuid.uuid4())
        self._pending[request_id] = future

        await self._ws.send_json(
            {
                "type": "approval_request",
                "request_id": request_id,
                "tool_name": tool_name,
                "args": args,
                "risk_level": risk_level,
            }
        )

        try:
            return await asyncio.wait_for(future, timeout=120)
        except TimeoutError:
            return False
        finally:
            self._pending.pop(request_id, None)

    def resolve_approval(self, request_id: str, approved: bool) -> None:
        """Resolve a pending approval request from the client."""
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(approved)


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
async def create_chat_session(
    app_config=Depends(get_app_config),
    llm_config=Depends(get_llm_config),
    db=Depends(get_db),
    registry=Depends(get_registry),
):
    """Create a new chat session, returning a session_id for the WebSocket."""
    from ..app import get_latest_snapshot

    # Build a temporary agent and runner for this session.
    # No approval bridge yet — it's wired in when the WebSocket connects.
    # For multi-agent mode, provide a no-op risk gate factory.
    def _placeholder_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(tool_risk_levels=tool_risk_levels)

    if app_config.multi_agent:
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory=_placeholder_risk_gate,
        )
    else:
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            before_tool_callback=create_risk_gate(tool_risk_levels=TOOL_RISK_LEVELS),
        )
    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=adk_app)

    # Build risk evaluation pipeline
    guardrails = deps.guardrails
    rule_gate = RuleGate(
        threshold=guardrails.risk_tolerance,
        strict=guardrails.risk_strict,
        allowed=set(guardrails.tools_allow),
        approve=set(guardrails.tools_require_approval),
        denied=set(guardrails.tools_deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate, analyzer=build_pattern_analyzer())

    snapshot = await get_latest_snapshot()
    session_state = {
        "risk_evaluator": risk_evaluator,
        "risk_tolerance": rule_gate.threshold,
        "latest_snapshot": snapshot,
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
    )
    await db.create_session(session.id)

    return ChatSessionResponse(session_id=session.id)


@router.websocket("/ws/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """Bidirectional chat WebSocket with streaming responses."""
    await websocket.accept()

    # Read skill name from query params directly (more reliable than
    # FastAPI parameter injection for WebSocket endpoints).
    skill_name = websocket.query_params.get("skill") or None

    from ..app import get_latest_snapshot

    app_config = deps.get_app_config()
    llm_config = deps.get_llm_config()
    registry = deps.get_registry()
    db = deps.db
    notifier = deps.notifier

    # Create approval bridge for this WebSocket connection
    approval_bridge = WebApprovalBridge(websocket)

    # Build agent with approval bridge wired in.
    # For multi-agent, each sub-agent gets its own factory with per-agent tolerance.
    guardrails_snapshot = deps.guardrails

    def _make_risk_gate(tool_risk_levels: dict[str, int], agent_tolerance: int | None = None):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            risk_overrides=dict(guardrails_snapshot.tools_risk_overrides),
            approval_provider=approval_bridge,
            default_threshold=agent_tolerance,
        )

    # Skills require direct tool access, so always use single-agent mode
    # when executing a skill.  In multi-agent mode the root agent has no
    # tools and cannot carry out skill instructions itself.
    use_multi_agent = app_config.multi_agent and not skill_name

    if use_multi_agent:
        agent_tolerances = {
            "Monitor": guardrails_snapshot.monitor_tolerance,
            "Container": guardrails_snapshot.container_tolerance,
            "Admin": guardrails_snapshot.admin_tolerance,
            "Notifier": guardrails_snapshot.notifier_tolerance,
        }

        def _resolve_threshold(name: str) -> int | None:
            tol = agent_tolerances.get(name)
            return RuleGate(threshold=tol).threshold if tol else None

        def _per_agent_factory(agent_name: str) -> RiskGateFactory:
            threshold = _resolve_threshold(agent_name)

            def factory(tool_risk_levels: dict[str, int]):
                return _make_risk_gate(tool_risk_levels, agent_tolerance=threshold)

            return factory

        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory_builder=_per_agent_factory,
        )
    else:
        risk_gate_callback = create_risk_gate(
            tool_risk_levels=TOOL_RISK_LEVELS,
            risk_overrides=dict(deps.guardrails.tools_risk_overrides),
            approval_provider=approval_bridge,
        )
        # Override multi_agent so create_squire_agent takes the
        # single-agent path even when the global config says otherwise.
        agent_config = app_config.model_copy(update={"multi_agent": False})
        agent = create_squire_agent(
            app_config=agent_config,
            llm_config=llm_config,
            before_tool_callback=risk_gate_callback,
        )

    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=adk_app)

    # Build session state
    guardrails = deps.guardrails
    rule_gate = RuleGate(
        threshold=guardrails.risk_tolerance,
        strict=guardrails.risk_strict,
        allowed=set(guardrails.tools_allow),
        approve=set(guardrails.tools_require_approval),
        denied=set(guardrails.tools_deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate, analyzer=build_pattern_analyzer())
    snapshot = await get_latest_snapshot()

    session_state = {
        "risk_evaluator": risk_evaluator,
        "risk_tolerance": rule_gate.threshold,
        "latest_snapshot": snapshot,
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

    # Load skill context into session state if a skill name was provided.
    # This MUST happen before create_session because InMemorySessionService
    # deep-copies the state dict — later mutations won't be visible.
    skill_active = False
    if skill_name and deps.skills_service:
        skill_data = deps.skills_service.get_skill(skill_name)
        if skill_data and skill_data.instructions:
            skill_active = True
            session_state["active_skill"] = {
                "skill_name": skill_data.name,
                "hosts": skill_data.hosts,
                "instructions": skill_data.instructions,
            }
            logger.info("Loaded skill '%s' into session %s", skill_name, session_id)
        else:
            logger.warning("Skill '%s' not found or has no instructions", skill_name)

    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
        session_id=session_id,
    )

    # Replay prior messages so the LLM has context
    if db:
        prior = await db.get_messages(session_id)
        if prior:
            for msg in prior:
                content_text = msg.get("content", "")
                if not content_text:
                    continue
                role = msg.get("role", "user")
                from google.adk.events.event import Event

                event = Event(
                    author="user" if role == "user" else agent.name,
                    invocation_id=Event.new_id(),
                    content=types.Content(
                        role=role,
                        parts=[types.Part(text=content_text)],
                    ),
                )
                await runner.session_service.append_event(session, event)

    streaming_task: asyncio.Task | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "approval_response":
                approval_bridge.resolve_approval(msg.get("request_id", ""), msg.get("approved", False))
                continue

            if msg_type == "stop_generation":
                if streaming_task and not streaming_task.done():
                    streaming_task.cancel()
                continue

            if msg_type == "message":
                content = msg.get("content", "").strip()
                if not content:
                    continue

                # Wait for any prior streaming to finish
                if streaming_task and not streaming_task.done():
                    await streaming_task

                # Persist user message
                if db:
                    await db.save_message(session_id=session_id, role="user", content=content)

                # Stream the agent response as a background task so the
                # receive loop stays active for approval_response messages.
                streaming_task = asyncio.create_task(
                    _stream_response(
                        websocket=websocket,
                        runner=runner,
                        session=session,
                        agent=agent,
                        user_text=content,
                        app_config=app_config,
                        db=db,
                        notifier=notifier,
                        skill_active=skill_active,
                    )
                )
                # Only auto-continue for the first message (skill execution).
                # Subsequent user messages are normal chat turns.
                skill_active = False
                continue

            await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for session %s", session_id)
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()


async def _stream_response(
    websocket: WebSocket,
    runner: InMemoryRunner,
    session,
    agent,
    user_text: str,
    app_config,
    db,
    notifier,
    skill_active: bool = False,
) -> None:
    """Run the agent and stream response tokens over WebSocket.

    When ``skill_active`` is set, the agent is automatically re-prompted
    after each turn so it works through the skill instructions without the
    user having to send "continue" manually.
    """
    max_turns = 15 if skill_active else 1
    current_text = user_text

    try:
        all_response_text = ""
        prev_response = ""

        for turn in range(max_turns):
            turn_response, tools_used, input_tokens, output_tokens, total_tokens = await _run_single_turn(
                websocket=websocket,
                runner=runner,
                session=session,
                agent=agent,
                user_text=current_text,
                app_config=app_config,
                db=db,
            )

            # Persist assistant response
            if db and _should_persist_assistant_turn(turn_response, input_tokens, output_tokens, total_tokens):
                await db.save_message(
                    session_id=session.id,
                    role="assistant",
                    content=turn_response,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
                await db.update_session_active(session.id)

            # If this is not a skill session or we've exhausted turns, stop.
            if not skill_active or turn >= max_turns - 1:
                await websocket.send_json({"type": "message_complete", "content": turn_response})
                break

            await websocket.send_json({"type": "message_complete", "content": turn_response})

            all_response_text += "\n" + turn_response

            # Stop if [SKILL COMPLETE] marker detected (only when tools were used).
            if tools_used and _is_skill_complete(all_response_text):
                break

            # Safety: stop if the agent repeated itself verbatim.
            if turn > 0 and turn_response == prev_response:
                break
            prev_response = turn_response

            current_text = "Continue executing the skill. Use your tools."
            if db:
                await db.save_message(session_id=session.id, role="user", content=current_text)

    except asyncio.CancelledError:
        try:
            await websocket.send_json({"type": "message_complete", "content": "", "stopped": True})
        except Exception:
            pass
    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.exception("Error streaming response")
        err_text = str(e)
        if db:
            await db.log_event(
                category="error",
                summary="Chat streaming error",
                session_id=session.id,
                details=err_text[:_EVENT_LOG_DETAIL_MAX],
            )
        try:
            await websocket.send_json({"type": "error", "message": err_text})
        except Exception:
            pass


async def _run_single_turn(
    websocket: WebSocket,
    runner: InMemoryRunner,
    session,
    agent,
    user_text: str,
    app_config,
    db,
) -> tuple[str, bool, int | None, int | None, int | None]:
    """Run one agent turn and stream events over the WebSocket.

    Returns:
        A tuple of (response_text, tools_were_called, input_tokens, output_tokens, total_tokens).
    """
    message = types.Content(parts=[types.Part(text=user_text)])
    response_parts: list[str] = []
    run_config = RunConfig(streaming_mode=StreamingMode.SSE)
    final_text = ""
    tools_called = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    async for event in runner.run_async(
        user_id=app_config.user_id,
        session_id=session.id,
        new_message=message,
        run_config=run_config,
    ):
        event_input_tokens, event_output_tokens, event_total_tokens = _extract_token_usage_from_event(event)
        input_tokens = _accumulate_token_count(input_tokens, event_input_tokens)
        output_tokens = _accumulate_token_count(output_tokens, event_output_tokens)
        total_tokens = _accumulate_token_count(total_tokens, event_total_tokens)

        if not event.content or not event.content.parts:
            continue

        for part in event.content.parts:
            if getattr(part, "thought", False):
                continue

            if part.function_call:
                fc = part.function_call
                # Reset so response_parts only tracks the text
                # segment *after* this tool call (prevents
                # concatenating prior sub-agent text into
                # message_complete).
                response_parts = []
                if fc.name in ADK_INTERNAL_TOOLS:
                    continue
                tools_called = True
                request_id = str(uuid.uuid4())
                await websocket.send_json(
                    {
                        "type": "tool_call",
                        "name": fc.name,
                        "args": fc.args or {},
                        "request_id": request_id,
                    }
                )
                if db:
                    await db.log_event(
                        category="tool_call",
                        summary=f"Called {fc.name}",
                        session_id=session.id,
                        tool_name=fc.name,
                        details=json.dumps(fc.args or {}),
                    )

            elif part.function_response:
                fr = part.function_response
                response_parts = []
                if fr.name in ADK_INTERNAL_TOOLS:
                    continue
                output_text = str(fr.response) if fr.response is not None else ""
                clipped = output_text[:_EVENT_LOG_DETAIL_MAX]
                await websocket.send_json(
                    {
                        "type": "tool_result",
                        "name": fr.name,
                        "output": clipped,
                        "request_id": "",
                    }
                )
                if db:
                    await db.log_event(
                        category="tool_result",
                        summary=f"Completed {fr.name or 'tool'}",
                        session_id=session.id,
                        tool_name=fr.name,
                        details=clipped,
                    )

            elif part.text and event.partial:
                response_parts.append(part.text)
                await websocket.send_json({"type": "token", "content": part.text})

            elif part.text and event.is_final_response():
                final_text = part.text
                streamed = "".join(response_parts)
                if final_text and final_text != streamed:
                    delta = final_text[len(streamed) :] if streamed and final_text.startswith(streamed) else final_text
                    if delta.strip():
                        response_parts.append(delta)
                        await websocket.send_json({"type": "token", "content": delta})

    raw = final_text or "".join(response_parts)
    return _strip_raw_tool_calls(raw), tools_called, input_tokens, output_tokens, total_tokens
