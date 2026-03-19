"""Chat WebSocket and session creation endpoints."""

import asyncio
import json
import logging
import uuid
from typing import Any

from agent_risk_engine import RiskEvaluator, RuleGate
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from ...agents import create_squire_agent
from ...callbacks.risk_gate import create_risk_gate
from ...config import RiskOverridesConfig
from ...tools import TOOL_RISK_LEVELS
from ..dependencies import get_app_config, get_db, get_llm_config, get_registry
from ..schemas import ChatSessionResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Active chat sessions: session_id -> (runner, session, agent)
_active_sessions: dict[str, tuple[InMemoryRunner, Any, Any]] = {}
_sessions_lock = asyncio.Lock()


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
    risk_overrides = RiskOverridesConfig()
    rule_gate = RuleGate(
        threshold=app_config.risk_tolerance,
        strict=app_config.risk_strict,
        allowed_tools=set(risk_overrides.allow),
        approve_tools=set(risk_overrides.approve),
        denied_tools=set(risk_overrides.deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate)

    snapshot = await get_latest_snapshot()
    session_state = {
        "risk_evaluator": risk_evaluator,
        "risk_tolerance": rule_gate.threshold,
        "latest_snapshot": snapshot,
        "house": app_config.house,
        "squire_name": app_config.squire_name,
        "squire_profile": app_config.squire_profile,
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
    )
    await db.create_session(session.id)

    async with _sessions_lock:
        _active_sessions[session.id] = (runner, session, agent)

    return ChatSessionResponse(session_id=session.id)


@router.websocket("/ws/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """Bidirectional chat WebSocket with streaming responses."""
    await websocket.accept()

    from .. import dependencies as deps
    from ..app import get_latest_snapshot

    app_config = deps.get_app_config()
    llm_config = deps.get_llm_config()
    registry = deps.get_registry()
    db = deps.db
    notifier = deps.notifier

    # Create approval bridge for this WebSocket connection
    approval_bridge = WebApprovalBridge(websocket)

    # Build agent with approval bridge wired in
    def _make_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            approval_provider=approval_bridge,
        )

    if app_config.multi_agent:
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory=_make_risk_gate,
        )
    else:
        risk_gate_callback = create_risk_gate(
            tool_risk_levels=TOOL_RISK_LEVELS,
            approval_provider=approval_bridge,
        )
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            before_tool_callback=risk_gate_callback,
        )

    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=adk_app)

    # Build session state
    risk_overrides = RiskOverridesConfig()
    rule_gate = RuleGate(
        threshold=app_config.risk_tolerance,
        strict=app_config.risk_strict,
        allowed_tools=set(risk_overrides.allow),
        approve_tools=set(risk_overrides.approve),
        denied_tools=set(risk_overrides.deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate)
    snapshot = await get_latest_snapshot()

    session_state = {
        "risk_evaluator": risk_evaluator,
        "risk_tolerance": rule_gate.threshold,
        "latest_snapshot": snapshot,
        "house": app_config.house,
        "squire_name": app_config.squire_name,
        "squire_profile": app_config.squire_profile,
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

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
                    )
                )
                continue

            await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for session %s", session_id)
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()
        async with _sessions_lock:
            _active_sessions.pop(session_id, None)


async def _stream_response(
    websocket: WebSocket,
    runner: InMemoryRunner,
    session,
    agent,
    user_text: str,
    app_config,
    db,
    notifier,
) -> None:
    """Run the agent and stream response tokens over WebSocket."""
    message = types.Content(parts=[types.Part(text=user_text)])
    response_parts = []
    run_config = RunConfig(streaming_mode=StreamingMode.SSE)

    try:
        final_text = ""

        async for event in runner.run_async(
            user_id=app_config.user_id,
            session_id=session.id,
            new_message=message,
            run_config=run_config,
        ):
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
                    await websocket.send_json(
                        {
                            "type": "tool_result",
                            "name": fr.name,
                            "output": str(fr.response)[:500],
                            "request_id": "",
                        }
                    )

                elif part.text and event.partial:
                    response_parts.append(part.text)
                    await websocket.send_json({"type": "token", "content": part.text})

                elif part.text and event.is_final_response():
                    final_text = part.text
                    # In multi-agent mode, partial tokens may have streamed
                    # the root agent's text while the sub-agent's response
                    # arrives only in the final event.  Send any genuinely
                    # new content as a token so the frontend displays it.
                    streamed = "".join(response_parts)
                    if final_text and final_text != streamed:
                        delta = (
                            final_text[len(streamed):]
                            if streamed and final_text.startswith(streamed)
                            else final_text
                        )
                        if delta.strip():
                            response_parts.append(delta)
                            await websocket.send_json(
                                {"type": "token", "content": delta}
                            )

        full_response = final_text or "".join(response_parts)
        await websocket.send_json({"type": "message_complete", "content": full_response})

        # Persist assistant response
        if db and full_response:
            await db.save_message(session_id=session.id, role="assistant", content=full_response)
            await db.update_session_active(session.id)

    except asyncio.CancelledError:
        partial = final_text or "".join(response_parts)
        try:
            await websocket.send_json({"type": "message_complete", "content": partial, "stopped": True})
            if db and partial:
                await db.save_message(session_id=session.id, role="assistant", content=partial)
                await db.update_session_active(session.id)
        except Exception:
            pass
    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.exception("Error streaming response")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
