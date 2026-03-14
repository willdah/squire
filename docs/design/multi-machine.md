# Multi-Machine Management

How Squire should evolve from managing a single host to managing a fleet of homelab machines.

## Context

Squire currently runs on one machine and interacts with it via `LocalBackend`, which implements the `SystemBackend` protocol. All tools (`system_info`, `docker_ps`, `run_command`, etc.) execute through this abstraction rather than calling subprocess directly — making it straightforward to swap in a different backend.

The goal is multi-machine management: one Squire instance that can monitor, troubleshoot, and act across multiple hosts.

## Approaches

### Option A: SSH Backend

Squire runs on one machine and reaches out to others over SSH. A new `SSHBackend` implements the existing `SystemBackend` protocol — `run()` calls `ssh host cmd` instead of local subprocess.

**Pros:**
- Dead simple — no software to install on targets
- Works with the existing tool/backend architecture unchanged
- One Squire instance, multiple machines
- SSH is well-understood, already authenticated in most homelabs

**Cons:**
- Squire needs SSH keys to every machine
- All commands tunnel through one box
- Latency on every command
- If the hub machine is down, you lose everything
- No local caching or state on target machines

### Option B: Hub + Agent (Beszel-style)

A lightweight `squire-agent` daemon runs on each target machine, exposing a small API (gRPC, HTTP, or Unix-style protocol over SSH). The hub Squire talks to agents instead of running commands directly.

**Pros:**
- Agents can collect and cache data locally (snapshots, metrics, logs)
- Richer than raw SSH — agents can stream events, push alerts, maintain local state
- Scales better across many machines
- Each agent runs with minimal permissions on its own box
- Hub going down doesn't lose target-side state

**Cons:**
- More infrastructure — deploy, update, and secure an agent on every machine
- More code to build and maintain
- Authentication/trust model between hub and agents
- Agent versioning and compatibility

## Recommendation: Phased Approach

Start with Option A (SSH), design for Option B.

### Phase 1: SSHBackend

Implement `SSHBackend` as a new `SystemBackend`. Immediate multi-machine support with zero new infrastructure.

- SSH key-based auth (no password prompts)
- Config maps host aliases to connection details
- Tools are unaware of which backend they're using
- Agent can be told "check the nginx container on `media-server`" and it just works

```toml
[[hosts]]
name = "media-server"
hostname = "192.168.1.10"
user = "will"

[[hosts]]
name = "nas"
hostname = "192.168.1.20"
user = "will"
port = 2222
```

### Phase 2: Lightweight Agent Daemon

Extract the "agent" side into a tiny daemon — essentially `LocalBackend` + a thin API server. Deploy it on target machines.

- Agent binary/script is minimal: run commands, read files, report metrics
- Hub discovers agents via config or mDNS
- Replaces SSH tunneling with direct API calls
- Agents can cache snapshots and stream metrics without being polled

### Phase 3: Fleet Intelligence

Hub reasons across the fleet. Agents push events. The LLM can correlate issues across machines.

- Agents push health heartbeats and alerts
- Hub maintains a fleet-wide view of system state
- LLM can answer "why is my Plex buffering?" by correlating media-server CPU, NAS disk I/O, and network throughput
- Centralized event log across all machines

## Key Design Principle

The `SystemBackend` protocol is already the right abstraction. Each phase just adds a new implementation:

```
Phase 1: SSHBackend    → ssh host cmd
Phase 2: AgentBackend  → http://host:port/api/run
Phase 3: AgentBackend  → same, but with push/streaming
```

Tool code never changes. The backend is selected per-host at runtime.
