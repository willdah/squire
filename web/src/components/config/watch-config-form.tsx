"use client";

import { useState } from "react";
import { Lock, Loader2, RotateCcw, Save } from "lucide-react";
import { apiPatch } from "@/lib/api";
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConfigSource } from "@/lib/types";
import { ConfigHint, ConfigIntro } from "./config-help";
import { SectionResetButton, SourceBadge } from "./provenance";

interface WatchConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  sources: Record<string, ConfigSource>;
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

export function WatchConfigForm({ values, envOverrides, sources, onSaved }: WatchConfigFormProps) {
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

      await apiPatch("/api/config/watch", changed);
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
          <CardTitle className="text-base">Watch</CardTitle>
          <CardDescription>
            Autonomous <code>squire watch</code> loop: timing, prompts, limits, and notifications.
          </CardDescription>
        </div>
        <SectionResetButton section="watch" sources={sources} onReset={onSaved} />
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfigIntro title="How saves work">
          <p>
            UI edits land in the database as overrides and take effect immediately; any running watch process reloads
            within a few seconds. <code>squire.toml</code> is read-only from the app — use &ldquo;Reset&rdquo; to revert a
            field to the value in <code>squire.toml</code> or the code default.
          </p>
        </ConfigIntro>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Interval (minutes)</Label>
            {isLocked("interval_minutes") && <EnvLock field="interval_minutes" prefix="SQUIRE_WATCH_" />}
            <SourceBadge section="watch" field="interval_minutes" sources={sources} onReset={onSaved} />
          </div>
          <Input
            type="number"
            min={1}
            value={intervalMinutes}
            onChange={(e) => setIntervalMinutes(parseInt(e.target.value) || 1)}
            disabled={isLocked("interval_minutes")}
          />
          <ConfigHint>Wall-clock wait between autonomous check-in cycles. Lower = more frequent monitoring.</ConfigHint>
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
          <ConfigHint>
            Maximum time one watch cycle may run before it is aborted. Prevents a stuck agent from blocking the loop.
          </ConfigHint>
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
          <ConfigHint>Instructions injected each cycle; shapes what the agent prioritizes during check-ins.</ConfigHint>
        </div>

        <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 px-3 py-3">
          <div className="flex items-center justify-between gap-3">
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
          <ConfigHint>Notify when the watch agent runs one or more tools in a successful cycle.</ConfigHint>
        </div>

        <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 px-3 py-3">
          <div className="flex items-center justify-between gap-3">
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
          <ConfigHint>
            Notify when a tool call is blocked by watch risk policy (visibility in strict setups).
          </ConfigHint>
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
          <ConfigHint>Hard cap on tools per cycle to limit blast radius and cost.</ConfigHint>
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
          <ConfigHint>
            After this many completed cycles, watch starts a fresh ADK session with a short carryover summary—reduces
            memory growth over long runs.
          </ConfigHint>
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
          <ConfigHint>
            How many recent ADK events are kept in session context each cycle. Lower trims history earlier; higher keeps
            more tool transcript in memory.
          </ConfigHint>
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
