# CLI Reference

Squire is operated through the `squire` command-line interface.

```
squire [COMMAND] [OPTIONS]
```

## Commands

### `squire web`

Start the web interface — a browser-based frontend backed by FastAPI.

```bash
squire web                   # default: http://0.0.0.0:8420
squire web --port 9000       # custom port
squire web --reload          # auto-reload for development
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--port` | `-p` | `8420` | Port to listen on |
| `--host` | `-H` | `0.0.0.0` | Host to bind to |
| `--reload` | | `false` | Enable auto-reload for development |

The web UI provides pages for Chat, Activity, Sessions, Skills, Watch, Hosts, Notifications, and Config.

---

### `squire watch`

Start autonomous watch mode -- a headless monitoring loop.

```bash
squire watch                 # start monitoring
squire watch status          # check status from another terminal
```

Watch mode periodically:
1. Collects system snapshots from all configured hosts
2. Injects a check-in prompt into the agent
3. Lets the agent reason about system state and take action
4. Persists responses and dispatches webhook notifications

Tools above the configured risk tolerance are auto-denied (no interactive approval). Session state is rotated after a configurable number of cycles to bound memory.

Logs to stdout in structured format, suitable for systemd/journald.

**Operational config** (`[watch]` section in `squire.toml`):

| Field | Default | Description |
|---|---|---|
| `interval_minutes` | `5` | Minutes between watch cycles |
| `max_tool_calls_per_cycle` | `15` | Tool call budget per cycle |
| `cycle_timeout_seconds` | `300` | Max wall-clock time per cycle |
| `cycles_per_session` | `50` | Rotate ADK session after this many cycles |
| `checkin_prompt` | *(built-in)* | Prompt injected each cycle |
| `notify_on_action` | `true` | Notify when agent takes corrective action |
| `notify_on_blocked` | `true` | Notify when a tool call is blocked |

**Risk policy** (`[guardrails.watch]` section):

| Field | Default | Description |
|---|---|---|
| `tolerance` | `read-only` | Risk tolerance for watch mode |
| `tools_allow` | `[]` | Additional tools to auto-allow in watch mode |
| `tools_deny` | `[]` | Additional tools to deny in watch mode |

**Notification categories:**

| Category | Description |
|---|---|
| `watch.start` | Watch mode started |
| `watch.stop` | Watch mode stopped |
| `watch.action` | Agent took a corrective action |
| `watch.blocked` | Tool call denied by risk policy |
| `watch.alert` | Watch loop detected an anomaly |
| `watch.error` | Exception during a cycle |

---

### `squire skills`

Manage file-based skills (Open Agent Skills spec). Skills are stored as `SKILL.md` files in the configured skills directory (default `~/.local/share/squire/skills`).

#### `squire skills list`

List all configured skills.

```bash
squire skills list
```

#### `squire skills show`

Display a skill's metadata and instructions.

```bash
squire skills show restart-on-error
```

#### `squire skills add`

Create a new skill from a Markdown instructions file.

```bash
squire skills add --name restart-on-error --description "Restart errored containers" --instructions-file instructions.md
squire skills add -n my-check -d "Health check" -f check.md --host prod-01 --trigger watch
```

| Option | Short | Required | Default | Description |
|---|---|---|---|---|
| `--name` | `-n` | Yes | | Skill name — lowercase letters, numbers, hyphens (max 64 chars) |
| `--description` | `-d` | Yes | | What the skill does and when to use it |
| `--instructions-file` | `-f` | Yes | | Path to Markdown file with instructions |
| `--host` | | No | `all` | Target host (`all` or a specific host name) |
| `--trigger` | `-t` | No | `manual` | `manual` or `watch` |

#### `squire skills remove`

Delete a skill and its directory.

```bash
squire skills remove restart-on-error
```

#### `squire skills enable`

Enable a previously disabled skill.

```bash
squire skills enable restart-on-error
```

#### `squire skills disable`

Disable a skill without deleting it.

```bash
squire skills disable restart-on-error
```

---

### `squire sessions`

Manage chat sessions.

#### `squire sessions list`

List recent chat sessions.

```bash
squire sessions list
```

Displays a table with session ID, creation time, last activity, and a preview of the conversation.

#### `squire sessions clear`

Delete all chat sessions and their messages, and purge durable ADK session state.

```bash
squire sessions clear         # prompts for confirmation
squire sessions clear --yes   # skip confirmation
```

---

### `squire version`

Show the installed Squire version.

```bash
squire version
```
