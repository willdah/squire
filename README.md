<div align="center">
  <img src="docs/assets/squire_mascot.png" alt="Squire" width="200">
  <h1>Squire</h1>
  <p><strong>Your homelab's faithful attendant.</strong></p>
</div>

---

## Features

- **Interactive TUI** — Chat with your Squire in a terminal interface with status panel, log viewer, and approval modals
- **Built-in tools** — System info, Docker management, log reading, network diagnostics, config inspection, and guarded command execution
- **Risk profiles** — Control what your Squire can do: `read-only`, `cautious`, `standard`, `full-trust`, or `custom`
- **Multi-model LLM** — Powered by [LiteLLM](https://github.com/BerriAI/litellm) — use Ollama, Anthropic, OpenAI, Gemini, or any supported provider
- **Session persistence** — SQLite-backed chat history with session resume
- **Webhook notifications** — Get alerts on Discord, ntfy.sh, or any HTTP endpoint
- **Personality profiles** — Choose from built-in squire personalities (Rook, Cedric, Wynn) or create your own

## Quickstart

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/wahern/squire.git
cd squire
cp squire.example.toml squire.toml  # edit to taste
uv run squire chat
```

## Configuration

Settings are resolved in order of precedence (highest first):

1. **Environment variables** (`SQUIRE_*`) — always win
2. **TOML config file** — first found from:
   - `./squire.toml` (project directory)
   - `~/.config/squire/squire.toml` (user config)
   - `/etc/squire/squire.toml` (system-wide)
3. **Built-in defaults**

See [`squire.example.toml`](squire.example.toml) for all options.

### LLM Setup

Squire uses LiteLLM, so any supported model works. The default is Ollama:

```toml
[llm]
model = "ollama_chat/llama3.1:8b"
api_base = "http://localhost:11434"
```

### Risk Profiles

Control tool permissions with `risk_profile`:

| Profile | Read | Low-risk mutations | High-risk actions |
|---|---|---|---|
| `read-only` | Allowed | Blocked | Blocked |
| `cautious` | Allowed | Allowed | Needs approval |
| `standard` | Allowed | Allowed | Needs approval |
| `full-trust` | Allowed | Allowed | Allowed |
| `custom` | Per-tool configuration | | |

### Personalization

Give your Squire an identity:

```toml
house = "Agents"              # Your house name
squire_profile = "rook"      # Built-in profile: rook, cedric, wynn
squire_name = "Gareth"       # Custom name (overrides profile name)
```

**Built-in profiles:**
- **Rook** — Watchful and methodical. Concise responses, confirms before acting.
- **Cedric** — Confident and proactive. Anticipates problems, takes initiative.
- **Wynn** — Thoughtful and educational. Explains reasoning, teaches as it goes.

## CLI

```
squire chat                  # Start a chat session
squire chat --resume <id>    # Resume a previous session
squire sessions              # List recent sessions
squire version               # Show version
```

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## License

[MIT](LICENSE) — William Ahern
