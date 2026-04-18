"""Notifier sub-agent — ad-hoc notifications.

Tools: send_notification.
"""

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..config import AppConfig, LLMConfig
from ..instructions.notifier_agent import build_instruction
from ..tools.notifications import NOTIFIER_RISK_LEVELS, NOTIFIER_TOOLS
from ..types import RiskGateFactory

DESCRIPTION = (
    "Ad-hoc notifications: sending one-off messages to configured webhook "
    "endpoints. Alerting itself lives in external monitoring stacks."
)


def create_notifier_agent(
    llm_config: LLMConfig,
    app_config: AppConfig,
    risk_gate_factory: RiskGateFactory,
) -> Agent:
    """Create the Notifier sub-agent."""
    model_kwargs = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    return Agent(
        name="Notifier",
        description=DESCRIPTION,
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_instruction,
        tools=NOTIFIER_TOOLS,
        before_tool_callback=risk_gate_factory(NOTIFIER_RISK_LEVELS),
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )
