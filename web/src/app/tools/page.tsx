"use client";

import { Fragment, Suspense, useState } from "react";
import useSWR from "swr";
import { apiGet, apiPatch } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Wrench, ChevronRight, Save, Loader2, Search, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { useUrlState, useUrlStateSet } from "@/hooks/use-url-state";
import type { Effect, ToolInfo, ToolAction } from "@/lib/types";

type SortCol = "name" | "group" | "risk" | "effect" | "";

const RISK_COLORS: Record<number, string> = {
  1: "bg-green-500/15 text-green-700 dark:text-green-400",
  2: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  3: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  4: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  5: "bg-red-500/15 text-red-700 dark:text-red-400",
};

const GROUP_COLORS: Record<string, string> = {
  monitor: "bg-sky-500/12 text-sky-700 dark:text-sky-400",
  container: "bg-violet-500/12 text-violet-700 dark:text-violet-400",
  admin: "bg-amber-500/12 text-amber-700 dark:text-amber-400",
};

const EFFECT_COLORS: Record<Effect, string> = {
  read: "bg-sky-500/12 text-sky-700 dark:text-sky-400",
  write: "bg-amber-500/12 text-amber-700 dark:text-amber-400",
  mixed: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
};

// base-ui's <SelectValue> renders the raw value key, not the selected item's
// label. Pass the label text as children so the trigger shows "Risk-based"
// instead of "default".
const APPROVAL_LABELS: Record<string, string> = {
  default: "Risk-based",
  always: "Always",
  never: "Auto-allow",
};

function EffectBadge({ effect }: { effect: Effect }) {
  return (
    <Badge variant="outline" className={EFFECT_COLORS[effect]}>
      {effect}
    </Badge>
  );
}

function RiskBadge({ level, override }: { level: number; override?: number | null }) {
  const effective = override ?? level;
  return (
    <Badge variant="outline" className={RISK_COLORS[effective] ?? ""}>
      {effective}
      {override != null && <span className="ml-1 opacity-60">(was {level})</span>}
    </Badge>
  );
}

function ActionRow({ toolName, action, onOverride, pendingValue }: {
  toolName: string;
  action: ToolAction;
  onOverride: (compound: string, value: number | null) => void;
  pendingValue?: number | null;
}) {
  const compound = `${toolName}:${action.name}`;
  const hasPending = pendingValue !== undefined;
  return (
    <TableRow className="bg-muted/30">
      <TableCell />
      <TableCell className="pl-10 text-sm text-muted-foreground">{action.name}</TableCell>
      <TableCell />
      <TableCell>
        <EffectBadge effect={action.effect} />
      </TableCell>
      <TableCell>
        <RiskBadge level={action.risk_level} override={action.risk_override} />
      </TableCell>
      <TableCell />
      <TableCell />
      <TableCell>
        <Input
          type="number"
          min={1}
          max={5}
          className="w-16 h-7 text-xs"
          placeholder="-"
          value={hasPending ? (pendingValue ?? "") : (action.risk_override ?? "")}
          onChange={(e) => {
            const v = e.target.value ? parseInt(e.target.value, 10) : null;
            if (v !== null && (v < 1 || v > 5)) return;
            onOverride(compound, v);
          }}
        />
      </TableCell>
    </TableRow>
  );
}

export default function ToolsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading tools...</div>}>
      <ToolsPageInner />
    </Suspense>
  );
}

