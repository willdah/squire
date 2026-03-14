"""Chat pane — message list and input widget for the Renew TUI."""

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from google.adk.runners import InMemoryRunner
from google.genai import types


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
    """

    def __init__(self, content: str, role: str = "assistant", **kwargs):
        super().__init__(content, **kwargs)
        self.add_class(role)


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

    def __init__(self, agent_runner=None, session=None, app_config=None, **kwargs):
        super().__init__(**kwargs)
        self._runner: InMemoryRunner | None = agent_runner
        self._session = session
        self._app_config = app_config
        self._processing = False

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="message-list")
        yield Input(placeholder="Ask Renew something...", id="chat-input")

    def on_mount(self) -> None:
        self._add_message("Renew is ready. Ask me about your system.", "system")

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

            message = types.Content(parts=[types.Part(text=user_text)])
            response_parts = []

            async for event in self._runner.run_async(
                user_id=self._app_config.user_id if self._app_config else "renew-user",
                session_id=self._session.id,
                new_message=message,
            ):
                if not event.content or not event.content.parts:
                    continue

                for part in event.content.parts:
                    # Show tool calls as system messages
                    if part.function_call:
                        fc = part.function_call
                        args_str = ", ".join(f"{k}={v!r}" for k, v in (fc.args or {}).items())
                        self.app.call_from_thread(
                            self._add_message,
                            f"Calling tool: {fc.name}({args_str})",
                            "system",
                        )
                    # Show tool results as system messages
                    elif part.function_response:
                        fr = part.function_response
                        preview = str(fr.response)[:200]
                        self.app.call_from_thread(
                            self._add_message,
                            f"Tool result ({fr.name}): {preview}",
                            "system",
                        )
                    # Collect final text response
                    elif part.text and event.is_final_response():
                        response_parts.append(part.text)

            response_text = "\n".join(response_parts) if response_parts else "No response from agent."
            self.app.call_from_thread(self._add_message, response_text, "assistant")
        except Exception as e:
            self.app.call_from_thread(self._add_message, f"Error: {e}", "system")
        finally:
            self._processing = False

    def _add_message(self, content: str, role: str) -> None:
        """Add a message bubble to the chat display."""
        prefix = {"user": "You", "assistant": "Renew", "system": ""}.get(role, "")
        display_text = f"[bold]{prefix}[/bold]: {content}" if prefix else content
        message_list = self.query_one("#message-list")
        message_list.mount(MessageBubble(display_text, role=role))
        message_list.scroll_end(animate=False)

    def clear_messages(self) -> None:
        """Remove all messages from the chat display."""
        message_list = self.query_one("#message-list")
        message_list.remove_children()
        self._add_message("Chat cleared.", "system")
