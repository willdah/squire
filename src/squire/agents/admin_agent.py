"""Admin sub-agent — system administration and command execution.

Tools: systemctl, run_command
"""

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..config import AppConfig, LLMConfig
from ..instructions.admin_agent import build_instruction
from ..tools.groups import ADMIN_RISK_LEVELS, ADMIN_TOOLS
from ..types import RiskGateFactory

DESCRIPTION = (
    "System administration: managing systemd services and executing shell commands. "
    "Use for service management, ad-hoc commands, and host-level operations."
)


def create_admin_agent(
    llm_config: LLMConfig,
    app_config: AppConfig,
    risk_gate_factory: RiskGateFactory,
) -> Agent:
    """Create the Admin sub-agent."""
    model_kwargs = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    return Agent(
        name="Admin",
        description=DESCRIPTION,
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_instruction,
        tools=ADMIN_TOOLS,
        before_tool_callback=risk_gate_factory(ADMIN_RISK_LEVELS),
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )
