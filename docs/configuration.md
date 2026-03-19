# Configuration Reference

Squire is configured through a TOML file and environment variables.

## Precedence

Settings are resolved in order (highest priority first):

1. **Environment variables** (`SQUIRE_*`)
2. **TOML config file** -- first found from:
   - `./squire.toml` (project directory)
   - `~/.config/squire/squire.toml` (user config)
   - `/etc/squire/squire.toml` (system-wide)
3. **Built-in defaults**

To get started, copy the example config:

```bash
cp squire.example.toml squire.toml
```

---

## Top-Level Settings

These are set as top-level keys in `squire.toml` or via `SQUIRE_*` environment variables.

| Key | Default | Env Var | Description |
|---|---|---|---|
| `app_name` | `"Squire"` | `SQUIRE_APP_NAME` | Application name for the ADK runner |
| `user_id` | `"squire-user"` | `SQUIRE_USER_ID` | User ID for ADK session management |
| `house` | `""` | `SQUIRE_HOUSE` | Name of the house Squire serves (e.g., a family name or domain) |
| `squire_profile` | `""` | `SQUIRE_SQUIRE_PROFILE` | Personality profile: `rook`, `cedric`, or `wynn` |
| `squire_name` | `""` | `SQUIRE_SQUIRE_NAME` | Custom name (overrides the profile's bundled name) |
| `risk_tolerance` | `"cautious"` | `SQUIRE_RISK_TOLERANCE` | Global risk tolerance (see [Risk Tolerance](#risk-tolerance)) |
| `risk_strict` | `false` | `SQUIRE_RISK_STRICT` | When `true`, tools above tolerance are denied instead of prompting |
| `history_limit` | `50` | `SQUIRE_HISTORY_LIMIT` | Maximum messages in conversation context |
| `max_tool_rounds` | `10` | `SQUIRE_MAX_TOOL_ROUNDS` | Maximum tool-call rounds per user message |
| `multi_agent` | `false` | `SQUIRE_MULTI_AGENT` | Enable sub-agent decomposition (see [Multi-Agent Mode](#multi-agent-mode)) |

### Personality Profiles

| Profile | Name | Style |
|---|---|---|
| `rook` | Rook | Watchful and methodical. Concise, confirms before acting. |
| `cedric` | Cedric | Confident and proactive. Anticipates problems, takes initiative. |
| `wynn` | Wynn | Thoughtful and educational. Explains reasoning, teaches as it goes. |

Set a profile with `squire_profile` and optionally override the name with `squire_name`:

```toml
squire_profile = "cedric"
squire_name = "Gareth"       # uses Cedric's personality but a custom name
house = "Titancore"
```

---

## Risk Tolerance

Risk tolerance controls which tools Squire can use automatically, which require approval, and which are blocked.

Every tool has a built-in risk level (1--5). The tolerance setting determines the cutoff:

| Tolerance | Level | Auto-allows | Needs approval |
|---|---|---|---|
| `read-only` | 1 | System info, network info, container listing | Everything else |
| `cautious` | 2 | + log viewing, config reads | Compose, systemctl, commands |
| `standard` | 3 | + compose, systemctl | Arbitrary command execution |
| `full-trust` | 5 | Everything | Nothing |

```toml
risk_tolerance = "cautious"    # default
risk_strict = false            # false = prompt for approval; true = deny outright
```

You can also pass integer values (1--5) or set via env var:

```bash
export SQUIRE_RISK_TOLERANCE=standard
```

### Built-In Tool Risk Levels

| Tool | Risk Level | Description |
|---|---|---|
| `system_info` | 1 | CPU, memory, disk, uptime |
| `network_info` | 1 | Network interfaces, routes |
| `docker_ps` | 1 | List containers |
| `list_alert_rules` | 1 | List configured alert rules |
| `docker_logs` | 2 | View container logs |
| `read_config` | 2 | Read configuration files |
| `journalctl` | 2 | View system/service logs |
| `send_notification` | 2 | Send a notification |
| `create_alert_rule` | 2 | Create an alert rule |
| `docker_compose` | 3 | Manage compose stacks (start/stop/restart) |
| `systemctl` | 3 | Manage systemd services |
| `delete_alert_rule` | 3 | Delete an alert rule |
| `run_command` | 5 | Execute arbitrary shell commands |

---

## Guardrails -- `[guardrails]`

The `[guardrails]` section consolidates all safety policy in one place: tool-level overrides, per-agent tolerances, command/path guards, and watch-mode risk overrides.

Env vars use the `SQUIRE_GUARDRAILS_` prefix.

### Tool-Level Overrides

Override risk behavior for specific tools, regardless of the global tolerance:

```toml
[guardrails]
tools_allow = ["docker_logs"]            # bypass risk check, auto-run
tools_require_approval = ["docker_compose"]  # always prompt, even if tolerance allows
tools_deny = ["run_command"]             # hard block, never execute
```

| Key | Default | Env Var | Description |
|---|---|---|---|
| `tools_allow` | `[]` | `SQUIRE_GUARDRAILS_TOOLS_ALLOW` | Tool names that bypass risk check |
| `tools_require_approval` | `[]` | `SQUIRE_GUARDRAILS_TOOLS_REQUIRE_APPROVAL` | Tool names that always require approval |
| `tools_deny` | `[]` | `SQUIRE_GUARDRAILS_TOOLS_DENY` | Tool names that are hard-blocked |

### Command Guards

Controls which commands `run_command` can execute:

```toml
[guardrails]
commands_allow = ["ping", "traceroute", "df", "free", "uptime", "cat", "head", "tail"]
commands_block = ["rm", "mkfs", "dd", "shutdown", "reboot"]
```

| Key | Default | Env Var | Description |
|---|---|---|---|
| `commands_allow` | *(see below)* | `SQUIRE_GUARDRAILS_COMMANDS_ALLOW` | Commands that `run_command` can execute |
| `commands_block` | *(see below)* | `SQUIRE_GUARDRAILS_COMMANDS_BLOCK` | Commands that are always blocked (checked first) |

**Default command allowlist:** `ping`, `traceroute`, `dig`, `nslookup`, `df`, `free`, `uptime`, `ip`, `ss`, `cat`, `head`, `tail`

**Default command blocklist:** `rm`, `mkfs`, `dd`, `fdisk`, `parted`, `shutdown`, `reboot`, `init`, `bash`, `sh`, `zsh`, `fish`, `csh`, `tcsh`, `dash`, `python`, `python3`, `perl`, `ruby`, `node`, `lua`

The blocklist is checked first -- a command on both lists is blocked.

### Config Path Guards

Controls which directories `read_config` can access:

```toml
[guardrails]
config_paths = ["/etc/nginx/", "/opt/stacks/"]
```

| Key | Default | Env Var | Description |
|---|---|---|---|
| `config_paths` | `[]` | `SQUIRE_GUARDRAILS_CONFIG_PATHS` | Directories that `read_config` can access |

### Per-Agent Tolerance Overrides

Each sub-agent can have its own risk tolerance (only relevant when `multi_agent = true`), falling back to the global setting if unset:

```toml
risk_tolerance = "cautious"                # global default

[guardrails]
monitor_tolerance = "standard"            # auto-allow all monitor tools
container_tolerance = "cautious"          # prompt for compose mutations
admin_tolerance = "read-only"             # prompt for everything
notifier_tolerance = "cautious"           # prompt for delete_alert_rule
```

| Key | Env Var | Description |
|---|---|---|
| `monitor_tolerance` | `SQUIRE_GUARDRAILS_MONITOR_TOLERANCE` | Monitor sub-agent tolerance |
| `container_tolerance` | `SQUIRE_GUARDRAILS_CONTAINER_TOLERANCE` | Container sub-agent tolerance |
| `admin_tolerance` | `SQUIRE_GUARDRAILS_ADMIN_TOLERANCE` | Admin sub-agent tolerance |
| `notifier_tolerance` | `SQUIRE_GUARDRAILS_NOTIFIER_TOLERANCE` | Notifier sub-agent tolerance |

### Watch-Mode Risk Overrides -- `[guardrails.watch]`

Risk policy for watch mode lives in a sub-table under `[guardrails]`:

```toml
[guardrails.watch]
tolerance = "read-only"            # overrides global risk_tolerance for watch
tools_allow = []                   # additional tools to auto-allow in watch
tools_deny = []                    # additional tools to deny in watch
```

| Key | Env Var | Description |
|---|---|---|
| `tolerance` | `SQUIRE_GUARDRAILS_WATCH_TOLERANCE` | Risk tolerance for watch mode |
| `tools_allow` | `SQUIRE_GUARDRAILS_WATCH_TOOLS_ALLOW` | Additional tools to auto-allow in watch |
| `tools_deny` | `SQUIRE_GUARDRAILS_WATCH_TOOLS_DENY` | Additional tools to deny in watch |

Watch mode is always strict (deny, never prompt) since there's no interactive approval provider.

---

## Multi-Agent Mode

When `multi_agent = true`, Squire decomposes into specialized sub-agents. The LLM routes requests automatically while maintaining a single persona.

```toml
multi_agent = true
```

| Sub-Agent | Tools | Risk Range |
|---|---|---|
| **Monitor** | `system_info`, `network_info`, `docker_ps`, `journalctl`, `read_config` | 1--2 |
| **Container** | `docker_logs`, `docker_compose` | 2--3 |
| **Admin** | `systemctl`, `run_command` | 3--5 |
| **Notifier** | `send_notification`, `list_alert_rules`, `create_alert_rule`, `delete_alert_rule` | 1--3 |

---

## LLM Provider -- `[llm]`

Squire uses [LiteLLM](https://github.com/BerriAI/litellm), so any supported model works.

| Key | Default | Env Var | Description |
|---|---|---|---|
| `model` | `"ollama_chat/llama3.1:8b"` | `SQUIRE_LLM_MODEL` | LiteLLM model identifier |
| `api_base` | `null` | `SQUIRE_LLM_API_BASE` | API base URL (required for Ollama, optional for cloud providers) |
| `temperature` | `0.2` | `SQUIRE_LLM_TEMPERATURE` | Sampling temperature (0.0--2.0) |
| `max_tokens` | `4096` | `SQUIRE_LLM_MAX_TOKENS` | Maximum tokens in LLM response |

### Examples

**Ollama (local or remote):**
```toml
[llm]
model = "ollama_chat/qwen3.5:35b"
api_base = "http://localhost:11434"
```

**Anthropic:**
```toml
[llm]
model = "anthropic/claude-sonnet-4-20250514"
# Set ANTHROPIC_API_KEY env var
```

**OpenAI:**
```toml
[llm]
model = "gpt-4o"
# Set OPENAI_API_KEY env var
```

**Google Gemini:**
```toml
[llm]
model = "gemini/gemini-2.0-flash"
# Set GEMINI_API_KEY env var
```

---

## Database -- `[db]`

Squire persists chat history, system snapshots, events, and alert rules to SQLite.

| Key | Default | Env Var | Description |
|---|---|---|---|
| `path` | `~/.local/share/squire/squire.db` | `SQUIRE_DB_PATH` | Path to the SQLite database file |
| `snapshot_interval_minutes` | `15` | `SQUIRE_DB_SNAPSHOT_INTERVAL_MINUTES` | Minutes between automatic system snapshots |

```toml
[db]
path = "~/.local/share/squire/squire.db"
snapshot_interval_minutes = 15
```

---

## Remote Hosts -- `[[hosts]]`

Connect Squire to other machines via SSH. Each entry defines a remote host.

| Key | Default | Description |
|---|---|---|
| `name` | *(required)* | Unique alias for this host |
| `address` | *(required)* | Hostname or IP address |
| `user` | `"root"` | SSH username |
| `port` | `22` | SSH port |
| `key_file` | `null` | Path to SSH private key (uses ssh-agent if omitted) |
| `tags` | `[]` | Optional tags for grouping |
| `services` | `[]` | Docker Compose services on this host |
| `service_root` | `"/opt"` | Root directory for compose service directories |

```toml
[[hosts]]
name = "media-server"
address = "192.168.1.10"
user = "test_user"
services = ["plex", "sonarr", "radarr"]
service_root = "/opt/stacks"

[[hosts]]
name = "nas"
address = "192.168.1.20"
user = "test_user"
port = 2222
tags = ["storage"]
```

Squire connects lazily on first use. Remote tool calls receive a **+1 risk bump** (e.g., `docker_ps` becomes risk 2 on a remote host).

---

## Watch Mode -- `[watch]`

Operational configuration for autonomous watch mode (`squire watch`). See [CLI reference](cli.md) for full details.

Risk policy for watch mode is configured under `[guardrails.watch]`, not here.

| Key | Default | Env Var | Description |
|---|---|---|---|
| `interval_minutes` | `5` | `SQUIRE_WATCH_INTERVAL_MINUTES` | Minutes between watch cycles |
| `max_tool_calls_per_cycle` | `15` | `SQUIRE_WATCH_MAX_TOOL_CALLS_PER_CYCLE` | Tool call budget per cycle |
| `cycle_timeout_seconds` | `300` | `SQUIRE_WATCH_CYCLE_TIMEOUT_SECONDS` | Max wall-clock time per cycle |
| `cycles_per_session` | `50` | `SQUIRE_WATCH_CYCLES_PER_SESSION` | Rotate session after N cycles |
| `checkin_prompt` | *(built-in)* | `SQUIRE_WATCH_CHECKIN_PROMPT` | Prompt injected each cycle |
| `notify_on_action` | `true` | `SQUIRE_WATCH_NOTIFY_ON_ACTION` | Notify on corrective actions |
| `notify_on_blocked` | `true` | `SQUIRE_WATCH_NOTIFY_ON_BLOCKED` | Notify on blocked tool calls |

```toml
[watch]
interval_minutes = 5
max_tool_calls_per_cycle = 15
cycle_timeout_seconds = 300
cycles_per_session = 50
```

---

## Notifications -- `[notifications]`

Webhook-based notifications for events, watch mode alerts, and approval outcomes.

| Key | Default | Env Var | Description |
|---|---|---|---|
| `enabled` | `false` | `SQUIRE_NOTIFICATIONS_ENABLED` | Enable the notification system |
| `webhooks` | `[]` | | List of webhook endpoints (see below) |

Each webhook entry:

| Key | Default | Description |
|---|---|---|
| `name` | *(required)* | Human-readable name (e.g., `"discord"`, `"ntfy"`) |
| `url` | *(required)* | URL to POST event payloads to |
| `events` | `["*"]` | Event categories to subscribe to (`"*"` for all) |
| `headers` | `{}` | Optional HTTP headers (e.g., `Authorization`) |

```toml
[notifications]
enabled = true

[[notifications.webhooks]]
name = "discord"
url = "https://discord.com/api/webhooks/..."
events = ["watch.alert", "watch.action", "watch.blocked"]

[[notifications.webhooks]]
name = "ntfy"
url = "https://ntfy.sh/squire-alerts"
events = ["*"]
headers = { Authorization = "Bearer tk_..." }
```

### Event Categories

| Category | Source | Description |
|---|---|---|
| `tool_call` | Chat | A tool was called |
| `error` | Chat | An error occurred |
| `approval_denied` | Chat | User denied a tool approval |
| `watch.start` | Watch | Watch mode started |
| `watch.stop` | Watch | Watch mode stopped |
| `watch.action` | Watch | Agent took a corrective action |
| `watch.blocked` | Watch | Tool call denied by risk policy |
| `watch.alert` | Watch | Alert rule triggered |
| `watch.error` | Watch | Exception during a watch cycle |
| `user` | Agent | Ad-hoc notification sent by the agent |
