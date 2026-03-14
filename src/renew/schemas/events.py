from datetime import datetime

from pydantic import BaseModel, Field


class Event(BaseModel):
    """A discrete event worth logging."""

    timestamp: datetime = Field(default_factory=datetime.now)
    category: str  # "tool_call", "error", "approval_denied", "notification"
    summary: str
    details: str | None = None
    session_id: str | None = None


class ToolCallEvent(Event):
    """Event recording a tool invocation."""

    category: str = "tool_call"
    tool_name: str = ""
    tool_args: dict = Field(default_factory=dict)
    success: bool = True
    output_preview: str = ""


class ApprovalEvent(Event):
    """Event recording a risk approval decision."""

    category: str = "approval"
    tool_name: str = ""
    tool_args: dict = Field(default_factory=dict)
    approved: bool = False
