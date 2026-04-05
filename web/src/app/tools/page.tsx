"use client";

import { Fragment, useState } from "react";
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
import type { ToolInfo, ToolAction } from "@/lib/types";

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
      <TableCell className="pl-10 text-sm text-muted-foreground">{action.name}</TableCell>
      <TableCell />
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
  const { data: tools, mutate } = useSWR("/api/tools", () =>
    apiGet<ToolInfo[]>("/api/tools")
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [persist, setPersist] = useState(false);

  // Search, filter, sort
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortCol, setSortCol] = useState<"name" | "group" | "risk" | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Track pending config changes
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, number | null>>({});
  const [pendingDeny, setPendingDeny] = useState<Set<string> | null>(null);
  const [pendingApproval, setPendingApproval] = useState<Record<string, string | null>>({});

  const hasPending =
    Object.keys(pendingOverrides).length > 0 ||
    pendingDeny !== null ||
    Object.keys(pendingApproval).length > 0;

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
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
      mutate();
    } finally {
      setSaving(false);
    }
  };

  const toggleSort = (col: "name" | "group" | "risk") => {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
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
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      return true;
    })
    .sort((a, b) => {
      if (!sortCol) return 0;
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortCol === "name") return a.name.localeCompare(b.name) * dir;
      if (sortCol === "group") return a.group.localeCompare(b.group) * dir;
      if (sortCol === "risk") return (getMaxRisk(a) - getMaxRisk(b)) * dir;
      return 0;
    });

  const SortIcon = ({ col }: { col: "name" | "group" | "risk" }) => {
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
          <Select value={groupFilter} onValueChange={(v) => setGroupFilter(v ?? "all")}>
            <SelectTrigger className="h-8 w-[130px] text-xs">
              <SelectValue placeholder="All groups" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All groups</SelectItem>
              <SelectItem value="monitor">Monitor</SelectItem>
              <SelectItem value="container">Container</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "all")}>
            <SelectTrigger className="h-8 w-[130px] text-xs">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="enabled">Enabled</SelectItem>
              <SelectItem value="disabled">Disabled</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {!tools || tools.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
          <Wrench className="h-8 w-8" />
          <p className="text-sm">No tools registered</p>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("name")}>
                  <span className="flex items-center">Name<SortIcon col="name" /></span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("group")}>
                  <span className="flex items-center">Group<SortIcon col="group" /></span>
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
                  <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">
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
                            <SelectValue />
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

          {hasPending && (
            <div className="flex items-center justify-between pt-2 border-t">
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
          )}
        </>
      )}
    </div>
  );
}
