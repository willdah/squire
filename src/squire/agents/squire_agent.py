"""Root Squire agent — an ADK LlmAgent with system tools and risk gating."""

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..callbacks.risk_gate import risk_gate_callback
from ..config import AppConfig, LLMConfig
from ..instructions.squire_agent import build_instruction
from ..tools import ALL_TOOLS


def create_squire_agent(
    app_config: AppConfig | None = None,
    llm_config: LLMConfig | None = None,
) -> Agent:
    """Factory function that creates the root Squire agent.

    Args:
        app_config: Application configuration.
        llm_config: LLM provider configuration.

    Returns:
        A fully configured ADK Agent ready to run.
    """
    app_config = app_config or AppConfig()
    llm_config = llm_config or LLMConfig()

    model_kwargs = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    return Agent(
        name="Squire",
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_instruction,
        tools=ALL_TOOLS,
        before_tool_callback=risk_gate_callback,
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )
