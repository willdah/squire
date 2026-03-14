# Squire — TODO

## Theme & Personalization
- [x] Users should be able to set their "house" so the Squire knows what house it represents
- [x] Allow users to name their Squire via `squire_name` config
- [ ] Add ASCII art or color themes to the TUI for a more engaging experience (e.g. house sigils, themed colors)
- [x] Ship with a few pre-configured "Squire profiles" that users can choose from (e.g. "Rook the Cautious", "Cedric the Bold", "Wynn the Wise") with response styles
- [ ] Allow users to customize the Squire's personality and response style via config (e.g. formal vs casual, verbose vs concise, humorous vs serious)

## Bugs
- [x] Fix test isolation — tests were picking up local `squire.toml` instead of using defaults

## Documentation
- [ ] Expand README with usage guide, configuration examples, and TUI screenshots

## Features
- [x] Revamp risk system: layered architecture (RuleGate → ToolAnalyzer → StateMonitor → ActionGate) with integer 1-5 risk levels, framework-agnostic `squire.risk` package, stub layers ready for future implementation
- [ ] SSH/remote backend — implement `SSHBackend` to manage remote machines via the `SystemBackend` protocol
- [ ] Streaming LLM responses in the TUI (currently buffered until complete)
- [ ] More tools: package management (`apt`, `brew`), service management (`systemctl`), backup status
- [ ] Web UI or HTTP API for browser/mobile access alongside the TUI

## Infrastructure
- [ ] Structured logging beyond DB events
- [ ] Tool call rate limiting
