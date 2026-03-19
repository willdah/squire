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

export interface ConfigResponse {
  app: Record<string, unknown>;
  llm: Record<string, unknown>;
  database: Record<string, unknown>;
  notifications: Record<string, unknown>;
  security: Record<string, unknown>;
  watch: Record<string, unknown>;
  risk: Record<string, unknown>;
  hosts: Record<string, unknown>[];
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
