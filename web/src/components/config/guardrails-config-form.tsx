"use client";

import { useState } from "react";
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface GuardrailsConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  tomlPath: string | null;
  onSaved: () => void;
}

const TOLERANCE_OPTIONS = [
  { value: "", label: "Default (inherit)" },
  { value: "read-only", label: "Read Only" },
  { value: "cautious", label: "Cautious" },
  { value: "standard", label: "Standard" },
  { value: "full-trust", label: "Full Trust" },
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

export function GuardrailsConfigForm({ values, envOverrides, tomlPath, onSaved }: GuardrailsConfigFormProps) {
  const toArr = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
  const toStr = (v: unknown): string => (v != null ? String(v) : "");

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
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = (field: string) => envOverrides.includes(field);

  const isDirty =
    !arraysEqual(values.tools_allow, toolsAllow) ||
    !arraysEqual(values.tools_require_approval, toolsRequireApproval) ||
    !arraysEqual(values.tools_deny, toolsDeny) ||
    monitorTolerance !== toStr(values.monitor_tolerance) ||
    containerTolerance !== toStr(values.container_tolerance) ||
    adminTolerance !== toStr(values.admin_tolerance) ||
    notifierTolerance !== toStr(values.notifier_tolerance) ||
    watchTolerance !== toStr(values.watch_tolerance) ||
    !arraysEqual(values.watch_tools_allow, watchToolsAllow) ||
    !arraysEqual(values.watch_tools_deny, watchToolsDeny);

  const revert = () => {
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
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const changed: Record<string, unknown> = {};
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

      const url = persist ? "/api/config/guardrails?persist=true" : "/api/config/guardrails";
      await apiPatch(url, changed);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Guardrails</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
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
        </div>

        <div className="border-t pt-4 space-y-3">
          <Label className="text-sm font-medium">Per-Agent Tolerance</Label>
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

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex items-center justify-between pt-2 border-t">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={persist}
              onChange={(e) => setPersist(e.target.checked)}
              disabled={!tomlPath}
              className="rounded"
            />
            Save to disk{tomlPath ? "" : " (no squire.toml found)"}
          </label>
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
