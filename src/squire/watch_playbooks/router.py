"""Dynamic watch playbook router with deterministic and LLM-assisted selection."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from litellm import acompletion

from ..config import LLMConfig
from ..skills import Skill
from ..watch_autonomy import Incident, severity_rank

logger = logging.getLogger(__name__)

PlaybookPath = Literal["deterministic_single", "tie_break", "semantic", "generic"]

GENERIC_FALLBACK_PLAYBOOK = (
    "### Playbook: Default Watch Triage\n"
    "- Validate the signal with targeted diagnostics before taking action.\n"
    "- Prefer read-only checks and minimal-blast-radius operations.\n"
    "- If confidence is low or issue remains unresolved, escalate with clear manual next steps."
)


@dataclass(slots=True)
class RouterThresholds:
    single_match_plausibility_min: float = 0.45
    tie_break_min_confidence: float = 0.60
    semantic_min_confidence: float = 0.55


@dataclass(slots=True)
class PlaybookSelection:
    incident: Incident
    candidate_count: int
    selected_playbook: str | None
    path_taken: PlaybookPath
    confidence: float
    reasoning: str
    instructions: str


async def route_playbooks_for_incidents(
    incidents: list[Incident],
    playbook_skills: list[Skill],
    *,
    llm_config: LLMConfig | None = None,
    thresholds: RouterThresholds | None = None,
    max_selected_playbooks: int = 3,
    semantic_candidate_cap: int = 10,
    prompt_char_budget: int = 6000,
) -> tuple[list[str], list[PlaybookSelection]]:
    """Route one playbook per incident; return merged prompt blocks and selection trace."""
    thresholds = thresholds or RouterThresholds()
    ordered_incidents = sorted(incidents, key=lambda inc: (severity_rank(inc.severity), inc.key))
    selections: list[PlaybookSelection] = []

    for incident in ordered_incidents:
        deterministic = _deterministic_candidates(incident, playbook_skills)
        if len(deterministic) == 1:
            skill = deterministic[0]
            confidence, reasoning = await _plausibility_check(incident, skill, llm_config)
            if confidence >= thresholds.single_match_plausibility_min:
                selections.append(
                    PlaybookSelection(
                        incident=incident,
                        candidate_count=1,
                        selected_playbook=skill.name,
                        path_taken="deterministic_single",
                        confidence=confidence,
                        reasoning=reasoning,
                        instructions=skill.instructions,
                    )
                )
            else:
                selections.append(_generic_selection(incident, 1, confidence, "Plausibility check below threshold"))
            continue

        if len(deterministic) > 1:
            picked, confidence, reasoning = await _llm_choose_best(
                incident,
                deterministic,
                llm_config=llm_config,
                mode="tie_break",
            )
            if picked is not None and confidence >= thresholds.tie_break_min_confidence:
                selections.append(
                    PlaybookSelection(
                        incident=incident,
                        candidate_count=len(deterministic),
                        selected_playbook=picked.name,
                        path_taken="tie_break",
                        confidence=confidence,
                        reasoning=reasoning,
                        instructions=picked.instructions,
                    )
                )
            else:
                selections.append(_generic_selection(incident, len(deterministic), confidence, reasoning))
            continue

        semantic_candidates = _semantic_candidates(incident, playbook_skills, semantic_candidate_cap)
        if not semantic_candidates:
            selections.append(_generic_selection(incident, 0, 0.0, "No host-compatible semantic candidates"))
            continue

        picked, confidence, reasoning = await _llm_choose_best(
            incident,
            semantic_candidates,
            llm_config=llm_config,
            mode="semantic",
        )
        if picked is not None and confidence >= thresholds.semantic_min_confidence:
            selections.append(
                PlaybookSelection(
                    incident=incident,
                    candidate_count=len(semantic_candidates),
                    selected_playbook=picked.name,
                    path_taken="semantic",
                    confidence=confidence,
                    reasoning=reasoning,
                    instructions=picked.instructions,
                )
            )
        else:
            selections.append(_generic_selection(incident, len(semantic_candidates), confidence, reasoning))

    merged_instructions = _merge_selected_playbooks(
        selections,
        max_selected_playbooks=max_selected_playbooks,
        prompt_char_budget=prompt_char_budget,
    )
    return merged_instructions, selections


def _deterministic_candidates(incident: Incident, playbook_skills: list[Skill]) -> list[Skill]:
    return [
        skill
        for skill in playbook_skills
        if _host_compatible(skill.hosts, incident.host)
        and any(incident.key.startswith(prefix) for prefix in skill.incident_keys)
    ]


def _semantic_candidates(incident: Incident, playbook_skills: list[Skill], cap: int) -> list[Skill]:
    compatible = [skill for skill in playbook_skills if _host_compatible(skill.hosts, incident.host)]
    compatible.sort(key=lambda s: s.name)
    return compatible[:cap]


def _host_compatible(hosts: list[str], incident_host: str) -> bool:
    return "all" in hosts or incident_host in hosts


def _generic_selection(
    incident: Incident, candidate_count: int, confidence: float, reasoning: str
) -> PlaybookSelection:
    return PlaybookSelection(
        incident=incident,
        candidate_count=candidate_count,
        selected_playbook=None,
        path_taken="generic",
        confidence=max(0.0, min(confidence, 1.0)),
        reasoning=reasoning,
        instructions=GENERIC_FALLBACK_PLAYBOOK,
    )


def _merge_selected_playbooks(
    selections: list[PlaybookSelection],
    *,
    max_selected_playbooks: int,
    prompt_char_budget: int,
) -> list[str]:
    by_name: dict[str, dict] = {}
    for selection in selections:
        name = selection.selected_playbook or "__generic__"
        if name not in by_name:
            by_name[name] = {
                "instructions": selection.instructions,
                "incident_keys": [],
            }
        by_name[name]["incident_keys"].append(selection.incident.key)

    merged: list[str] = []
    used_chars = 0
    for name in sorted(by_name):
        if len(merged) >= max_selected_playbooks:
            break
        item = by_name[name]
        if name == "__generic__":
            block = item["instructions"]
        else:
            header = f"### Playbook: {name} (selected for: {', '.join(item['incident_keys'])})"
            block = f"{header}\n{item['instructions']}"
        if used_chars + len(block) > prompt_char_budget:
            break
        merged.append(block)
        used_chars += len(block)
    return merged


async def _plausibility_check(incident: Incident, skill: Skill, llm_config: LLMConfig | None) -> tuple[float, str]:
    if llm_config is None:
        return _heuristic_similarity(incident, skill), "Heuristic plausibility"
    prompt = (
        "Score how plausible this playbook is for the incident from 0 to 1.\n"
        f"Incident: key={incident.key}, title={incident.title}, detail={incident.detail}\n"
        f"Playbook: name={skill.name}, description={skill.description}\n"
        'Return JSON: {"confidence": <0-1>, "reasoning": "..."}'
    )
    data = await _llm_json(prompt, llm_config)
    confidence = _safe_confidence(data.get("confidence")) if data else _heuristic_similarity(incident, skill)
    reasoning = str(data.get("reasoning", "LLM plausibility")) if data else "Heuristic plausibility fallback"
    return confidence, reasoning


async def _llm_choose_best(
    incident: Incident,
    candidates: list[Skill],
    *,
    llm_config: LLMConfig | None,
    mode: Literal["tie_break", "semantic"],
) -> tuple[Skill | None, float, str]:
    if not candidates:
        return None, 0.0, "No candidates"
    if llm_config is None:
        best = max(candidates, key=lambda s: _heuristic_similarity(incident, s))
        return best, _heuristic_similarity(incident, best), f"Heuristic {mode} fallback"

    candidate_lines = [
        f"- {idx}: {c.name} | desc={c.description} | keys={','.join(c.incident_keys)} | hosts={','.join(c.hosts)}"
        for idx, c in enumerate(candidates)
    ]
    prompt = (
        f"Choose the best playbook for mode={mode}.\n"
        f"Incident key={incident.key}, severity={incident.severity}, host={incident.host}, detail={incident.detail}\n"
        "Candidates:\n"
        + "\n".join(candidate_lines)
        + '\nReturn JSON: {"index": <int>, "confidence": <0-1>, "reasoning": "..."}'
    )
    data = await _llm_json(prompt, llm_config)
    if not data:
        best = max(candidates, key=lambda s: _heuristic_similarity(incident, s))
        return best, _heuristic_similarity(incident, best), f"Heuristic {mode} fallback"
    idx = data.get("index")
    confidence = _safe_confidence(data.get("confidence"))
    reasoning = str(data.get("reasoning", f"LLM {mode}"))
    if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
        return None, confidence, "LLM returned invalid index"
    return candidates[idx], confidence, reasoning


def _heuristic_similarity(incident: Incident, skill: Skill) -> float:
    incident_text = f"{incident.key} {incident.title} {incident.detail}".lower()
    skill_text = f"{skill.name} {skill.description} {skill.instructions}".lower()
    tokens = {t for t in re.split(r"[^a-z0-9]+", incident_text) if len(t) > 2}
    if not tokens:
        return 0.2
    overlap = sum(1 for t in tokens if t in skill_text)
    return max(0.0, min(1.0, overlap / max(3, len(tokens))))


def _safe_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


async def _llm_json(prompt: str, llm_config: LLMConfig) -> dict | None:
    kwargs: dict = {}
    if llm_config.api_base:
        kwargs["api_base"] = llm_config.api_base
    try:
        response = await acompletion(
            model=llm_config.model,
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=300,
            **kwargs,
        )
    except Exception:
        logger.debug("LLM JSON helper failed", exc_info=True)
        return None
    content = response.choices[0].message.content if response and response.choices else ""
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
