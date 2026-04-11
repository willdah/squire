"use client";

import { useState } from "react";
import { Lock, Loader2, RotateCcw, Save } from "lucide-react";
import { apiPatch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfigHint, ConfigIntro } from "./config-help";

interface AppConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  tomlPath: string | null;
  onSaved: () => void;
}

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

export function AppConfigForm({ values, envOverrides, tomlPath, onSaved }: AppConfigFormProps) {
  const [appName, setAppName] = useState(String(values.app_name ?? "Squire"));
  const [userId, setUserId] = useState(String(values.user_id ?? "squire-user"));
  const [historyLimit, setHistoryLimit] = useState(Number(values.history_limit ?? 50));
  const [maxToolRounds, setMaxToolRounds] = useState(Number(values.max_tool_rounds ?? 10));
  const [multiAgent, setMultiAgent] = useState(Boolean(values.multi_agent));
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = (field: string) => envOverrides.includes(field);

  const isDirty =
    appName !== String(values.app_name ?? "Squire") ||
    userId !== String(values.user_id ?? "squire-user") ||
    historyLimit !== Number(values.history_limit ?? 50) ||
    maxToolRounds !== Number(values.max_tool_rounds ?? 10) ||
    multiAgent !== Boolean(values.multi_agent);

  const revert = () => {
    setAppName(String(values.app_name ?? "Squire"));
    setUserId(String(values.user_id ?? "squire-user"));
    setHistoryLimit(Number(values.history_limit ?? 50));
    setMaxToolRounds(Number(values.max_tool_rounds ?? 10));
    setMultiAgent(Boolean(values.multi_agent));
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const changed: Record<string, unknown> = {};
      if (appName !== String(values.app_name ?? "Squire")) changed.app_name = appName;
      if (userId !== String(values.user_id ?? "squire-user")) changed.user_id = userId;
      if (historyLimit !== Number(values.history_limit ?? 50)) changed.history_limit = historyLimit;
      if (maxToolRounds !== Number(values.max_tool_rounds ?? 10)) changed.max_tool_rounds = maxToolRounds;
      if (multiAgent !== Boolean(values.multi_agent)) changed.multi_agent = multiAgent;

      const url = persist ? "/api/config/app?persist=true" : "/api/config/app";
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
        <CardTitle className="text-base">App</CardTitle>
        <CardDescription>
          Identity and session behavior. Affects new and ongoing chat sessions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfigIntro title="When changes apply">
          <p>
            Saving updates the running API server immediately for new and ongoing chat sessions. Check{" "}
            <strong>Save to disk</strong> below to write values into <code>squire.toml</code> when a file is found.
          </p>
        </ConfigIntro>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>App name</Label>
            {isLocked("app_name") && <EnvLock field="app_name" prefix="SQUIRE_" />}
          </div>
          <Input
            value={appName}
            onChange={(e) => setAppName(e.target.value)}
            disabled={isLocked("app_name")}
            className="text-sm"
          />
          <ConfigHint>Application name registered with the ADK runner (sessions and tooling see this label).</ConfigHint>
        </div>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>User ID</Label>
            {isLocked("user_id") && <EnvLock field="user_id" prefix="SQUIRE_" />}
          </div>
          <Input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            disabled={isLocked("user_id")}
            className="text-sm font-mono"
          />
          <ConfigHint>
            User scope for ADK session storage. Changing it starts a new logical user; use only if you intentionally
            want to separate sessions.
          </ConfigHint>
        </div>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>History Limit</Label>
            {isLocked("history_limit") && <EnvLock field="history_limit" prefix="SQUIRE_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={historyLimit}
            onChange={(e) => setHistoryLimit(parseInt(e.target.value) || 1)}
            disabled={isLocked("history_limit")}
          />
          <ConfigHint>
            Maximum chat messages kept in context for the model. Lower values reduce token use; higher values preserve
            longer conversations.
          </ConfigHint>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Max Tool Rounds</Label>
            {isLocked("max_tool_rounds") && <EnvLock field="max_tool_rounds" prefix="SQUIRE_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={maxToolRounds}
            onChange={(e) => setMaxToolRounds(parseInt(e.target.value) || 1)}
            disabled={isLocked("max_tool_rounds")}
          />
          <ConfigHint>
            Cap on tool-call iterations per single user message. Stops runaway tool loops; raise if the model often needs
            many steps to finish one request.
          </ConfigHint>
        </div>

        <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5">
              <Label>Multi-Agent</Label>
              {isLocked("multi_agent") && <EnvLock field="multi_agent" prefix="SQUIRE_" />}
            </div>
            <Switch
              checked={multiAgent}
              onCheckedChange={setMultiAgent}
              disabled={isLocked("multi_agent")}
            />
          </div>
          <ConfigHint>
            When enabled, requests can be routed to specialized internal agents (still presented as one assistant in the
            UI). Uses more model calls; can improve focus for mixed tasks.
          </ConfigHint>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex items-center justify-between pt-2 border-t">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:items-center">
            <input
              type="checkbox"
              checked={persist}
              onChange={(e) => setPersist(e.target.checked)}
              disabled={!tomlPath}
              className="rounded"
            />
            <span>
              Save to disk{tomlPath ? "" : " (no squire.toml found)"} — also writes{" "}
              <code className="font-mono text-[11px]">squire.toml</code> so values survive restart.
            </span>
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
