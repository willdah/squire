"""Root Squire agent — single-agent or multi-agent with sub-agent routing."""

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..config import AppConfig, LLMConfig
from ..instructions.squire_agent import build_instruction
from ..tools import ALL_TOOLS
from ..types import BeforeToolCallback, RiskGateFactory, RiskGateFactoryBuilder


def create_squire_agent(
    app_config: AppConfig | None = None,
    llm_config: LLMConfig | None = None,
    before_tool_callback: BeforeToolCallback | None = None,
    risk_gate_factory: RiskGateFactory | None = None,
    risk_gate_factory_builder: RiskGateFactoryBuilder | None = None,
) -> Agent:
    """Factory function that creates the root Squire agent.

    Args:
        app_config: Application configuration.
        llm_config: LLM provider configuration.
        before_tool_callback: Risk gate callback for single-agent mode.
            Created by ``create_risk_gate()`` in ``callbacks.risk_gate``.
            Ignored when ``multi_agent=True``.
        risk_gate_factory: Factory that creates scoped before_tool_callbacks
            for sub-agents. Required when ``multi_agent=True``. Accepts
            a ``tool_risk_levels`` dict and returns a callback.
        risk_gate_factory_builder: Builder that returns a per-agent factory
            given the sub-agent name. When provided, overrides
            ``risk_gate_factory`` for multi-agent mode.

    Returns:
        A fully configured ADK Agent ready to run.
    """
    app_config = app_config or AppConfig()
    llm_config = llm_config or LLMConfig()

    model_kwargs = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    if app_config.multi_agent:
        return _create_multi_agent(app_config, llm_config, model_kwargs, risk_gate_factory, risk_gate_factory_builder)

    return Agent(
        name="Squire",
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_instruction,
        tools=ALL_TOOLS,
        before_tool_callback=before_tool_callback,
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )


def _create_multi_agent(
    app_config: AppConfig,
    llm_config: LLMConfig,
    model_kwargs: dict,
    risk_gate_factory: RiskGateFactory | None,
    risk_gate_factory_builder: RiskGateFactoryBuilder | None = None,
) -> Agent:
    """Create the multi-agent hierarchy with sub-agent routing."""
    from ..instructions.router_agent import build_instruction as build_router_instruction
    from .admin_agent import create_admin_agent
    from .container_agent import create_container_agent
    from .monitor_agent import create_monitor_agent
    from .notifier_agent import create_notifier_agent

    if risk_gate_factory is None and risk_gate_factory_builder is None:
        raise ValueError("risk_gate_factory or risk_gate_factory_builder is required when multi_agent=True")

    def _factory_for(agent_name: str) -> RiskGateFactory:
        if risk_gate_factory_builder is not None:
            return risk_gate_factory_builder(agent_name)
        return risk_gate_factory  # type: ignore[return-value]

    monitor = create_monitor_agent(llm_config, app_config, _factory_for("Monitor"))
    container = create_container_agent(llm_config, app_config, _factory_for("Container"))
    admin = create_admin_agent(llm_config, app_config, _factory_for("Admin"))
    notifier = create_notifier_agent(llm_config, app_config, _factory_for("Notifier"))

    return Agent(
        name="Squire",
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=build_router_instruction,
        tools=[],
        sub_agents=[monitor, container, admin, notifier],
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )
