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
import { Wrench, ChevronRight, Save, Loader2 } from "lucide-react";
import type { ToolInfo, ToolAction } from "@/lib/types";

const RISK_COLORS: Record<number, string> = {
  1: "bg-green-500/15 text-green-700 dark:text-green-400",
  2: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  3: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  4: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  5: "bg-red-500/15 text-red-700 dark:text-red-400",
};

const GROUP_COLORS: Record<string, string> = {
  monitor: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  container: "bg-purple-500/15 text-purple-700 dark:text-purple-400",
  admin: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
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

  return (
    <div className="space-y-6 animate-fade-in">
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

      {!tools || tools.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
          <Wrench className="h-8 w-8" />
          <p className="text-sm">No tools registered</p>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Approval</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Override</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tools.map((tool) => {
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
