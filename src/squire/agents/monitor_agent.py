"""Monitor sub-agent — read-only system observation.

Tools: system_info, network_info, docker_ps, journalctl, read_config
"""

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..config import AppConfig, LLMConfig
from ..instructions.monitor_agent import build_instruction
from ..tools.groups import MONITOR_RISK_LEVELS, MONITOR_TOOLS
from ..types import RiskGateFactory

DESCRIPTION = (
    "Read-only system observation: health checks, resource usage, container listing, "
    "log viewing, and config reading. Use for questions about system status, metrics, "
    "and diagnostics."
)


def create_monitor_agent(
    llm_config: LLMConfig,
    app_config: AppConfig,
    risk_gate_factory: RiskGateFactory,
) -> Agent:
    """Create the Monitor sub-agent."""
    model_kwargs = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    return Agent(
        name="Monitor",
        description=DESCRIPTION,
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_instruction,
        tools=MONITOR_TOOLS,
        before_tool_callback=risk_gate_factory(MONITOR_RISK_LEVELS),
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )
