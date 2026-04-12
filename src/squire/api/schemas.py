"""Pydantic response models for the Squire web API."""

from pydantic import BaseModel, Field

# --- System / Snapshots ---


class ContainerInfo(BaseModel):
    name: str = ""
    image: str = ""
    status: str = ""
    state: str = ""
    ports: str = ""


class HostSnapshot(BaseModel):
    hostname: str = "unknown"
    os_info: str = ""
    cpu_percent: float = 0
    memory_total_mb: float = 0
    memory_used_mb: float = 0
    uptime: str = ""
    disk_usage_raw: str = ""
    containers: list[ContainerInfo] = []
    error: str | None = None


class SystemStatusResponse(BaseModel):
    hosts: dict[str, HostSnapshot]


class SnapshotRecord(BaseModel):
    hostname: str = "unknown"
    cpu_percent: float = 0
    memory_used_mb: float = 0
    memory_total_mb: float = 0
    uptime: str = ""
    containers: list[ContainerInfo] = []


# --- Hosts ---


class HostInfo(BaseModel):
    name: str
    address: str = ""
    user: str = ""
    port: int = 22
    tags: list[str] = []
    services: list[str] = []
    snapshot: HostSnapshot | None = None
    source: str = "managed"
    status: str = "active"


class HostCreate(BaseModel):
    name: str
    address: str
    user: str = "root"
    port: int = 22
    tags: list[str] = []
    services: list[str] = []
    service_root: str = "/opt"


class HostEnrollmentResponse(BaseModel):
    name: str
    status: str
    public_key: str
    message: str


class HostVerifyResponse(BaseModel):
    name: str
    reachable: bool
    message: str


# --- Sessions ---


class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    last_active: str
    preview: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class MessageInfo(BaseModel):
    id: int | None = None
    session_id: str
    timestamp: str
    role: str
    content: str | None = None
    tool_calls_json: str | None = None
    tool_call_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


# --- Alerts ---


class AlertRule(BaseModel):
    id: int | None = None
    name: str
    condition: str
    host: str = "all"
    severity: str = "warning"
    cooldown_minutes: int = 30
    last_fired_at: str | None = None
    enabled: bool = True
    created_at: str | None = None


class AlertRuleCreate(BaseModel):
    name: str
    condition: str
    host: str = "all"
    severity: str = "warning"
    cooldown_minutes: int = 30


class AlertRuleUpdate(BaseModel):
    condition: str | None = None
    host: str | None = None
    severity: str | None = None
    cooldown_minutes: int | None = None


# --- Skills ---


class Skill(BaseModel):
    name: str
    description: str = ""
    hosts: list[str] = ["all"]
    trigger: str = "manual"
    enabled: bool = True
    incident_keys: list[str] = []
    instructions: str = ""


class SkillCreate(BaseModel):
    name: str
    description: str
    hosts: list[str] = ["all"]
    trigger: str = "manual"
    incident_keys: list[str] = []
    allow_custom_incident_prefixes: bool = False
    instructions: str


class SkillUpdate(BaseModel):
    description: str | None = None
    hosts: list[str] | None = None
    trigger: str | None = None
    enabled: bool | None = None
    incident_keys: list[str] | None = None
    allow_custom_incident_prefixes: bool | None = None
    instructions: str | None = None


class IncidentFamilyInfo(BaseModel):
    prefix: str
    description: str


class PlaybookDryRunIncident(BaseModel):
    key: str
    severity: str = "high"
    host: str = "local"
    title: str = ""
    detail: str = ""


class PlaybookDryRunRequest(BaseModel):
    incidents: list[PlaybookDryRunIncident] = Field(min_length=1, max_length=25)
    use_llm: bool = False


class PlaybookDryRunSelection(BaseModel):
    incident: PlaybookDryRunIncident
    candidate_count: int
    selected_playbook: str | None = None
    path_taken: str
    confidence: float
    reasoning: str


class PlaybookDryRunResponse(BaseModel):
    selections: list[PlaybookDryRunSelection]


class BootstrapPlaybooksResponse(BaseModel):
    created: list[str]
    skipped: list[str]


# --- Events ---


class EventInfo(BaseModel):
    id: int | None = None
    timestamp: str
    session_id: str | None = None
    category: str
    tool_name: str | None = None
    summary: str
    details: str | None = None


# --- Tools ---


class ToolParameter(BaseModel):
    name: str
    type: str
    required: bool = True
    default: str | None = None


class ToolAction(BaseModel):
    name: str
    risk_level: int
    risk_override: int | None = None


class ToolInfo(BaseModel):
    name: str
    description: str
    group: str
    parameters: list[ToolParameter]
    actions: list[ToolAction] | None = None
    risk_level: int | None = None  # single-action tools only
    risk_override: int | None = None  # single-action tools only
    status: str  # "enabled" | "disabled"
    approval_policy: str | None = None  # "always" | "never" | null


# --- Config ---


class ConfigResponse(BaseModel):
    app: dict
    llm: dict
    database: dict
    notifications: dict
    guardrails: dict
    watch: dict
    hosts: list[dict]


class ConfigSectionMeta(BaseModel):
    values: dict
    env_overrides: list[str] = []


class ConfigDetailResponse(BaseModel):
    app: ConfigSectionMeta
    llm: ConfigSectionMeta
    database: ConfigSectionMeta
    notifications: ConfigSectionMeta
    guardrails: ConfigSectionMeta
    watch: ConfigSectionMeta
    skills: ConfigSectionMeta
    hosts: list[dict]
    toml_path: str | None = None


class AppConfigUpdate(BaseModel):
    app_name: str | None = None
    user_id: str | None = None
    history_limit: int | None = None
    max_tool_rounds: int | None = None
    multi_agent: bool | None = None


class LLMConfigUpdate(BaseModel):
    model: str | None = None
    api_base: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class LLMModelsResponse(BaseModel):
    provider: str
    current_model: str
    models: list[str]
    error: str | None = None


class WatchConfigPatch(BaseModel):
    interval_minutes: int | None = Field(default=None, ge=1)
    max_tool_calls_per_cycle: int | None = Field(default=None, ge=1)
    cycle_timeout_seconds: int | None = Field(default=None, ge=30)
    checkin_prompt: str | None = None
    notify_on_action: bool | None = None
    notify_on_blocked: bool | None = None
    cycles_per_session: int | None = Field(default=None, ge=1)
    max_context_events: int | None = Field(default=None, ge=10)
    max_identical_actions_per_cycle: int | None = Field(default=None, ge=1)
    blocked_action_cooldown_cycles: int | None = Field(default=None, ge=1)
    max_remote_actions_per_cycle: int | None = Field(default=None, ge=1)


class GuardrailsConfigUpdate(BaseModel):
    risk_tolerance: str | None = None
    risk_strict: bool | None = None
    tools_allow: list[str] | None = None
    tools_require_approval: list[str] | None = None
    tools_deny: list[str] | None = None
    tools_risk_overrides: dict[str, int] | None = None
    monitor_tolerance: str | None = None
    container_tolerance: str | None = None
    admin_tolerance: str | None = None
    notifier_tolerance: str | None = None
    watch_tolerance: str | None = None
    watch_tools_allow: list[str] | None = None
    watch_tools_deny: list[str] | None = None
    commands_allow: list[str] | None = None
    commands_block: list[str] | None = None
    config_paths: list[str] | None = None


class NotificationsConfigUpdate(BaseModel):
    enabled: bool | None = None
    webhooks: list[dict] | None = None
    email: dict | None = None


class SkillsConfigUpdate(BaseModel):
    path: str | None = None


# --- Watch ---


class WatchStatusResponse(BaseModel):
    status: str = "unknown"
    started_at: str | None = None
    stopped_at: str | None = None
    cycle: str | None = None
    last_cycle_at: str | None = None
    interval_minutes: str | None = None
    risk_tolerance: str | None = None
    session_id: str | None = None
    watch_id: str | None = None
    watch_session_id: str | None = None
    cycle_id: str | None = None
    last_response: str | None = None
    pid: str | None = None
    total_actions: str | None = None
    total_blocked: str | None = None
    total_errors: str | None = None
    total_resolved: str | None = None
    total_escalated: str | None = None
    total_input_tokens: str | None = None
    total_output_tokens: str | None = None
    total_tokens: str | None = None
    last_outcome: str | None = None


class WatchConfigUpdate(BaseModel):
    interval_minutes: int | None = Field(default=None, ge=1)
    max_tool_calls_per_cycle: int | None = Field(default=None, ge=1)
    cycle_timeout_seconds: int | None = Field(default=None, ge=30)
    checkin_prompt: str | None = None
    notify_on_action: bool | None = None
    notify_on_blocked: bool | None = None
    cycles_per_session: int | None = Field(default=None, ge=1)
    max_context_events: int | None = Field(default=None, ge=10)
    max_identical_actions_per_cycle: int | None = Field(default=None, ge=1)
    blocked_action_cooldown_cycles: int | None = Field(default=None, ge=1)
    max_remote_actions_per_cycle: int | None = Field(default=None, ge=1)
    risk_tolerance: int | None = Field(default=None, ge=1, le=5)


class WatchConfigResponse(BaseModel):
    interval_minutes: int
    max_tool_calls_per_cycle: int
    cycle_timeout_seconds: int
    checkin_prompt: str
    notify_on_action: bool
    notify_on_blocked: bool
    cycles_per_session: int
    max_context_events: int
    max_identical_actions_per_cycle: int
    blocked_action_cooldown_cycles: int
    max_remote_actions_per_cycle: int
    risk_tolerance: int | None


class WatchApprovalAction(BaseModel):
    approved: bool


class WatchCommandResponse(BaseModel):
    status: str
    message: str = ""


class WatchReportInfo(BaseModel):
    id: int | None = None
    report_id: str
    watch_id: str
    watch_session_id: str | None = None
    report_type: str
    status: str
    title: str
    digest: str
    report_json: str
    created_at: str


class WatchTimelineItem(BaseModel):
    item_id: str
    kind: str
    watch_id: str | None = None
    watch_session_id: str | None = None
    cycle: int | None = None
    created_at: str
    status: str | None = None
    incident_count: int | None = None
    tool_count: int | None = None
    blocked_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    payload_json: str | None = None


class WatchRunSummary(BaseModel):
    watch_id: str
    started_at: str
    stopped_at: str | None = None
    status: str
    session_count: int = 0
    cycle_count: int = 0
    report_count: int = 0
    watch_report_id: str | None = None


class WatchSessionSummary(BaseModel):
    watch_session_id: str
    watch_id: str
    adk_session_id: str
    started_at: str
    stopped_at: str | None = None
    status: str
    cycle_count: int = 0
    session_report_id: str | None = None
    session_report_status: str | None = None
    session_report_title: str | None = None


class WatchCycleSummary(BaseModel):
    cycle_id: str
    watch_id: str
    watch_session_id: str
    cycle_number: int
    started_at: str
    ended_at: str | None = None
    status: str
    duration_seconds: float | None = None
    tool_count: int = 0
    blocked_count: int = 0
    incident_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    incident_key: str | None = None


# --- Chat ---


class ChatSessionCreate(BaseModel):
    host_context: list[str] | None = None


class ChatSessionResponse(BaseModel):
    session_id: str
