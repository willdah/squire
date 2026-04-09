import type { HostInfo, SystemStatusResponse, ToolInfo } from "@/lib/types";

export type MentionKind = "host" | "container" | "tool" | "service";

export interface MentionCandidate {
  kind: MentionKind;
  /** Full token without @ (e.g. "nas" or "nas/nginx") */
  token: string;
  /** Shown in the autocomplete row */
  label: string;
  subtitle?: string;
  /** Text to insert into the textarea (includes leading @) */
  insertText: string;
}

function countMap<T>(items: T[], keyFn: (t: T) => string): Map<string, number> {
  const m = new Map<string, number>();
  for (const t of items) {
    const k = keyFn(t);
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  return m;
}

export interface MentionData {
  candidates: MentionCandidate[];
  /** token (no @) -> English phrase for the model */
  expansionByToken: Map<string, string>;
}

/**
 * Build mention autocomplete entries and expansion map from API-shaped data.
 * Duplicate container/service names use "host/name" tokens.
 */
export function buildMentionData(
  hosts: HostInfo[] | undefined,
  systemStatus: SystemStatusResponse | undefined,
  tools: ToolInfo[] | undefined
): MentionData {
  const candidates: MentionCandidate[] = [];
  const expansionByToken = new Map<string, string>();

  const hostList = hosts ?? [];

  for (const h of hostList) {
    const token = h.name;
    expansionByToken.set(
      token,
      `the enrolled host "${h.name}" (${h.address}${h.tags?.length ? `, tags: ${h.tags.join(", ")}` : ""})`
    );
    candidates.push({
      kind: "host",
      token,
      label: h.name,
      subtitle: h.address,
      insertText: `@${token}`,
    });
  }

  const containerOccurrences: { name: string; host: string }[] = [];
  const statusHosts = systemStatus?.hosts ?? {};
  for (const [hostName, snap] of Object.entries(statusHosts)) {
    for (const c of snap.containers ?? []) {
      containerOccurrences.push({ name: c.name, host: hostName });
    }
  }
  const nameCounts = countMap(containerOccurrences, (x) => x.name);

  for (const { name, host } of containerOccurrences) {
    const ambiguous = (nameCounts.get(name) ?? 0) > 1;
    const token = ambiguous ? `${host}/${name}` : name;
    if (expansionByToken.has(token)) continue;
    expansionByToken.set(
      token,
      ambiguous
        ? `container "${name}" on host "${host}"`
        : `container "${name}"`
    );
    candidates.push({
      kind: "container",
      token,
      label: name,
      subtitle: ambiguous ? `on ${host}` : snapSubtitle(statusHosts[host], name),
      insertText: `@${token}`,
    });
  }

  const serviceOccurrences: { name: string; host: string }[] = [];
  for (const h of hostList) {
    for (const svc of h.services ?? []) {
      serviceOccurrences.push({ name: svc, host: h.name });
    }
  }
  const svcCounts = countMap(serviceOccurrences, (x) => x.name);

  for (const { name, host } of serviceOccurrences) {
    let token = (svcCounts.get(name) ?? 0) > 1 ? `${host}/${name}` : name;
    if (expansionByToken.has(token)) {
      token = `${host}/${name}`;
    }
    if (expansionByToken.has(token)) {
      continue;
    }
    expansionByToken.set(
      token,
      `service "${name}" on host "${host}" (from host configuration)`
    );
    candidates.push({
      kind: "service",
      token,
      label: name,
      subtitle: (svcCounts.get(name) ?? 0) > 1 ? `on ${host}` : "service",
      insertText: `@${token}`,
    });
  }

  for (const t of tools ?? []) {
    const token = t.name;
    if (expansionByToken.has(token)) continue;
    expansionByToken.set(token, `the registered tool "${t.name}" (${t.description})`);
    candidates.push({
      kind: "tool",
      token,
      label: t.name,
      subtitle: t.group,
      insertText: `@${token}`,
    });
  }

  return { candidates, expansionByToken };
}

function snapSubtitle(snap: SystemStatusResponse["hosts"][string] | undefined, containerName: string): string {
  if (!snap) return "container";
  const c = snap.containers?.find((x) => x.name === containerName);
  return c?.state ?? c?.status ?? "container";
}

/** Escape for use in RegExp */
function reEscape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Replace @tokens with expansion prose. Longest tokens first.
 * Unknown @words are left unchanged.
 */
export function expandMentionsInText(text: string, expansionByToken: Map<string, string>): string {
  const tokens = [...expansionByToken.keys()].sort((a, b) => b.length - a.length);
  if (tokens.length === 0) return text;

  let out = text;
  for (const token of tokens) {
    const re = new RegExp(`@${reEscape(token)}(?![a-zA-Z0-9_./-])`, "g");
    const exp = expansionByToken.get(token);
    if (!exp) continue;
    out = out.replace(re, exp);
  }
  return out;
}

export function filterMentionCandidates(candidates: MentionCandidate[], query: string): MentionCandidate[] {
  const q = query.trim().toLowerCase();
  if (!q) return candidates;

  const scored = candidates
    .map((c) => {
      const label = c.label.toLowerCase();
      const token = c.token.toLowerCase();
      const sub = (c.subtitle ?? "").toLowerCase();
      let score = 0;
      if (token.startsWith(q) || label.startsWith(q)) score = 100;
      else if (token.includes(q) || label.includes(q) || sub.includes(q)) score = 50;
      return { c, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.c.label.localeCompare(b.c.label));

  return scored.map((x) => x.c);
}
