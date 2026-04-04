// TypeScript types matching the API schemas

export interface ContainerInfo {
  name: string;
  image: string;
  status: string;
  state: string;
  ports: string;
}

export interface HostSnapshot {
  hostname: string;
  os_info: string;
  cpu_percent: number;
  memory_total_mb: number;
  memory_used_mb: number;
  uptime: string;
  disk_usage_raw: string;
  containers: ContainerInfo[];
  error?: string | null;
}

export interface SystemStatusResponse {
  hosts: Record<string, HostSnapshot>;
}

export interface HostInfo {
  name: string;
  address: string;
  user: string;
  port: number;
  tags: string[];
  services: string[];
  snapshot: HostSnapshot | null;
  source: string;
  status: string;
}

export interface HostCreate {
  name: string;
  address: string;
  user: string;
  port: number;
  tags: string[];
  services: string[];
  service_root: string;
}

export interface HostEnrollmentResponse {
  name: string;
  status: string;
  public_key: string;
  message: string;
}

export interface HostVerifyResponse {
  name: string;
  reachable: boolean;
  message: string;
}

export interface SessionInfo {
  session_id: string;
  created_at: string;
  last_active: string;
  preview: string;
}

export interface MessageInfo {
  id?: number;
  session_id: string;
  timestamp: string;
  role: string;
  content?: string;
  tool_calls_json?: string;
  tool_call_id?: string;
}

export interface AlertRule {
  id?: number;
  name: string;
  condition: string;
  host: string;
  severity: string;
  cooldown_minutes: number;
  last_fired_at?: string | null;
  enabled: boolean;
  created_at?: string;
}

export interface Skill {
  name: string;
  description: string;
  host: string;
  trigger: string;
  enabled: boolean;
  instructions: string;
}

export interface EventInfo {
  id?: number;
  timestamp: string;
  session_id?: string;
  category: string;
  tool_name?: string;
  summary: string;
  details?: string;
}

export interface WatchStatus {
  status: string;
  started_at?: string | null;
  stopped_at?: string | null;
  cycle?: string | null;
  last_cycle_at?: string | null;
  interval_minutes?: string | null;
  risk_tolerance?: string | null;
  session_id?: string | null;
  last_response?: string | null;
  pid?: string | null;
}

// Watch event from watch_events table
export interface WatchEvent {
  id: number;
  cycle: number;
  type: string;
  content: string | null;
  created_at: string;
}

// Aggregated cycle summary
export interface WatchCycle {
  cycle: number;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  duration_seconds: number | null;
  tool_count: number;
  event_count: number;
}

// Watch config from API
export interface WatchConfigResponse {
  interval_minutes: number;
  cycle_timeout_seconds: number;
  checkin_prompt: string;
  notify_on_action: boolean;
  notify_on_blocked: boolean;
  cycles_per_session: number;
  risk_tolerance: number | null;
}

// Watch config update payload
export interface WatchConfigUpdate {
  interval_minutes?: number;
  risk_tolerance?: number;
  checkin_prompt?: string;
}

export interface ConfigResponse {
  app: Record<string, unknown>;
  llm: Record<string, unknown>;
  database: Record<string, unknown>;
  notifications: Record<string, unknown>;
  guardrails: Record<string, unknown>;
  watch: Record<string, unknown>;
  hosts: Record<string, unknown>[];
}

export interface ConfigSectionMeta {
  values: Record<string, unknown>;
  env_overrides: string[];
}

export interface ConfigDetailResponse {
  app: ConfigSectionMeta;
  llm: ConfigSectionMeta;
  database: ConfigSectionMeta;
  notifications: ConfigSectionMeta;
  guardrails: ConfigSectionMeta;
  watch: ConfigSectionMeta;
  hosts: Record<string, unknown>[];
  toml_path: string | null;
}

// WebSocket message types
export interface WsToken {
  type: "token";
  content: string;
}
export interface WsToolCall {
  type: "tool_call";
  name: string;
  args: Record<string, unknown>;
  request_id: string;
}
export interface WsToolResult {
  type: "tool_result";
  name: string;
  output: string;
  request_id: string;
}
export interface WsApprovalRequest {
  type: "approval_request";
  request_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  risk_level: number;
}
export interface WsMessageComplete {
  type: "message_complete";
  content: string;
  stopped?: boolean;
}
export interface WsError {
  type: "error";
  message: string;
}

export type WsServerMessage =
  | WsToken
  | WsToolCall
  | WsToolResult
  | WsApprovalRequest
  | WsMessageComplete
  | WsError;
