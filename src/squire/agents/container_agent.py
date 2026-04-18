"""Container sub-agent — container lifecycle management.

Tools: docker_ps, docker_logs, docker_compose, docker_container, docker_image, docker_cleanup,
docker_volume, docker_network
"""

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..config import AppConfig, LLMConfig
from ..instructions.container_agent import build_instruction
from ..tools.groups import CONTAINER_RISK_LEVELS, CONTAINER_TOOLS
from ..types import RiskGateFactory

DESCRIPTION = (
    "Container lifecycle management: viewing container logs, restarting services, "
    "and managing Docker Compose stacks. Use for container operations and troubleshooting."
)


def create_container_agent(
    llm_config: LLMConfig,
    app_config: AppConfig,
    risk_gate_factory: RiskGateFactory,
) -> Agent:
    """Create the Container sub-agent."""
    model_kwargs = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    return Agent(
        name="Container",
        description=DESCRIPTION,
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_instruction,
        tools=CONTAINER_TOOLS,
        before_tool_callback=risk_gate_factory(CONTAINER_RISK_LEVELS),
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )
