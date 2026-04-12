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
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface MessageInfo {
  id?: number;
  session_id: string;
  timestamp: string;
  role: string;
  content?: string;
  tool_calls_json?: string;
  tool_call_id?: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
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

export interface AlertRuleCreate {
  name: string;
  condition: string;
  host?: string;
  severity?: string;
  cooldown_minutes?: number;
}

export interface Skill {
  name: string;
  description: string;
  hosts: string[];
  trigger: string;
  enabled: boolean;
  incident_keys: string[];
  instructions: string;
}

export interface IncidentFamilyInfo {
  prefix: string;
  description: string;
}

export interface PlaybookDryRunIncident {
  key: string;
  severity: string;
  host: string;
  title: string;
  detail: string;
}

export interface PlaybookDryRunSelection {
  incident: PlaybookDryRunIncident;
  candidate_count: number;
  selected_playbook: string | null;
  path_taken: "deterministic_single" | "tie_break" | "semantic" | "generic";
  confidence: number;
  reasoning: string;
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
  watch_id?: string | null;
  watch_session_id?: string | null;
  cycle_id?: string | null;
  last_response?: string | null;
  pid?: string | null;
  total_actions?: string | null;
  total_blocked?: string | null;
  total_errors?: string | null;
  total_resolved?: string | null;
  total_escalated?: string | null;
  total_input_tokens?: string | null;
  total_output_tokens?: string | null;
  total_tokens?: string | null;
  last_outcome?: string | null;
}

// Watch event from watch_events table
export interface WatchEvent {
  id: number;
  cycle: number;
  cycle_id?: string | null;
  watch_id?: string | null;
  watch_session_id?: string | null;
  type: string;
  content: string | null;
  created_at: string;
}

// Aggregated cycle summary
export interface WatchCycle {
  cycle_id?: string | null;
  watch_id?: string | null;
  watch_session_id?: string | null;
  cycle: number;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  duration_seconds: number | null;
  tool_count: number;
  blocked_count?: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  incident_count?: number;
  resolved?: boolean;
  escalated?: boolean;
  incident_key?: string | null;
  event_count: number;
}

export interface WatchReportInfo {
  id?: number;
  report_id: string;
  watch_id: string;
  watch_session_id?: string | null;
  report_type: "session" | "watch" | string;
  status: string;
  title: string;
  digest: string;
  report_json: string;
  created_at: string;
}

export interface WatchTimelineItem {
  item_id: string;
  kind: "cycle" | "report" | string;
  watch_id?: string | null;
  watch_session_id?: string | null;
  cycle?: number | null;
  created_at: string;
  status?: string | null;
  incident_count?: number | null;
  tool_count?: number | null;
  blocked_count?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  payload_json?: string | null;
}

export interface WatchRunSummary {
  watch_id: string;
  started_at: string;
  stopped_at?: string | null;
  status: string;
  session_count: number;
  cycle_count: number;
  report_count: number;
  watch_report_id?: string | null;
}

export interface WatchSessionSummary {
  watch_session_id: string;
  watch_id: string;
  adk_session_id: string;
  started_at: string;
  stopped_at?: string | null;
  status: string;
  cycle_count: number;
  session_report_id?: string | null;
  session_report_status?: string | null;
  session_report_title?: string | null;
}

export interface WatchCycleSummary {
  cycle_id: string;
  watch_id: string;
  watch_session_id: string;
  cycle_number: number;
  started_at: string;
  ended_at?: string | null;
  status: string;
  duration_seconds?: number | null;
  tool_count: number;
  blocked_count: number;
  incident_count: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  incident_key?: string | null;
}

// Watch config from API
export interface WatchConfigResponse {
  interval_minutes: number;
  max_tool_calls_per_cycle: number;
  cycle_timeout_seconds: number;
  checkin_prompt: string;
  notify_on_action: boolean;
  notify_on_blocked: boolean;
  cycles_per_session: number;
  max_context_events: number;
  max_identical_actions_per_cycle: number;
  blocked_action_cooldown_cycles: number;
  max_remote_actions_per_cycle: number;
  risk_tolerance: number | null;
}

// Watch config update payload
export interface WatchConfigUpdate {
  interval_minutes?: number;
  max_tool_calls_per_cycle?: number;
  cycle_timeout_seconds?: number;
  checkin_prompt?: string;
  notify_on_action?: boolean;
  notify_on_blocked?: boolean;
  cycles_per_session?: number;
  max_context_events?: number;
  max_identical_actions_per_cycle?: number;
  blocked_action_cooldown_cycles?: number;
  max_remote_actions_per_cycle?: number;
  risk_tolerance?: number;
}

// --- Tools ---

export interface ToolParameter {
  name: string;
  type: string;
  required: boolean;
  default?: string | null;
}

export interface ToolAction {
  name: string;
  risk_level: number;
  risk_override: number | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  group: string;
  parameters: ToolParameter[];
  actions: ToolAction[] | null;
  risk_level: number | null;
  risk_override: number | null;
  status: "enabled" | "disabled";
  approval_policy: "always" | "never" | null;
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
  skills: ConfigSectionMeta;
  hosts: Record<string, unknown>[];
  toml_path: string | null;
}

export interface LLMModelsResponse {
  provider: string;
  current_model: string;
  models: string[];
  error?: string | null;
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
