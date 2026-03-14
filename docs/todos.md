# Squire — TODO

## Theme & Personalization
- [x] Users should be able to set their "house" so the Squire knows what house it represents
- [ ] Should users be able to name their Squire? This could add a personalized touch and enhance the medieval theme

## Bugs
- [x] Fix test isolation — tests were picking up local `squire.toml` instead of using defaults

## Documentation
- [ ] Expand README with usage guide, configuration examples, and TUI screenshots

## Features
- [ ] SSH/remote backend — implement `SSHBackend` to manage remote machines via the `SystemBackend` protocol
- [ ] Streaming LLM responses in the TUI (currently buffered until complete)
- [ ] More tools: package management (`apt`, `brew`), service management (`systemctl`), backup status
- [ ] Web UI or HTTP API for browser/mobile access alongside the TUI

## Infrastructure
- [ ] Structured logging beyond DB events
- [ ] Tool call rate limiting
