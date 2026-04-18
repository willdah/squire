"use client";

import { useEffect, useState } from "react";
import { Lock, Loader2, RotateCcw, Save, X } from "lucide-react";
import { apiPatch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConfigSource } from "@/lib/types";
import { ConfigHint, ConfigIntro } from "./config-help";
import { SectionResetButton, SourceBadge } from "./provenance";

interface GuardrailsConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  sources: Record<string, ConfigSource>;
  tomlPath: string | null;
  onSaved: () => void;
}

const RISK_OPTIONS = [
  { value: "read-only", label: "Read Only" },
  { value: "cautious", label: "Cautious" },
  { value: "standard", label: "Standard" },
  { value: "full-trust", label: "Full Trust" },
];

const TOLERANCE_OPTIONS = [
  { value: "", label: "Default (inherit)" },
  ...RISK_OPTIONS,
];

function EnvLock({ field, prefix }: { field: string; prefix: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
        </TooltipTrigger>
        <TooltipContent>
          <p>Set by {prefix}{field.toUpperCase()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function TagInput({
  value,
  onChange,
  disabled,
  placeholder,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");

  const addTag = () => {
    const tag = input.trim();
    if (tag && !value.includes(tag)) {
      onChange([...value, tag]);
    }
    setInput("");
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  return (
    <div className="space-y-1.5">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((tag) => (
            <Badge key={tag} variant="secondary" className="text-xs gap-1">
              {tag}
              {!disabled && (
                <button onClick={() => removeTag(tag)} className="hover:text-destructive">
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}
      {!disabled && (
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTag();
            }
          }}
          placeholder={placeholder ?? "Type and press Enter"}
          className="text-xs"
        />
      )}
    </div>
  );
}

function arraysEqual(a: unknown, b: string[]): boolean {
  const arr = Array.isArray(a) ? (a as string[]) : [];
  return arr.length === b.length && arr.every((v, i) => v === b[i]);
}

export function GuardrailsConfigForm({ values, envOverrides, sources, onSaved }: GuardrailsConfigFormProps) {
  const toArr = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
  const toStr = (v: unknown): string => (v != null ? String(v) : "");

  const [riskTolerance, setRiskTolerance] = useState(toStr(values.risk_tolerance) || "cautious");
  const [riskStrict, setRiskStrict] = useState(Boolean(values.risk_strict));
  const [toolsAllow, setToolsAllow] = useState(toArr(values.tools_allow));
  const [toolsRequireApproval, setToolsRequireApproval] = useState(toArr(values.tools_require_approval));
  const [toolsDeny, setToolsDeny] = useState(toArr(values.tools_deny));
  const [monitorTolerance, setMonitorTolerance] = useState(toStr(values.monitor_tolerance));
  const [containerTolerance, setContainerTolerance] = useState(toStr(values.container_tolerance));
  const [adminTolerance, setAdminTolerance] = useState(toStr(values.admin_tolerance));
  const [notifierTolerance, setNotifierTolerance] = useState(toStr(values.notifier_tolerance));
  const [watchTolerance, setWatchTolerance] = useState(toStr(values.watch_tolerance));
  const [watchToolsAllow, setWatchToolsAllow] = useState(toArr(values.watch_tools_allow));
  const [watchToolsDeny, setWatchToolsDeny] = useState(toArr(values.watch_tools_deny));
  const [commandsAllow, setCommandsAllow] = useState(toArr(values.commands_allow));
  const [commandsBlock, setCommandsBlock] = useState(toArr(values.commands_block));
  const [configPaths, setConfigPaths] = useState(toArr(values.config_paths));
  const riskOrigJson = JSON.stringify(
    values.tools_risk_overrides && typeof values.tools_risk_overrides === "object"
      ? (values.tools_risk_overrides as Record<string, unknown>)
      : {},
    null,
    2
  );
  const [toolsRiskJson, setToolsRiskJson] = useState(riskOrigJson);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRiskTolerance(toStr(values.risk_tolerance) || "cautious");
    setRiskStrict(Boolean(values.risk_strict));
    setToolsAllow(toArr(values.tools_allow));
    setToolsRequireApproval(toArr(values.tools_require_approval));
    setToolsDeny(toArr(values.tools_deny));
    setMonitorTolerance(toStr(values.monitor_tolerance));
    setContainerTolerance(toStr(values.container_tolerance));
    setAdminTolerance(toStr(values.admin_tolerance));
    setNotifierTolerance(toStr(values.notifier_tolerance));
    setWatchTolerance(toStr(values.watch_tolerance));
    setWatchToolsAllow(toArr(values.watch_tools_allow));
    setWatchToolsDeny(toArr(values.watch_tools_deny));
    setCommandsAllow(toArr(values.commands_allow));
    setCommandsBlock(toArr(values.commands_block));
    setConfigPaths(toArr(values.config_paths));
    setToolsRiskJson(
      JSON.stringify(
        values.tools_risk_overrides && typeof values.tools_risk_overrides === "object"
          ? (values.tools_risk_overrides as Record<string, unknown>)
          : {},
        null,
        2
      )
    );
  }, [values]);

  const isLocked = (field: string) => envOverrides.includes(field);

  const isDirty =
    riskTolerance !== (toStr(values.risk_tolerance) || "cautious") ||
    riskStrict !== Boolean(values.risk_strict) ||
    !arraysEqual(values.tools_allow, toolsAllow) ||
    !arraysEqual(values.tools_require_approval, toolsRequireApproval) ||
    !arraysEqual(values.tools_deny, toolsDeny) ||
    monitorTolerance !== toStr(values.monitor_tolerance) ||
    containerTolerance !== toStr(values.container_tolerance) ||
    adminTolerance !== toStr(values.admin_tolerance) ||
    notifierTolerance !== toStr(values.notifier_tolerance) ||
    watchTolerance !== toStr(values.watch_tolerance) ||
    !arraysEqual(values.watch_tools_allow, watchToolsAllow) ||
    !arraysEqual(values.watch_tools_deny, watchToolsDeny) ||
    !arraysEqual(values.commands_allow, commandsAllow) ||
    !arraysEqual(values.commands_block, commandsBlock) ||
    !arraysEqual(values.config_paths, configPaths) ||
    toolsRiskJson.trim() !== riskOrigJson.trim();

  const revert = () => {
    setRiskTolerance(toStr(values.risk_tolerance) || "cautious");
    setRiskStrict(Boolean(values.risk_strict));
    setToolsAllow(toArr(values.tools_allow));
    setToolsRequireApproval(toArr(values.tools_require_approval));
    setToolsDeny(toArr(values.tools_deny));
    setMonitorTolerance(toStr(values.monitor_tolerance));
    setContainerTolerance(toStr(values.container_tolerance));
    setAdminTolerance(toStr(values.admin_tolerance));
    setNotifierTolerance(toStr(values.notifier_tolerance));
    setWatchTolerance(toStr(values.watch_tolerance));
    setWatchToolsAllow(toArr(values.watch_tools_allow));
    setWatchToolsDeny(toArr(values.watch_tools_deny));
    setCommandsAllow(toArr(values.commands_allow));
    setCommandsBlock(toArr(values.commands_block));
    setConfigPaths(toArr(values.config_paths));
    setToolsRiskJson(riskOrigJson);
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      let parsedOverrides: Record<string, number> | undefined;
      if (toolsRiskJson.trim() !== riskOrigJson.trim()) {
        try {
          const p = JSON.parse(toolsRiskJson) as unknown;
          if (p === null || typeof p !== "object" || Array.isArray(p)) {
            throw new Error("Must be a JSON object");
          }
          parsedOverrides = p as Record<string, number>;
        } catch {
          setError("Tool risk overrides must be valid JSON object (tool name → number).");
          setSaving(false);
          return;
        }
      }

      const changed: Record<string, unknown> = {};
      if (riskTolerance !== (toStr(values.risk_tolerance) || "cautious")) changed.risk_tolerance = riskTolerance;
      if (riskStrict !== Boolean(values.risk_strict)) changed.risk_strict = riskStrict;
      if (!arraysEqual(values.tools_allow, toolsAllow)) changed.tools_allow = toolsAllow;
      if (!arraysEqual(values.tools_require_approval, toolsRequireApproval))
        changed.tools_require_approval = toolsRequireApproval;
      if (!arraysEqual(values.tools_deny, toolsDeny)) changed.tools_deny = toolsDeny;
      const tolFields = [
        ["monitor_tolerance", monitorTolerance, values.monitor_tolerance],
        ["container_tolerance", containerTolerance, values.container_tolerance],
        ["admin_tolerance", adminTolerance, values.admin_tolerance],
        ["notifier_tolerance", notifierTolerance, values.notifier_tolerance],
        ["watch_tolerance", watchTolerance, values.watch_tolerance],
      ] as const;
      for (const [key, cur, orig] of tolFields) {
        if (cur !== toStr(orig)) changed[key] = cur || null;
      }
      if (!arraysEqual(values.watch_tools_allow, watchToolsAllow)) changed.watch_tools_allow = watchToolsAllow;
      if (!arraysEqual(values.watch_tools_deny, watchToolsDeny)) changed.watch_tools_deny = watchToolsDeny;
      if (!arraysEqual(values.commands_allow, commandsAllow)) changed.commands_allow = commandsAllow;
      if (!arraysEqual(values.commands_block, commandsBlock)) changed.commands_block = commandsBlock;
      if (!arraysEqual(values.config_paths, configPaths)) changed.config_paths = configPaths;
      if (parsedOverrides !== undefined) changed.tools_risk_overrides = parsedOverrides;

      await apiPatch("/api/config/guardrails", changed);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-base">Guardrails</CardTitle>
          <CardDescription>
            Global risk policy, tool lists, per-agent overrides, watch-specific policy, and command/path restrictions.
          </CardDescription>
        </div>
        <SectionResetButton section="guardrails" sources={sources} onReset={onSaved} />
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfigIntro title="How this interacts with chat and watch">
          <p>
            All settings here—including risk tolerance, tool lists, and command allowlists—take effect immediately for
            new chat sessions and tool calls as soon as you save. A running <strong>watch</strong> process reloads
            within seconds; UI edits override <code>squire.toml</code>.
          </p>
        </ConfigIntro>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Risk Tolerance</Label>
            {isLocked("risk_tolerance") && <EnvLock field="risk_tolerance" prefix="SQUIRE_GUARDRAILS_" />}
            <SourceBadge section="guardrails" field="risk_tolerance" sources={sources} onReset={onSaved} />
          </div>
          <Select
            value={riskTolerance}
            onValueChange={(v) => v && setRiskTolerance(v)}
            disabled={isLocked("risk_tolerance")}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RISK_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ConfigHint>
            Global ceiling for how risky a tool may be before it needs approval. Higher tiers allow more destructive
            actions without prompting.
          </ConfigHint>
        </div>

        <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5">
              <Label>Risk Strict</Label>
              {isLocked("risk_strict") && <EnvLock field="risk_strict" prefix="SQUIRE_GUARDRAILS_" />}
            </div>
            <Switch
              checked={riskStrict}
              onCheckedChange={setRiskStrict}
              disabled={isLocked("risk_strict")}
            />
          </div>
          <ConfigHint>
            When on, tools above your tolerance are <strong>denied outright</strong> instead of asking for approval—safer
            for unattended or fast-moving sessions. When off, borderline tools prompt in the chat UI.
          </ConfigHint>
        </div>

        <div className="border-t pt-4 space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Tools Allow</Label>
            {isLocked("tools_allow") && <EnvLock field="tools_allow" prefix="SQUIRE_GUARDRAILS_" />}
          </div>
          <TagInput
            value={toolsAllow}
            onChange={setToolsAllow}
            disabled={isLocked("tools_allow")}
            placeholder="Tool name, press Enter"
          />
          <ConfigHint>
            Tool names that bypass the normal risk gate and may run without approval (use sparingly).
          </ConfigHint>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Tools Require Approval</Label>
            {isLocked("tools_require_approval") && (
              <EnvLock field="tools_require_approval" prefix="SQUIRE_GUARDRAILS_" />
            )}
          </div>
          <TagInput
            value={toolsRequireApproval}
            onChange={setToolsRequireApproval}
            disabled={isLocked("tools_require_approval")}
            placeholder="Tool name, press Enter"
          />
          <ConfigHint>Always prompt for approval before these tools run, even if global tolerance would allow them.</ConfigHint>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Tools Deny</Label>
            {isLocked("tools_deny") && <EnvLock field="tools_deny" prefix="SQUIRE_GUARDRAILS_" />}
          </div>
          <TagInput
            value={toolsDeny}
            onChange={setToolsDeny}
            disabled={isLocked("tools_deny")}
            placeholder="Tool name, press Enter"
          />
          <ConfigHint>Hard-blocked tools: never executed, regardless of tolerance or approval UI.</ConfigHint>
        </div>

        <div className="border-t pt-4 space-y-3">
          <Label className="text-sm font-medium">Per-Agent Tolerance</Label>
          <ConfigHint className="mb-1">
            Optional per-role tolerance. When set, overrides the global Risk Tolerance above for that sub-agent. Empty
            inherits the global value. Only applies when multi-agent mode is enabled; takes effect on the next chat
            session.
          </ConfigHint>
          {(
            [
              ["monitor_tolerance", "Monitor", monitorTolerance, setMonitorTolerance],
              ["container_tolerance", "Container", containerTolerance, setContainerTolerance],
              ["admin_tolerance", "Admin", adminTolerance, setAdminTolerance],
              ["notifier_tolerance", "Notifier", notifierTolerance, setNotifierTolerance],
            ] as const
          ).map(([field, label, value, setter]) => (
            <div key={field} className="flex items-center gap-3">
              <Label className="w-24 text-xs">{label}</Label>
              <Select
                value={value}
                onValueChange={(v) => v != null && setter(v)}
                disabled={isLocked(field)}
              >
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Default" />
                </SelectTrigger>
                <SelectContent>
                  {TOLERANCE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {isLocked(field) && <EnvLock field={field} prefix="SQUIRE_GUARDRAILS_" />}
            </div>
          ))}
        </div>

        <div className="border-t pt-4 space-y-3">
          <Label className="text-sm font-medium">Watch Mode Overrides</Label>
          <ConfigHint className="mb-1">
            Policy for headless <code>squire watch</code>. Requires a watch restart to apply in the watch process; web
            chat is unaffected.
          </ConfigHint>
          <div className="flex items-center gap-3">
            <Label className="w-24 text-xs">Tolerance</Label>
            <Select
              value={watchTolerance}
              onValueChange={(v) => v != null && setWatchTolerance(v)}
              disabled={isLocked("watch_tolerance")}
            >
              <SelectTrigger className="flex-1">
                <SelectValue placeholder="Default" />
              </SelectTrigger>
              <SelectContent>
                {TOLERANCE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Watch Tools Allow</Label>
            <TagInput value={watchToolsAllow} onChange={setWatchToolsAllow} disabled={isLocked("watch_tools_allow")} />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Watch Tools Deny</Label>
            <TagInput value={watchToolsDeny} onChange={setWatchToolsDeny} disabled={isLocked("watch_tools_deny")} />
          </div>
        </div>

        <div className="border-t pt-4 space-y-3">
          <Label className="text-sm font-medium">run_command and read_config</Label>
          <ConfigHint className="mb-1">
            Allowlists and blocklists for shell command basenames (not full paths). <code>read_config</code> may only read
            under directories you list here.
          </ConfigHint>
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Label className="text-xs">Commands Allow</Label>
              {isLocked("commands_allow") && <EnvLock field="commands_allow" prefix="SQUIRE_GUARDRAILS_" />}
            </div>
            <TagInput
              value={commandsAllow}
              onChange={setCommandsAllow}
              disabled={isLocked("commands_allow")}
              placeholder="Command basename, press Enter"
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Label className="text-xs">Commands Block</Label>
              {isLocked("commands_block") && <EnvLock field="commands_block" prefix="SQUIRE_GUARDRAILS_" />}
            </div>
            <TagInput
              value={commandsBlock}
              onChange={setCommandsBlock}
              disabled={isLocked("commands_block")}
              placeholder="Command basename, press Enter"
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Label className="text-xs">read_config allowed paths</Label>
              {isLocked("config_paths") && <EnvLock field="config_paths" prefix="SQUIRE_GUARDRAILS_" />}
            </div>
            <TagInput
              value={configPaths}
              onChange={setConfigPaths}
              disabled={isLocked("config_paths")}
              placeholder="Directory path, press Enter"
            />
          </div>
        </div>

        <div className="border-t pt-4 space-y-2">
          <div className="flex items-center gap-1.5">
            <Label className="text-sm font-medium">Tool risk overrides</Label>
            {isLocked("tools_risk_overrides") && (
              <EnvLock field="tools_risk_overrides" prefix="SQUIRE_GUARDRAILS_" />
            )}
          </div>
          <ConfigHint>
            JSON object mapping tool names or <code>tool:action</code> keys to risk integers 1–5. Raises or lowers
            baseline risk for specific tools; combine with allow/deny lists above.
          </ConfigHint>
          <Textarea
            value={toolsRiskJson}
            onChange={(e) => setToolsRiskJson(e.target.value)}
            disabled={isLocked("tools_risk_overrides")}
            rows={6}
            className="font-mono text-xs"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex items-center justify-end pt-2 border-t">
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={revert} disabled={!isDirty}>
              <RotateCcw className="h-3.5 w-3.5 mr-1" />
              Revert
            </Button>
            <Button size="sm" onClick={handleSave} disabled={!isDirty || saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              Save
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
