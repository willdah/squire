"""Opinionated autonomous playbooks for watch mode incidents."""

from __future__ import annotations

from ..watch_autonomy import Incident


def select_playbooks(incidents: list[Incident]) -> list[str]:
    """Return bounded playbook instructions based on detected incidents."""
    selected: list[str] = []
    keys = {incident.key for incident in incidents}

    if any(key.startswith("container-unhealthy:") for key in keys):
        selected.append(
            
                "### Playbook: Container Recovery\n"
                "- Inspect failing container logs before restart.\n"
                "- Prefer single-container restart over full stack restart.\n"
                "- Do not restart the same container more than once per cycle.\n"
                "- Verify post-restart health (state/status) and report delta."
            
        )

    if any(key.startswith("disk-pressure:") or key.startswith("disk-warning:") for key in keys):
        selected.append(
            
                "### Playbook: Disk Pressure\n"
                "- Identify top disk consumers first (safe diagnostics).\n"
                "- Prefer low-risk cleanup (`docker_cleanup:df`, `prune_images`) before broad destructive actions.\n"
                "- Avoid deleting active volumes or unknown data paths.\n"
                "- Verify free space improvement after each action."
            
        )

    if any(key.startswith("host-unreachable:") for key in keys):
        selected.append(
            
                "### Playbook: Host Reachability\n"
                "- Run network diagnostics to isolate DNS/routing/host-down signals.\n"
                "- Avoid repeated restart attempts on unreachable hosts.\n"
                "- If host remains unreachable, escalate with likely cause and next manual step."
            
        )

    if not selected:
        selected.append(
            
                "### Playbook: Preventive Health Sweep\n"
                "- Check container health and key services.\n"
                "- Investigate anomalies with logs before action.\n"
                "- Execute only minimal corrective actions with clear verification."
            
        )

    return selected
