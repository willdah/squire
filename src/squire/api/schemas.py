"""Pydantic response models for the Squire web API."""

from pydantic import BaseModel

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


class MessageInfo(BaseModel):
    id: int | None = None
    session_id: str
    timestamp: str
    role: str
    content: str | None = None
    tool_calls_json: str | None = None
    tool_call_id: str | None = None


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
    host: str = "all"
    trigger: str = "manual"
    enabled: bool = True
    instructions: str = ""


class SkillCreate(BaseModel):
    name: str
    description: str
    host: str = "all"
    trigger: str = "manual"
    instructions: str


class SkillUpdate(BaseModel):
    description: str | None = None
    host: str | None = None
    trigger: str | None = None
    enabled: bool | None = None
    instructions: str | None = None


# --- Events ---


class EventInfo(BaseModel):
    id: int | None = None
    timestamp: str
    session_id: str | None = None
    category: str
    tool_name: str | None = None
    summary: str
    details: str | None = None


# --- Config ---


class ConfigResponse(BaseModel):
    app: dict
    llm: dict
    database: dict
    notifications: dict
    guardrails: dict
    watch: dict
    hosts: list[dict]


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
    last_response: str | None = None
    pid: str | None = None


class WatchConfigUpdate(BaseModel):
    interval_minutes: int | None = None
    risk_tolerance: int | None = None
    checkin_prompt: str | None = None


class WatchConfigResponse(BaseModel):
    interval_minutes: int
    cycle_timeout_seconds: int
    checkin_prompt: str
    notify_on_action: bool
    notify_on_blocked: bool
    cycles_per_session: int
    risk_tolerance: int | None


class WatchApprovalAction(BaseModel):
    approved: bool


class WatchCommandResponse(BaseModel):
    status: str
    message: str = ""


# --- Chat ---


class ChatSessionCreate(BaseModel):
    host_context: list[str] | None = None


class ChatSessionResponse(BaseModel):
    session_id: str
