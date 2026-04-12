"""Tests for watch autonomy helpers."""

from squire.skills import Skill
from squire.watch_autonomy import (
    Incident,
    build_cycle_contract_prompt,
    build_cycle_outcome,
    detect_incidents,
    parse_contract_sections,
)
from squire.watch_playbooks import route_playbooks_for_incidents


def test_detect_incidents_container_and_disk():
    snapshot = {
        "local": {
            "disk_usage_raw": "/dev/disk1 100G 94G 6G 94% /",
            "containers": [{"name": "api", "state": "restarting", "status": "unhealthy"}],
        }
    }
    incidents = detect_incidents(snapshot)
    keys = {i.key for i in incidents}
    assert any(key.startswith("disk-pressure:local") for key in keys)
    assert any(key.startswith("container-unhealthy:local:api") for key in keys)


def test_build_prompt_includes_contract_and_blocks():
    incidents = [Incident(key="x", severity="high", title="Host unreachable", detail="timeout", host="node-1")]
    prompt = build_cycle_contract_prompt("Base check", incidents, ["### Playbook"], ["docker_compose:abc"])
    assert "strict autonomous watch mode" in prompt
    assert "## Incident Summary" in prompt
    assert "Do not repeat these recent actions" in prompt


def test_parse_sections_and_outcome():
    response = """
## Incident Summary
Container unhealthy.

## RCA Hypotheses
Crash loop from config drift.

## Action Plan and Actions Taken
Restarted container once.

## Verification Results
Container healthy after restart.

## Escalation
none
"""
    sections = parse_contract_sections(response)
    outcome = build_cycle_outcome([], sections, tool_count=1, blocked_count=0, cycle_status="ok")
    assert sections["incident summary"].startswith("Container unhealthy")
    assert outcome["resolved"] is True
    assert outcome["escalated"] is False


def test_markdown_none_escalation_is_not_escalated():
    response = """
## Incident Summary
Disk check completed.

## RCA Hypotheses
False positive from mount parsing.

## Action Plan and Actions Taken
Ran diagnostics only.

## Verification Results
Healthy.

## Escalation
**None**: no further action required.
"""
    sections = parse_contract_sections(response)
    outcome = build_cycle_outcome([], sections, tool_count=1, blocked_count=0, cycle_status="ok")
    assert outcome["escalated"] is False


async def test_select_playbooks_for_incidents():
    incidents = [
        Incident(key="container-unhealthy:local:api", severity="high", title="Container unhealthy", detail="x"),
        Incident(key="host-unreachable:node-1", severity="high", title="Host unreachable", detail="x", host="node-1"),
    ]
    playbook_skills = [
        Skill(
            name="container-recovery",
            description="Recover unhealthy containers",
            trigger="watch",
            hosts=["all"],
            incident_keys=["container-unhealthy:"],
            instructions="Container Recovery",
        ),
        Skill(
            name="host-reachability",
            description="Handle unreachable hosts",
            trigger="watch",
            hosts=["node-1"],
            incident_keys=["host-unreachable:"],
            instructions="Host Reachability",
        ),
    ]
    playbooks, _ = await route_playbooks_for_incidents(incidents, playbook_skills)
    joined = "\n".join(playbooks)
    assert "container-recovery" in joined
    assert "host-reachability" in joined
