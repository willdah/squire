"""Chat pane — message list and input widget for the Squire TUI."""

import json

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from ..database.service import DatabaseService
from ..notifications.webhook import WebhookDispatcher


class MessageBubble(Static):
    """A single chat message displayed in the conversation."""

    DEFAULT_CSS = """
    MessageBubble {
        margin: 0 1;
        padding: 0 1;
    }

    MessageBubble.user {
        color: $text;
        background: $primary 20%;
        border-left: thick $primary;
    }

    MessageBubble.assistant {
        color: $text;
        background: $surface;
        border-left: thick $success;
    }

    MessageBubble.system {
        color: $text-muted;
        text-style: italic;
    }

    MessageBubble.streaming {
        border-left: thick $warning;
    }
    """

    def __init__(self, content: str, role: str = "assistant", **kwargs):
        super().__init__(content, **kwargs)
        self.add_class(role)
        self._raw_content = content

    def append_text(self, text: str) -> None:
        """Append streaming text to this bubble and refresh the display."""
        self._raw_content += text
        self.update(self._raw_content)


class ChatPane(Static):
    """Chat interface with message history and input."""

    DEFAULT_CSS = """
    ChatPane {
        layout: vertical;
    }

    #message-list {
        height: 1fr;
        scrollbar-size: 1 1;
    }

    #chat-input {
        dock: bottom;
        margin: 0 1;
    }
    """

    def __init__(self, agent_runner=None, session=None, app_config=None, db=None, notifier=None, **kwargs):
        super().__init__(**kwargs)
        self._runner: InMemoryRunner | None = agent_runner
        self._session = session
        self._app_config = app_config
        self._db: DatabaseService | None = db
        self._notifier: WebhookDispatcher | None = notifier
        self._processing = False

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="message-list")
        yield Input(placeholder="Ask Squire something...", id="chat-input")

    def on_mount(self) -> None:
        self._add_message("Squire is ready. Ask me about your system.", "system")
        self.query_one("#chat-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text:
            return

        event.input.value = ""

        if self._processing:
            self._add_message("Still processing previous message...", "system")
            return

        self._add_message(user_text, "user")
        self._send_message(user_text)

    @work(thread=True)
    async def _send_message(self, user_text: str) -> None:
        """Send the user message to the ADK runner and stream the response."""
        self._processing = True
        try:
            if not self._runner or not self._session:
                self.app.call_from_thread(
                    self._add_message, "Agent not connected. Check your configuration.", "system"
                )
                return

            session_id = self._session.id

            # Persist user message
            await self._persist_message(session_id, "user", user_text)

            message = types.Content(parts=[types.Part(text=user_text)])
            response_parts = []
            streaming_bubble = None
            run_config = RunConfig(streaming_mode=StreamingMode.SSE)

            async for event in self._runner.run_async(
                user_id=self._app_config.user_id if self._app_config else "squire-user",
                session_id=session_id,
                new_message=message,
                run_config=run_config,
            ):
                if not event.content or not event.content.parts:
                    continue

                for part in event.content.parts:
                    # Log tool calls to activity log (not chat)
                    if part.function_call:
                        fc = part.function_call
                        args_str = ", ".join(f"{k}={v!r}" for k, v in (fc.args or {}).items())
                        call_text = f"Calling tool: {fc.name}({args_str})"
                        self.app.call_from_thread(self.app.add_log_entry, call_text, "tool-call")
                        # Log tool call event
                        await self._log_event(
                            session_id,
                            "tool_call",
                            f"Called {fc.name}",
                            tool_name=fc.name,
                            details=json.dumps(fc.args or {}),
                        )
                        # Reset streaming bubble — tool calls interrupt the response
                        streaming_bubble = None
                    # Log tool results to activity log (not chat)
                    elif part.function_response:
                        fr = part.function_response
                        preview = str(fr.response)[:200]
                        result_text = f"Tool result ({fr.name}): {preview}"
                        self.app.call_from_thread(self.app.add_log_entry, result_text, "tool-result")
                    # Stream partial text tokens into the live bubble
                    elif part.text and event.partial:
                        response_parts.append(part.text)
                        if streaming_bubble is None:
                            streaming_bubble = self.app.call_from_thread(
                                self._start_streaming_bubble, part.text
                            )
                        else:
                            self.app.call_from_thread(streaming_bubble.append_text, part.text)
                    # Final aggregated text (non-streaming fallback)
                    elif part.text and event.is_final_response() and streaming_bubble is None:
                        response_parts.append(part.text)

            # Finalize the streaming bubble or show the buffered response
            if streaming_bubble is not None:
                self.app.call_from_thread(self._finalize_streaming_bubble, streaming_bubble)
            elif response_parts:
                self.app.call_from_thread(self._add_message, "".join(response_parts), "assistant")
            else:
                self.app.call_from_thread(self._add_message, "No response from agent.", "system")

            response_text = "".join(response_parts)

            # Persist assistant response
            await self._persist_message(session_id, "assistant", response_text)

            # Update session last_active
            if self._db:
                await self._db.update_session_active(session_id)

        except Exception as e:
            error_text = f"Error: {e}"
            self.app.call_from_thread(self._add_message, error_text, "system")
            self.app.call_from_thread(self.app.add_log_entry, error_text, "error")
            await self._log_event(session_id, "error", str(e))
        finally:
            self._processing = False

    async def _persist_message(self, session_id: str, role: str, content: str) -> None:
        """Save a message to the database if available."""
        if self._db:
            try:
                await self._db.save_message(session_id=session_id, role=role, content=content)
            except Exception:
                pass  # Don't break chat if DB fails

    async def _log_event(
        self,
        session_id: str,
        category: str,
        summary: str,
        tool_name: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log an event to the database and dispatch webhook notifications."""
        if self._db:
            try:
                await self._db.log_event(
                    category=category,
                    summary=summary,
                    session_id=session_id,
                    tool_name=tool_name,
                    details=details,
                )
            except Exception:
                pass
        if self._notifier:
            try:
                await self._notifier.dispatch(
                    category=category,
                    summary=summary,
                    session_id=session_id,
                    tool_name=tool_name,
                    details=details,
                )
            except Exception:
                pass

    def _add_message(self, content: str, role: str) -> None:
        """Add a message bubble to the chat display."""
        prefix = {"user": "You", "assistant": "Squire", "system": ""}.get(role, "")
        display_text = f"[bold]{prefix}[/bold]: {content}" if prefix else content
        message_list = self.query_one("#message-list")
        message_list.mount(MessageBubble(display_text, role=role))
        message_list.scroll_end(animate=False)

    def _start_streaming_bubble(self, first_chunk: str) -> MessageBubble:
        """Mount a streaming assistant bubble and return it for incremental updates."""
        display_text = f"[bold]Squire[/bold]: {first_chunk}"
        bubble = MessageBubble(display_text, role="assistant")
        bubble.add_class("streaming")
        message_list = self.query_one("#message-list")
        message_list.mount(bubble)
        message_list.scroll_end(animate=False)
        return bubble

    def _finalize_streaming_bubble(self, bubble: MessageBubble) -> None:
        """Mark a streaming bubble as complete."""
        bubble.remove_class("streaming")
        self.query_one("#message-list").scroll_end(animate=False)

    def restore_messages(self, messages: list[dict]) -> None:
        """Replay prior messages into the chat display for a resumed session."""
        message_list = self.query_one("#message-list")
        message_list.remove_children()
        self._add_message("Session resumed.", "system")
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                self._add_message(content, role)

    def clear_messages(self) -> None:
        """Remove all messages from the chat display."""
        message_list = self.query_one("#message-list")
        message_list.remove_children()
        self._add_message("Chat cleared.", "system")
