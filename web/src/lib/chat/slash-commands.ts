/**
 * Slash command registry and parsing. Commands expand to natural language before send.
 * Extend SLASH_COMMAND_DEFS to add new commands.
 */

export interface SlashCommandDef {
  /** Stable id for tests and logging */
  id: string;
  /** Primary trigger shown in autocomplete (e.g. "/status") */
  insert: string;
  /** Short description for the menu */
  description: string;
}

/** Ordered list; autocomplete filters by insert/description. */
export const SLASH_COMMAND_DEFS: SlashCommandDef[] = [
  { id: "status", insert: "/status", description: "Show system status for all hosts" },
  { id: "containers", insert: "/containers", description: "List running containers across hosts" },
  { id: "logs", insert: "/logs ", description: "Tail container logs (add container name after /logs)" },
  { id: "restart", insert: "/restart ", description: "Restart a container (add name after /restart)" },
  { id: "watch-start", insert: "/watch start", description: "Start watch mode" },
  { id: "watch-stop", insert: "/watch stop", description: "Stop watch mode" },
  { id: "skill", insert: "/skill ", description: "Run a skill (add skill name after /skill)" },
  { id: "alerts", insert: "/alerts", description: "List active alert rules" },
  { id: "help", insert: "/help", description: "Show available quick commands" },
];

export interface ActiveSlashSegment {
  start: number;
  end: number;
  /** Text after "/", no leading slash */
  query: string;
}

/**
 * Active /command segment for autocomplete: "/" must be first character on its line,
 * and there must be no whitespace between "/" and the cursor.
 */
export function getActiveSlashSegment(value: string, cursor: number): ActiveSlashSegment | null {
  if (cursor <= 0) return null;
  const before = value.slice(0, cursor);
  const lineStart = before.lastIndexOf("\n") + 1;
  const lineBeforeCursor = before.slice(lineStart);
  const slashRel = lineBeforeCursor.indexOf("/");
  if (slashRel !== 0) return null;
  const absoluteSlash = lineStart;
  const afterSlash = value.slice(absoluteSlash + 1, cursor);
  if (/[\s\n]/.test(afterSlash)) return null;
  return { start: absoluteSlash, end: cursor, query: afterSlash };
}

export interface ActiveMentionSegment {
  start: number;
  end: number;
  query: string;
}

/** Active @mention fragment: no whitespace between "@" and cursor. */
export function getActiveMentionSegment(value: string, cursor: number): ActiveMentionSegment | null {
  if (cursor <= 0) return null;
  const before = value.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at === -1) return null;
  const fragment = before.slice(at + 1);
  if (/[\s\n]/.test(fragment)) return null;
  return { start: at, end: cursor, query: fragment };
}

export type AutocompleteMode = "slash" | "mention";

export function getActiveAutocompleteMode(
  value: string,
  cursor: number
): { mode: AutocompleteMode; segment: ActiveSlashSegment | ActiveMentionSegment } | null {
  const mention = getActiveMentionSegment(value, cursor);
  if (mention && cursor > mention.start) {
    return { mode: "mention", segment: mention };
  }
  const slash = getActiveSlashSegment(value, cursor);
  if (slash && cursor > slash.start) {
    return { mode: "slash", segment: slash };
  }
  return null;
}

function rankSlashMatch(queryLower: string, def: SlashCommandDef): number {
  const insertLower = def.insert.trim().toLowerCase();
  const descLower = def.description.toLowerCase();
  if (insertLower.startsWith("/" + queryLower) || (queryLower === "" && insertLower.startsWith("/"))) {
    return queryLower === "" ? 50 : insertLower === "/" + queryLower ? 100 : 80;
  }
  if (insertLower.includes(queryLower) || descLower.includes(queryLower)) {
    return 40;
  }
  return 0;
}

/** Filter slash commands for the menu; higher score sorts first. */
export function filterSlashCommands(query: string): SlashCommandDef[] {
  const q = query.trim().toLowerCase();
  if (q === "") {
    return SLASH_COMMAND_DEFS;
  }
  const scored = SLASH_COMMAND_DEFS.map((def) => ({
    def,
    score: rankSlashMatch(q, def),
  }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.def.insert.localeCompare(b.def.insert));
  return scored.map((x) => x.def);
}

/**
 * Transform the first line if it is a known slash command; otherwise return null.
 * Multi-line: replaces first line only, preserves the rest.
 */
export function transformSlashMessage(trimmed: string): string | null {
  const nl = trimmed.indexOf("\n");
  const firstLine = nl === -1 ? trimmed : trimmed.slice(0, nl);
  const restLines = nl === -1 ? "" : trimmed.slice(nl + 1);

  if (!firstLine.startsWith("/")) return null;
  const inner = firstLine.slice(1).trim();
  if (!inner) return null;

  const lower = inner.toLowerCase();

  let out: string | null = null;

  if (lower === "help" || lower.startsWith("help ")) {
    out =
      "Briefly list what you can help with: system status, containers, logs, restarts, watch mode, skills, and alerts. " +
      "Mention that I can also answer normal questions about the homelab.";
  } else if (lower === "alerts" || lower.startsWith("alerts ")) {
    const extra = inner.slice(6).trim();
    out = extra
      ? `List all active alert rules and their status, with extra context: ${extra}.`
      : "List all active alert rules and their current status.";
  } else if (lower === "containers" || lower.startsWith("containers ")) {
    const extra = inner.slice(10).trim();
    out = extra
      ? `List running containers across enrolled hosts. Focus on: ${extra}.`
      : "List all running containers across enrolled hosts.";
  } else if (lower.startsWith("watch start")) {
    const extra = inner.slice(11).trim();
    out = extra
      ? `Start watch mode (autonomous monitoring). Additional context: ${extra}.`
      : "Start watch mode for autonomous homelab monitoring.";
  } else if (lower.startsWith("watch stop")) {
    const extra = inner.slice(10).trim();
    out = extra
      ? `Stop watch mode. Additional context: ${extra}.`
      : "Stop watch mode.";
  } else if (lower.startsWith("logs ")) {
    const target = inner.slice(5).trim();
    out = target
      ? `Tail recent logs for the container "${target}" and summarize anything important.`
      : null;
  } else if (lower.startsWith("restart ")) {
    const target = inner.slice(8).trim();
    out = target
      ? `Restart the container "${target}" and confirm it comes back healthy.`
      : null;
  } else if (lower.startsWith("skill ")) {
    const name = inner.slice(6).trim();
    out = name
      ? `Execute the skill "${name}" using your tools and report results.`
      : null;
  } else if (lower === "status" || lower.startsWith("status ")) {
    const extra = inner.slice(6).trim();
    out = extra
      ? `Show detailed system status for all enrolled hosts, with emphasis on: ${extra}.`
      : "Show system status for all enrolled hosts (CPU, memory, disk, uptime, containers).";
  }

  if (out === null) return null;
  return restLines ? `${out}\n${restLines}` : out;
}