function ToolsPageInner() {
  const { data: tools, mutate } = useSWR("/api/tools", () =>
    apiGet<ToolInfo[]>("/api/tools")
  );
  const [expanded, setExpanded] = useUrlStateSet("expanded");
  const [saving, setSaving] = useState(false);
  const [persist, setPersist] = useState(false);

  // Search, filter, sort — URL-backed so they survive navigation.
  const [search, setSearch] = useUrlState<string>("q", "");
  const [groupFilter, setGroupFilter] = useUrlState<string>("group", "all");
  const [effectFilter, setEffectFilter] = useUrlState<string>("effect", "all");
  const [statusFilter, setStatusFilter] = useUrlState<string>("status", "all");
  const [sortCol, setSortCol] = useUrlState<SortCol>("sort", "");
  const [sortDir, setSortDir] = useUrlState<"asc" | "desc">("dir", "asc");

  // Track pending config changes
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, number | null>>({});
  const [pendingDeny, setPendingDeny] = useState<Set<string> | null>(null);
  const [pendingApproval, setPendingApproval] = useState<Record<string, string | null>>({});

  // Bulk-selection state (ephemeral — cleared after save).
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // `hasPending` must reflect *effective* changes, not just stale entries in
  // the pending maps: a user can edit and then revert a field, and the save
  // bar should disappear.
  const originalDeny = new Set(
    (tools ?? []).filter((t) => t.status === "disabled").map((t) => t.name)
  );

  const denyChanged = (() => {
    if (pendingDeny === null) return false;
    if (pendingDeny.size !== originalDeny.size) return true;
    for (const n of pendingDeny) if (!originalDeny.has(n)) return true;
    return false;
  })();

  const approvalChanged = Object.entries(pendingApproval).some(([name, policy]) => {
    const tool = tools?.find((t) => t.name === name);
    const original = tool?.approval_policy ?? null;
    return policy !== original;
  });

  const overridesChanged = Object.entries(pendingOverrides).some(([key, value]) => {
    const [toolName, actionName] = key.split(":");
    const tool = tools?.find((t) => t.name === toolName);
    if (!tool) return value !== null;
    const original = actionName
      ? tool.actions?.find((a) => a.name === actionName)?.risk_override ?? null
      : tool.risk_override ?? null;
    return value !== original;
  });

  const hasPending = denyChanged || approvalChanged || overridesChanged;

  const toggleExpand = (name: string) => {
    const next = new Set(expanded);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setExpanded(next);
  };

  const getEffectiveStatus = (tool: ToolInfo): boolean => {
    if (pendingDeny !== null) return !pendingDeny.has(tool.name);
    return tool.status === "enabled";
  };

  const getEffectiveApproval = (tool: ToolInfo): string | null => {
    if (tool.name in pendingApproval) return pendingApproval[tool.name];
    return tool.approval_policy;
  };

  const handleToggleStatus = (tool: ToolInfo) => {
    const currentDeny = pendingDeny ?? new Set(
      tools?.filter((t) => t.status === "disabled").map((t) => t.name) ?? []
    );
    const next = new Set(currentDeny);
    if (next.has(tool.name)) next.delete(tool.name);
    else next.add(tool.name);
    setPendingDeny(next);
  };

  const handleApprovalChange = (toolName: string, value: string) => {
    setPendingApproval((prev) => ({
      ...prev,
      [toolName]: value === "default" ? null : value,
    }));
  };

  const handleOverride = (compound: string, value: number | null) => {
    setPendingOverrides((prev) => ({ ...prev, [compound]: value }));
  };

  const toggleSelected = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const clearSelection = () => setSelected(new Set());

  const bulkSetEnabled = (enabled: boolean) => {
    if (!tools || selected.size === 0) return;
    const current = pendingDeny ?? new Set(
      tools.filter((t) => t.status === "disabled").map((t) => t.name)
    );
    const next = new Set(current);
    for (const name of selected) {
      if (enabled) next.delete(name);
      else next.add(name);
    }
    setPendingDeny(next);
  };

  const bulkSetApproval = (value: string) => {
    if (selected.size === 0) return;
    setPendingApproval((prev) => {
      const next = { ...prev };
      for (const name of selected) {
        next[name] = value === "default" ? null : value;
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (!tools) return;
    setSaving(true);
    try {
      const patch: Record<string, unknown> = {};

      // Build tools_deny from pending
      if (pendingDeny !== null) {
        patch.tools_deny = Array.from(pendingDeny);
      }

      // Build approval lists from pending
      if (Object.keys(pendingApproval).length > 0) {
        // Start from current state
        const currentAllow = new Set(
          tools.filter((t) => t.approval_policy === "never").map((t) => t.name)
        );
        const currentRequire = new Set(
          tools.filter((t) => t.approval_policy === "always").map((t) => t.name)
        );

        for (const [name, policy] of Object.entries(pendingApproval)) {
          currentAllow.delete(name);
          currentRequire.delete(name);
          if (policy === "never") currentAllow.add(name);
          else if (policy === "always") currentRequire.add(name);
        }

        patch.tools_allow = Array.from(currentAllow);
        patch.tools_require_approval = Array.from(currentRequire);
      }

      // Build risk overrides from pending
      if (Object.keys(pendingOverrides).length > 0) {
        // Start from current state
        const currentOverrides: Record<string, number> = {};
        for (const tool of tools) {
          if (tool.actions) {
            for (const a of tool.actions) {
              if (a.risk_override != null) {
                currentOverrides[`${tool.name}:${a.name}`] = a.risk_override;
              }
            }
          } else if (tool.risk_override != null) {
            currentOverrides[tool.name] = tool.risk_override;
          }
        }
        for (const [key, value] of Object.entries(pendingOverrides)) {
          if (value === null) delete currentOverrides[key];
          else currentOverrides[key] = value;
        }
        patch.tools_risk_overrides = currentOverrides;
      }

      const url = persist ? "/api/config/guardrails?persist=true" : "/api/config/guardrails";
      await apiPatch(url, patch);
      setPendingOverrides({});
      setPendingDeny(null);
      setPendingApproval({});
      clearSelection();
      mutate();
    } finally {
      setSaving(false);
    }
  };

  const toggleSort = (col: "name" | "group" | "risk" | "effect") => {
    if (sortCol === col) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const getMaxRisk = (tool: ToolInfo): number => {
    if (tool.actions) return Math.max(...tool.actions.map((a) => a.risk_override ?? a.risk_level));
    return tool.risk_override ?? tool.risk_level ?? 0;
  };

  const filteredTools = (tools ?? [])
    .filter((t) => {
      if (search) {
        const q = search.toLowerCase();
        if (!t.name.toLowerCase().includes(q) && !t.description.toLowerCase().includes(q)) return false;
      }
      if (groupFilter !== "all" && t.group !== groupFilter) return false;
      if (effectFilter !== "all" && t.effect !== effectFilter) return false;
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      return true;
    })
    .sort((a, b) => {
      if (!sortCol) return 0;
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortCol === "name") return a.name.localeCompare(b.name) * dir;
      if (sortCol === "group") return a.group.localeCompare(b.group) * dir;
      if (sortCol === "effect") return a.effect.localeCompare(b.effect) * dir;
      if (sortCol === "risk") return (getMaxRisk(a) - getMaxRisk(b)) * dir;
      return 0;
    });

  const filteredNames = filteredTools.map((t) => t.name);
  const allFilteredSelected =
    filteredNames.length > 0 && filteredNames.every((n) => selected.has(n));

  const toggleSelectAllFiltered = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        for (const n of filteredNames) next.delete(n);
      } else {
        for (const n of filteredNames) next.add(n);
      }
      return next;
    });
  };

  const SortIcon = ({ col }: { col: "name" | "group" | "risk" | "effect" }) => {
    if (sortCol !== col) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />;
    return sortDir === "asc"
      ? <ArrowUp className="h-3 w-3 ml-1" />
      : <ArrowDown className="h-3 w-3 ml-1" />;
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl">Tools</h1>
          {tools && tools.length > 0 && (
            <Badge variant="secondary">{tools.length}</Badge>
          )}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        View and configure the tools Squire has access to.
      </p>

      {tools && tools.length > 0 && (
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search tools..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 text-sm"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Group:</span>
            <Select value={groupFilter} onValueChange={(v) => setGroupFilter(String(v ?? "all"))}>
              <SelectTrigger className="h-8 w-[120px] text-xs">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="monitor">Monitor</SelectItem>
                <SelectItem value="container">Container</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Effect:</span>
            <Select value={effectFilter} onValueChange={(v) => setEffectFilter(String(v ?? "all"))}>
              <SelectTrigger className="h-8 w-[100px] text-xs">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="read">Read</SelectItem>
                <SelectItem value="write">Write</SelectItem>
                <SelectItem value="mixed">Mixed</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Status:</span>
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(String(v ?? "all"))}>
              <SelectTrigger className="h-8 w-[110px] text-xs">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="enabled">Enabled</SelectItem>
                <SelectItem value="disabled">Disabled</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {!tools || tools.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
          <Wrench className="h-8 w-8" />
          <p className="text-sm">No tools registered</p>
        </div>
      ) : (
        <>
          {hasPending && (
            <div className="sticky top-0 z-20 flex items-center justify-between rounded-md border border-primary/30 bg-primary/10 px-3 py-2 backdrop-blur-sm">
              <span className="text-xs text-muted-foreground">You have unsaved changes.</span>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={persist}
                    onChange={(e) => setPersist(e.target.checked)}
                    className="rounded"
                  />
                  Save to disk
                </label>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving ? (
                    <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5 mr-1" />
                  )}
                  Save Changes
                </Button>
              </div>
            </div>
          )}
          {selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/40 px-3 py-2">
              <span className="text-xs font-medium">{selected.size} selected</span>
              <Button size="sm" variant="outline" onClick={() => bulkSetEnabled(true)}>
                Enable
              </Button>
              <Button size="sm" variant="outline" onClick={() => bulkSetEnabled(false)}>
                Disable
              </Button>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground">Approval:</span>
                <Select value="" onValueChange={(v) => bulkSetApproval(String(v ?? "default"))}>
                  <SelectTrigger className="h-7 w-[140px] text-xs">
                    <SelectValue placeholder="Set for all" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Risk-based</SelectItem>
                    <SelectItem value="always">Always</SelectItem>
                    <SelectItem value="never">Auto-allow</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" variant="ghost" onClick={clearSelection} className="ml-auto text-xs">
                Clear
              </Button>
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-9">
                  <input
                    type="checkbox"
                    checked={allFilteredSelected}
                    onChange={toggleSelectAllFiltered}
                    aria-label="Select all visible tools"
                    className="rounded"
                  />
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("name")}>
                  <span className="flex items-center">Name<SortIcon col="name" /></span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("group")}>
                  <span className="flex items-center">Group<SortIcon col="group" /></span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("effect")}>
                  <span className="flex items-center">Effect<SortIcon col="effect" /></span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("risk")}>
                  <span className="flex items-center">Risk<SortIcon col="risk" /></span>
                </TableHead>
                <TableHead>Approval</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Override</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTools.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-8">
                    No tools match your filters
                  </TableCell>
                </TableRow>
              )}
              {filteredTools.map((tool) => {
                const isMulti = tool.actions && tool.actions.length > 0;
                const isExpanded = expanded.has(tool.name);
                return (
                  <Fragment key={tool.name}>
                    <TableRow
                      className={`hover:bg-muted/50${isMulti ? " cursor-pointer" : ""}`}
                      onClick={() => isMulti && toggleExpand(tool.name)}
                    >
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected.has(tool.name)}
                          onChange={() => toggleSelected(tool.name)}
                          aria-label={`Select ${tool.name}`}
                          className="rounded"
                        />
                      </TableCell>
                      <TableCell className="font-medium">
                        <span className="flex items-center gap-1.5">
                          {isMulti && (
                            <ChevronRight
                              className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                            />
                          )}
                          {tool.name}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={GROUP_COLORS[tool.group] ?? ""}>
                          {tool.group}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <EffectBadge effect={tool.effect} />
                      </TableCell>
                      <TableCell>
                        {tool.risk_level != null ? (
                          <RiskBadge level={tool.risk_level} override={tool.risk_override} />
                        ) : (
                          <span className="text-xs text-muted-foreground">per-action</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Select
                          value={getEffectiveApproval(tool) ?? "default"}
                          onValueChange={(v) => handleApprovalChange(tool.name, v ?? "default")}
                        >
                          <SelectTrigger className="h-7 w-[120px] text-xs" onClick={(e) => e.stopPropagation()}>
                            <SelectValue>
                              {APPROVAL_LABELS[getEffectiveApproval(tool) ?? "default"]}
                            </SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="default">Risk-based</SelectItem>
                            <SelectItem value="always">Always</SelectItem>
                            <SelectItem value="never">Auto-allow</SelectItem>
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Switch
                          checked={getEffectiveStatus(tool)}
                          onCheckedChange={() => handleToggleStatus(tool)}
                          size="sm"
                        />
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {tool.risk_level != null && (
                          <Input
                            type="number"
                            min={1}
                            max={5}
                            className="w-16 h-7 text-xs"
                            placeholder="-"
                            value={
                              tool.name in pendingOverrides
                                ? pendingOverrides[tool.name] ?? ""
                                : tool.risk_override ?? ""
                            }
                            onChange={(e) => {
                              const v = e.target.value ? parseInt(e.target.value, 10) : null;
                              if (v !== null && (v < 1 || v > 5)) return;
                              handleOverride(tool.name, v);
                            }}
                          />
                        )}
                      </TableCell>
                    </TableRow>
                    {isMulti && isExpanded &&
                      tool.actions!.map((action) => (
                        <ActionRow
                          key={`${tool.name}:${action.name}`}
                          toolName={tool.name}
                          action={action}
                          onOverride={handleOverride}
                          pendingValue={pendingOverrides[`${tool.name}:${action.name}`]}
                        />
                      ))}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>

        </>
      )}
    </div>
  );
}
