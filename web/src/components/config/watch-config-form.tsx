"use client";

import { useState } from "react";
import { Lock, Loader2, RotateCcw, Save } from "lucide-react";
import type { WatchStatus } from "@/lib/types";
import { apiGet, apiPatch, apiPut } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface WatchConfigFormProps {
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

export function WatchConfigForm({ values, envOverrides, tomlPath, onSaved }: WatchConfigFormProps) {
  const [intervalMinutes, setIntervalMinutes] = useState(Number(values.interval_minutes ?? 5));
  const [cycleTimeout, setCycleTimeout] = useState(Number(values.cycle_timeout_seconds ?? 300));
  const [checkinPrompt, setCheckinPrompt] = useState(String(values.checkin_prompt ?? ""));
  const [notifyOnAction, setNotifyOnAction] = useState(Boolean(values.notify_on_action ?? true));
  const [notifyOnBlocked, setNotifyOnBlocked] = useState(Boolean(values.notify_on_blocked ?? true));
  const [maxToolCallsPerCycle, setMaxToolCallsPerCycle] = useState(
    Number(values.max_tool_calls_per_cycle ?? 15)
  );
  const [cyclesPerSession, setCyclesPerSession] = useState(Number(values.cycles_per_session ?? 12));
  const [maxContextEvents, setMaxContextEvents] = useState(Number(values.max_context_events ?? 40));
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = (field: string) => envOverrides.includes(field);

  const isDirty =
    intervalMinutes !== Number(values.interval_minutes ?? 5) ||
    cycleTimeout !== Number(values.cycle_timeout_seconds ?? 300) ||
    checkinPrompt !== String(values.checkin_prompt ?? "") ||
    notifyOnAction !== Boolean(values.notify_on_action ?? true) ||
    notifyOnBlocked !== Boolean(values.notify_on_blocked ?? true) ||
    maxToolCallsPerCycle !== Number(values.max_tool_calls_per_cycle ?? 15) ||
    cyclesPerSession !== Number(values.cycles_per_session ?? 12) ||
    maxContextEvents !== Number(values.max_context_events ?? 40);

  const revert = () => {
    setIntervalMinutes(Number(values.interval_minutes ?? 5));
    setCycleTimeout(Number(values.cycle_timeout_seconds ?? 300));
    setCheckinPrompt(String(values.checkin_prompt ?? ""));
    setNotifyOnAction(Boolean(values.notify_on_action ?? true));
    setNotifyOnBlocked(Boolean(values.notify_on_blocked ?? true));
    setMaxToolCallsPerCycle(Number(values.max_tool_calls_per_cycle ?? 15));
    setCyclesPerSession(Number(values.cycles_per_session ?? 12));
    setMaxContextEvents(Number(values.max_context_events ?? 40));
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const changed: Record<string, unknown> = {};
      if (intervalMinutes !== Number(values.interval_minutes ?? 5)) changed.interval_minutes = intervalMinutes;
      if (cycleTimeout !== Number(values.cycle_timeout_seconds ?? 300)) changed.cycle_timeout_seconds = cycleTimeout;
      if (checkinPrompt !== String(values.checkin_prompt ?? "")) changed.checkin_prompt = checkinPrompt;
      if (notifyOnAction !== Boolean(values.notify_on_action ?? true)) changed.notify_on_action = notifyOnAction;
      if (notifyOnBlocked !== Boolean(values.notify_on_blocked ?? true)) changed.notify_on_blocked = notifyOnBlocked;
      if (maxToolCallsPerCycle !== Number(values.max_tool_calls_per_cycle ?? 15)) {
        changed.max_tool_calls_per_cycle = maxToolCallsPerCycle;
      }
      if (cyclesPerSession !== Number(values.cycles_per_session ?? 12)) {
        changed.cycles_per_session = cyclesPerSession;
      }
      if (maxContextEvents !== Number(values.max_context_events ?? 40)) {
        changed.max_context_events = maxContextEvents;
      }

      const url = persist ? "/api/config/watch?persist=true" : "/api/config/watch";
      await apiPatch(url, changed);

      try {
        const status = await apiGet<WatchStatus>("/api/watch/status");
        if (status.status === "running" && Object.keys(changed).length > 0) {
          await apiPut("/api/watch/config", changed);
        }
      } catch {
        /* watch API unavailable — server-side config still updated */
      }

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
        <CardTitle className="text-base">Watch</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          These settings apply to the web API immediately. If autonomous watch mode is running, compatible fields are
          also pushed to the watch process so they take effect on the next poll (typically within a few seconds).
          Risk tolerance for watch is controlled under Guardrails (watch tolerance); restart watch after changing it.
        </p>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Interval (minutes)</Label>
            {isLocked("interval_minutes") && <EnvLock field="interval_minutes" prefix="SQUIRE_WATCH_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={intervalMinutes}
            onChange={(e) => setIntervalMinutes(parseInt(e.target.value) || 1)}
            disabled={isLocked("interval_minutes")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Cycle Timeout (seconds)</Label>
            {isLocked("cycle_timeout_seconds") && <EnvLock field="cycle_timeout_seconds" prefix="SQUIRE_WATCH_" />}
          </div>
          <Input
            type="number"
            min={30}
            value={cycleTimeout}
            onChange={(e) => setCycleTimeout(parseInt(e.target.value) || 30)}
            disabled={isLocked("cycle_timeout_seconds")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Check-in Prompt</Label>
            {isLocked("checkin_prompt") && <EnvLock field="checkin_prompt" prefix="SQUIRE_WATCH_" />}
          </div>
          <Textarea
            rows={4}
            value={checkinPrompt}
            onChange={(e) => setCheckinPrompt(e.target.value)}
            disabled={isLocked("checkin_prompt")}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Label>Notify on Action</Label>
            {isLocked("notify_on_action") && <EnvLock field="notify_on_action" prefix="SQUIRE_WATCH_" />}
          </div>
          <Switch
            checked={notifyOnAction}
            onCheckedChange={setNotifyOnAction}
            disabled={isLocked("notify_on_action")}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Label>Notify on Blocked</Label>
            {isLocked("notify_on_blocked") && <EnvLock field="notify_on_blocked" prefix="SQUIRE_WATCH_" />}
          </div>
          <Switch
            checked={notifyOnBlocked}
            onCheckedChange={setNotifyOnBlocked}
            disabled={isLocked("notify_on_blocked")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Max tool calls per cycle</Label>
            {isLocked("max_tool_calls_per_cycle") && (
              <EnvLock field="max_tool_calls_per_cycle" prefix="SQUIRE_WATCH_" />
            )}
          </div>
          <Input
            type="number"
            min={1}
            value={maxToolCallsPerCycle}
            onChange={(e) => setMaxToolCallsPerCycle(parseInt(e.target.value) || 1)}
            disabled={isLocked("max_tool_calls_per_cycle")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Cycles per session</Label>
            {isLocked("cycles_per_session") && <EnvLock field="cycles_per_session" prefix="SQUIRE_WATCH_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={cyclesPerSession}
            onChange={(e) => setCyclesPerSession(parseInt(e.target.value) || 1)}
            disabled={isLocked("cycles_per_session")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Max context events</Label>
            {isLocked("max_context_events") && <EnvLock field="max_context_events" prefix="SQUIRE_WATCH_" />}
          </div>
          <Input
            type="number"
            min={10}
            value={maxContextEvents}
            onChange={(e) => setMaxContextEvents(parseInt(e.target.value) || 10)}
            disabled={isLocked("max_context_events")}
          />
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
