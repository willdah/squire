# Configuration Reference

Squire is configured through a TOML file and environment variables.

## Precedence

Settings are resolved in order (highest priority first):

1. **Environment variables** (`SQUIRE_`*)
2. **TOML config file** -- first found from:
  - `./squire.toml` (project directory)
  - `~/.config/squire/squire.toml` (user config)
  - `/etc/squire/squire.toml` (system-wide)
3. **Built-in defaults**

To get started, copy the example config:

```bash
cp squire.example.toml squire.toml
```

> **Looking for model recommendations?** See [Tested Models](#tested-models) for what's been validated.

---

## Top-Level Settings

These are set as top-level keys in `squire.toml` or via `SQUIRE_`* environment variables.


| Key               | Default         | Env Var                  | Description                                                                |
| ----------------- | --------------- | ------------------------ | -------------------------------------------------------------------------- |
| `app_name`        | `"Squire"`      | `SQUIRE_APP_NAME`        | Application name for the ADK runner                                        |
| `user_id`         | `"squire-user"` | `SQUIRE_USER_ID`         | User ID for ADK session management                                         |
| `history_limit`   | `50`            | `SQUIRE_HISTORY_LIMIT`   | Maximum messages in conversation context                                   |
| `max_tool_rounds` | `10`            | `SQUIRE_MAX_TOOL_ROUNDS` | Maximum tool-call rounds per user message                                  |
| `multi_agent`     | `false`         | `SQUIRE_MULTI_AGENT`     | Enable sub-agent decomposition (see [Multi-Agent Mode](#multi-agent-mode)) |


> **Note:** `risk_tolerance` and `risk_strict` have moved to `[guardrails]`. See [Guardrails](#guardrails----guardrails).

---

## Risk Tolerance

Risk tolerance controls which tools Squire can use automatically, which require approval, and which are blocked.

Every tool has a built-in risk level (1--5). The tolerance setting determines the cutoff:


| Tolerance    | Level | Auto-allows                                  | Needs approval               |
| ------------ | ----- | -------------------------------------------- | ---------------------------- |
| `read-only`  | 1     | System info, network info, container listing | Everything else              |
| `cautious`   | 2     | + log viewing, config reads                  | Compose, systemctl, commands |
| `standard`   | 3     | + compose, systemctl                         | Arbitrary command execution  |
| `full-trust` | 5     | Everything                                   | Nothing                      |


```toml
[guardrails]
risk_tolerance = "cautious"    # default
risk_strict = false            # false = prompt for approval; true = deny outright
```

You can also pass integer values (1--5) or set via env var:

```bash
export SQUIRE_GUARDRAILS_RISK_TOLERANCE=standard
```

### Built-In Tool Risk Levels


| Tool                | Risk Level | Description                                |
| ------------------- | ---------- | ------------------------------------------ |
| `system_info`       | 1          | CPU, memory, disk, uptime                  |
| `network_info`      | 1          | Network interfaces, routes                 |
| `docker_ps`         | 1          | List containers                            |
| `list_alert_rules`  | 1          | List configured alert rules                |
| `docker_logs`       | 2          | View container logs                        |
| `read_config`       | 2          | Read configuration files                   |
| `journalctl`        | 2          | View system/service logs                   |
| `send_notification` | 2          | Send a notification                        |
| `create_alert_rule` | 2          | Create an alert rule                       |
| `docker_compose`    | 3          | Manage compose stacks (start/stop/restart) |
| `systemctl`         | 3          | Manage systemd services                    |
| `delete_alert_rule` | 3          | Delete an alert rule                       |
| `run_command`       | 5          | Execute arbitrary shell commands           |


---

## Guardrails -- `[guardrails]`

The `[guardrails]` section consolidates all safety policy in one place: tool-level overrides, per-agent tolerances, command/path guards, and watch-mode risk overrides.

Env vars use the `SQUIRE_GUARDRAILS_` prefix.

### Global Risk Policy

The global risk tolerance and strict mode live here:

```toml
[guardrails]
risk_tolerance = "cautious"              # read-only, cautious, standard, full-trust
risk_strict = false                      # true = deny above threshold; false = prompt
```


| Key              | Default      | Env Var                            | Description                                                        |
| ---------------- | ------------ | ---------------------------------- | ------------------------------------------------------------------ |
| `risk_tolerance` | `"cautious"` | `SQUIRE_GUARDRAILS_RISK_TOLERANCE` | Global risk tolerance (see [Risk Tolerance](#risk-tolerance))      |
| `risk_strict`    | `false`      | `SQUIRE_GUARDRAILS_RISK_STRICT`    | When `true`, tools above tolerance are denied instead of prompting |


### Tool-Level Overrides

Override risk behavior for specific tools, regardless of the global tolerance:

```toml
[guardrails]
tools_allow = ["docker_logs"]            # bypass risk check, auto-run
tools_require_approval = ["docker_compose"]  # always prompt, even if tolerance allows
tools_deny = ["run_command"]             # hard block, never execute
```


| Key                      | Default | Env Var                                    | Description                               |
| ------------------------ | ------- | ------------------------------------------ | ----------------------------------------- |
| `tools_allow`            | `[]`    | `SQUIRE_GUARDRAILS_TOOLS_ALLOW`            | Tool names that bypass risk check         |
| `tools_require_approval` | `[]`    | `SQUIRE_GUARDRAILS_TOOLS_REQUIRE_APPROVAL` | Tool names that always require approval   |
| `tools_deny`             | `[]`    | `SQUIRE_GUARDRAILS_TOOLS_DENY`             | Tool names that are hard-blocked          |
| `tools_risk_overrides`   | `{}`    | `SQUIRE_GUARDRAILS_TOOLS_RISK_OVERRIDES`   | Per-tool risk level overrides (see below) |


### Per-Tool Risk Level Overrides

Override the built-in risk level for specific tools or tool actions. Values are integers 1--5. Keys can be a tool name (applies to all actions) or `tool:action` for granular control:

```toml
[guardrails]
tools_risk_overrides = { "docker_compose:restart" = 4, "run_command" = 3 }
```

### Command Guards

Controls which commands `run_command` can execute:

```toml
[guardrails]
commands_allow = ["ping", "nc", "dig", "ip", "df", "cat", "docker"]
commands_block = ["rm", "mkfs", "dd", "shutdown", "reboot"]
```


| Key              | Default       | Env Var                            | Description                                      |
| ---------------- | ------------- | ---------------------------------- | ------------------------------------------------ |
| `commands_allow` | *(see below)* | `SQUIRE_GUARDRAILS_COMMANDS_ALLOW` | Commands that `run_command` can execute          |
| `commands_block` | *(see below)* | `SQUIRE_GUARDRAILS_COMMANDS_BLOCK` | Commands that are always blocked (checked first) |


**Default command allowlist:** `ls`, `stat`, `file`, `du`, `find`, `wc`, `cat`, `head`, `tail`, `grep`, `hostname`, `date`, `whoami`, `id`, `uname`, `uptime`, `df`, `free`, `mount`, `lsblk`, `top`, `ps`, `which`, `ping`, `traceroute`, `dig`, `nslookup`, `ip`, `ss`, `netstat`, `nc`, `docker`, `systemctl`, `journalctl`, `lsof`

`nc` is allowed for common homelab port checks (for example `nc -zv host 22`). It can also listen or relay traffic; remove it from `commands_allow` if you want a stricter policy.

**Default command blocklist:** `rm`, `mkfs`, `dd`, `fdisk`, `parted`, `shutdown`, `reboot`, `init`, `bash`, `sh`, `zsh`, `fish`, `csh`, `tcsh`, `dash`, `python`, `python3`, `perl`, `ruby`, `node`, `lua`

The blocklist is checked first -- a command on both lists is blocked.

**Host / container PATH:** `run_command` runs binaries from the process environment. Minimal images (for example `python:*-slim`) may omit `ping`, `dig`, `nc`, and similar tools even when they are allowlisted. The published Squire Docker image installs packages for the default allowlist; on bare metal or custom images, install the equivalent OS packages or adjust `commands_allow` to match what is installed.

### Config Path Guards

Controls which directories `read_config` can access:

```toml
[guardrails]
config_paths = ["/etc/nginx/", "/opt/stacks/"]
```


| Key            | Default | Env Var                          | Description                               |
| -------------- | ------- | -------------------------------- | ----------------------------------------- |
| `config_paths` | `[]`    | `SQUIRE_GUARDRAILS_CONFIG_PATHS` | Directories that `read_config` can access |


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


| Key                   | Env Var                                 | Description                   |
| --------------------- | --------------------------------------- | ----------------------------- |
| `monitor_tolerance`   | `SQUIRE_GUARDRAILS_MONITOR_TOLERANCE`   | Monitor sub-agent tolerance   |
| `container_tolerance` | `SQUIRE_GUARDRAILS_CONTAINER_TOLERANCE` | Container sub-agent tolerance |
| `admin_tolerance`     | `SQUIRE_GUARDRAILS_ADMIN_TOLERANCE`     | Admin sub-agent tolerance     |
| `notifier_tolerance`  | `SQUIRE_GUARDRAILS_NOTIFIER_TOLERANCE`  | Notifier sub-agent tolerance  |


### Watch-Mode Risk Overrides -- `[guardrails.watch]`

Risk policy for watch mode lives in a sub-table under `[guardrails]`:

```toml
[guardrails.watch]
tolerance = "read-only"            # overrides global risk_tolerance for watch
tools_allow = []                   # additional tools to auto-allow in watch
tools_deny = []                    # additional tools to deny in watch
```


| Key           | Env Var                               | Description                             |
| ------------- | ------------------------------------- | --------------------------------------- |
| `tolerance`   | `SQUIRE_GUARDRAILS_WATCH_TOLERANCE`   | Risk tolerance for watch mode           |
| `tools_allow` | `SQUIRE_GUARDRAILS_WATCH_TOOLS_ALLOW` | Additional tools to auto-allow in watch |
| `tools_deny`  | `SQUIRE_GUARDRAILS_WATCH_TOOLS_DENY`  | Additional tools to deny in watch       |


Watch mode is always strict (deny, never prompt) since there's no interactive approval provider.

---

## Multi-Agent Mode

When `multi_agent = true`, Squire decomposes into specialized sub-agents. The LLM routes requests automatically while maintaining a single persona.

```toml
multi_agent = true
```


| Sub-Agent     | Tools                                                                             | Risk Range |
| ------------- | --------------------------------------------------------------------------------- | ---------- |
| **Monitor**   | `system_info`, `network_info`, `docker_ps`, `journalctl`, `read_config`           | 1--2       |
| **Container** | `docker_logs`, `docker_compose`                                                   | 2--3       |
| **Admin**     | `systemctl`, `run_command`                                                        | 3--5       |
| **Notifier**  | `send_notification`, `list_alert_rules`, `create_alert_rule`, `delete_alert_rule` | 1--3       |


---

## LLM Provider -- `[llm]`

Squire uses [LiteLLM](https://github.com/BerriAI/litellm), so any supported model works.


| Key           | Default                     | Env Var                  | Description                                                      |
| ------------- | --------------------------- | ------------------------ | ---------------------------------------------------------------- |
| `model`       | `"ollama_chat/llama3.1:8b"` | `SQUIRE_LLM_MODEL`       | LiteLLM model identifier                                         |
| `api_base`    | `null`                      | `SQUIRE_LLM_API_BASE`    | API base URL (required for Ollama, optional for cloud providers) |
| `temperature` | `0.2`                       | `SQUIRE_LLM_TEMPERATURE` | Sampling temperature (0.0--2.0)                                  |
| `max_tokens`  | `4096`                      | `SQUIRE_LLM_MAX_TOKENS`  | Maximum tokens in LLM response                                   |


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

### Tested Models

Squire relies heavily on tool/function calling. Models with strong tool-calling support produce the best results, especially for multi-step orchestration in watch mode.


| Model                              | Provider | Status          | Notes                                                                             |
| ---------------------------------- | -------- | --------------- | --------------------------------------------------------------------------------- |
| `ollama_chat/mistral-small3.2:24b` | Ollama   | **Recommended** | Current development model (v0.5.0+). Reliable tool-calling accuracy.              |
| `ollama_chat/llama3.1:8b`          | Ollama   | Not recommended | Used pre-v0.4.0. Tool-call accuracy was limited; suitable for basic queries only. |


**Cloud providers (Anthropic, OpenAI, Gemini):** These are supported via LiteLLM and expected to perform well -- particularly larger models with strong tool-calling capabilities -- but have not been validated with Squire yet. If you try a cloud model, feedback is welcome via [GitHub issues](https://github.com/willdahern/squire/issues).

**General guidance:** Larger parameter counts and models specifically fine-tuned for function calling tend to produce better results with Squire. If a model struggles with tool calls (wrong arguments, skipped calls, hallucinated tool names), try a larger variant or a different model family.

---

## Skills -- `[skills]`

Skills are file-based instruction sets aligned with the [Open Agent Skills spec](https://agentskills.io/specification). Each skill lives in a `NAME/SKILL.md` subdirectory under the configured skills path.


| Key    | Default                        | Env Var              | Description                            |
| ------ | ------------------------------ | -------------------- | -------------------------------------- |
| `path` | `~/.local/share/squire/skills` | `SQUIRE_SKILLS_PATH` | Directory containing skill definitions |


```toml
[skills]
path = "~/.local/share/squire/skills"
```

### SKILL.md Format

Each skill is a directory containing a `SKILL.md` file with YAML frontmatter and Markdown instructions:

```yaml
---
name: restart-on-error
description: Check container health and restart errored containers.
metadata:
  host: prod-apps-01
  trigger: manual
---

Check the status of all Docker containers on the target host.
If any containers are in an errored state, check their logs and restart them.
```

The format follows the [Open Agent Skills spec](https://agentskills.io/specification). `name` and `description` are spec-required top-level fields. Squire-specific fields live under `metadata`:


| Key                | Required | Default  | Description                                                                                |
| ------------------ | -------- | -------- | ------------------------------------------------------------------------------------------ |
| `name`             | Yes      |          | Skill name — lowercase letters, numbers, hyphens, max 64 chars. Must match directory name. |
| `description`      | Yes      |          | What the skill does and when to use it (max 1024 chars).                                   |
| `metadata.host`    | No       | `all`    | Target host (`all` or a specific host name)                                                |
| `metadata.trigger` | No       | `manual` | `manual` (on-demand) or `watch` (each watch cycle)                                         |
| `metadata.enabled` | No       | `true`   | Whether the skill is active                                                                |


The `metadata` key is omitted entirely when all Squire-specific fields are at their defaults.

Skills with `trigger: watch` are appended to the watch mode check-in prompt each cycle. Manual skills can be executed from the web UI or CLI.

---

## Database -- `[db]`

Squire persists chat history, system snapshots, events, and alert rules to SQLite.


| Key                         | Default                           | Env Var                               | Description                                |
| --------------------------- | --------------------------------- | ------------------------------------- | ------------------------------------------ |
| `path`                      | `~/.local/share/squire/squire.db` | `SQUIRE_DB_PATH`                      | Path to the SQLite database file           |
| `snapshot_interval_minutes` | `15`                              | `SQUIRE_DB_SNAPSHOT_INTERVAL_MINUTES` | Minutes between automatic system snapshots |


```toml
[db]
path = "~/.local/share/squire/squire.db"
snapshot_interval_minutes = 15
```

---

## Remote Hosts

Hosts are managed at runtime through the CLI or web UI. Squire persists host configuration in SQLite and makes changes available immediately without a restart.

> **Note:** While `[[hosts]]` entries can appear in `squire.toml`, they are **not loaded** by the application. Use the CLI or web UI to manage hosts.

### Adding a Host

```bash
squire hosts add --name media-server --address 192.168.1.10 --user will
squire hosts add --name nas --address 192.168.1.20 --user will --port 2222 --tags storage --services plex,sonarr
```


| Flag             | Default            | Description                                                          |
| ---------------- | ------------------ | -------------------------------------------------------------------- |
| `--name`         | *(required)*       | Unique alias for the host                                            |
| `--address`      | *(required)*       | Hostname or IP address                                               |
| `--user`         | `"root"`           | SSH username                                                         |
| `--port`         | `22`               | SSH port                                                             |
| `--key-file`     | *(auto-generated)* | Path to SSH private key (uses auto-generated ed25519 key by default) |
| `--tags`         | `[]`               | Comma-separated tags for grouping                                    |
| `--services`     | `[]`               | Comma-separated Docker Compose service names on this host            |
| `--service-root` | `"/opt"`           | Root directory for compose service directories on the host           |


### Enrollment Flow

On `hosts add`, Squire generates a dedicated ed25519 SSH key for the host and stores it at `~/.config/squire/keys/<name>`. It then attempts to deploy the public key automatically using your existing SSH access.

- **Auto-deploy succeeds** — the host status becomes `active` and Squire can connect immediately.
- **Auto-deploy fails** (no existing credentials, key-based auth not yet configured) — the host status is set to `pending_key` and Squire displays the public key for manual installation:

```bash
# Copy the public key shown by `hosts add`, then on the target machine:
echo "<public-key>" >> ~/.ssh/authorized_keys
```

Once the key is installed, verify the connection:

```bash
squire hosts verify media-server
```

A successful verify transitions the host to `active`.

You can also retrieve the public key for a host via the API or web UI:

```
GET /api/hosts/media-server/public-key
```

The web UI host detail page also displays the public key for `pending_key` hosts.

### Host Status


| Status        | Meaning                                             |
| ------------- | --------------------------------------------------- |
| `active`      | SSH key installed, Squire can connect               |
| `pending_key` | Awaiting public key installation on the target host |


### Listing and Removing Hosts

```bash
squire hosts list              # show all enrolled hosts and their status
squire hosts remove nas        # remove a host and its SSH key
```

### Using Hosts

Once enrolled, mention a host by name in conversation and Squire targets it automatically. Every tool also accepts an explicit `host` parameter. Remote tool calls receive a **+1 risk bump** — for example, `docker_ps` on a remote host is risk level 2 instead of 1.

### Web UI and API

The `/hosts` page in the web UI provides an "Add Host" dialog and lists all enrolled hosts with their status, tags, and services. The public key for `pending_key` hosts is shown inline.

Equivalent API endpoints:


| Method   | Path                           | Description                    |
| -------- | ------------------------------ | ------------------------------ |
| `POST`   | `/api/hosts`                   | Enroll a new host              |
| `GET`    | `/api/hosts`                   | List all hosts                 |
| `DELETE` | `/api/hosts/{name}`            | Remove a host                  |
| `POST`   | `/api/hosts/{name}/verify`     | Verify SSH connectivity        |
| `GET`    | `/api/hosts/{name}/public-key` | Retrieve the host's public key |


---

## Watch Mode -- `[watch]`

Operational configuration for autonomous watch mode (`squire watch`). See [CLI reference](cli.md) for full details.

Risk policy for watch mode is configured under `[guardrails.watch]`, not here.


| Key                        | Default      | Env Var                                 | Description                   |
| -------------------------- | ------------ | --------------------------------------- | ----------------------------- |
| `interval_minutes`         | `5`          | `SQUIRE_WATCH_INTERVAL_MINUTES`         | Minutes between watch cycles  |
| `max_tool_calls_per_cycle` | `15`         | `SQUIRE_WATCH_MAX_TOOL_CALLS_PER_CYCLE` | Tool call budget per cycle    |
| `cycle_timeout_seconds`    | `300`        | `SQUIRE_WATCH_CYCLE_TIMEOUT_SECONDS`    | Max wall-clock time per cycle |
| `cycles_per_session`       | `50`         | `SQUIRE_WATCH_CYCLES_PER_SESSION`       | Rotate session after N cycles |
| `checkin_prompt`           | *(built-in)* | `SQUIRE_WATCH_CHECKIN_PROMPT`           | Prompt injected each cycle    |
| `notify_on_action`         | `true`       | `SQUIRE_WATCH_NOTIFY_ON_ACTION`         | Notify on corrective actions  |
| `notify_on_blocked`        | `true`       | `SQUIRE_WATCH_NOTIFY_ON_BLOCKED`        | Notify on blocked tool calls  |


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


| Key        | Default | Env Var                        | Description                           |
| ---------- | ------- | ------------------------------ | ------------------------------------- |
| `enabled`  | `false` | `SQUIRE_NOTIFICATIONS_ENABLED` | Enable the notification system        |
| `webhooks` | `[]`    |                                | List of webhook endpoints (see below) |


Each webhook entry:


| Key       | Default      | Description                                       |
| --------- | ------------ | ------------------------------------------------- |
| `name`    | *(required)* | Human-readable name (e.g., `"discord"`, `"ntfy"`) |
| `url`     | *(required)* | URL to POST event payloads to                     |
| `events`  | `["*"]`      | Event categories to subscribe to (`"*"` for all)  |
| `headers` | `{}`         | Optional HTTP headers (e.g., `Authorization`)     |


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

### Email -- `[notifications.email]`

Email-based notifications as an alternative (or complement) to webhooks.

```toml
[notifications.email]
enabled = true
smtp_host = "smtp.example.com"
smtp_port = 587
use_tls = true
smtp_user = "squire@example.com"
smtp_password = "app-password"
from_address = "squire@example.com"
to_addresses = ["admin@example.com"]
events = ["watch.alert", "watch.action"]
```


| Key             | Default | Description                              |
| --------------- | ------- | ---------------------------------------- |
| `enabled`       | `false` | Whether email notifications are enabled  |
| `smtp_host`     | `""`    | SMTP server hostname                     |
| `smtp_port`     | `587`   | SMTP port (typically 587 for TLS)        |
| `use_tls`       | `true`  | Use STARTTLS for SMTP connection         |
| `smtp_user`     | `""`    | SMTP authentication username             |
| `smtp_password` | `""`    | SMTP authentication password             |
| `from_address`  | `""`    | Email sender address                     |
| `to_addresses`  | `[]`    | Recipient email addresses                |
| `events`        | `["*"]` | Event categories to send (`"*"` for all) |


### Event Categories


| Category          | Source | Description                           |
| ----------------- | ------ | ------------------------------------- |
| `tool_call`       | Chat   | A tool was called                     |
| `error`           | Chat   | An error occurred                     |
| `approval_denied` | Chat   | User denied a tool approval           |
| `watch.start`     | Watch  | Watch mode started                    |
| `watch.stop`      | Watch  | Watch mode stopped                    |
| `watch.action`    | Watch  | Agent took a corrective action        |
| `watch.blocked`   | Watch  | Tool call denied by risk policy       |
| `watch.alert`     | Watch  | Alert rule triggered                  |
| `watch.error`     | Watch  | Exception during a watch cycle        |
| `user`            | Agent  | Ad-hoc notification sent by the agent |


