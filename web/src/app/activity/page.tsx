"use client";

import { Suspense, useMemo, useState } from "react";
import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { EventTimeline } from "@/components/events/event-timeline";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUrlState, useUrlStateNumber } from "@/hooks/use-url-state";
import type { EventInfo, SessionInfo, WatchRunSummary } from "@/lib/types";

type WindowPreset = "1h" | "24h" | "7d" | "custom";

const CATEGORIES = [
  "all",
  "tool_call",
  "tool_result",
  "error",
  "watch.alert",
  "watch.action",
  "watch.blocked",
  "watch.digest",
  "watch.error",
  "watch.escalation",
  "watch.incident_detected",
  "watch.remediation",
  "watch.start",
  "watch.stop",
  "watch.verification",
];

const WINDOW_PRESETS = [
  { value: "1h", label: "Last 1 hour", hours: 1 },
  { value: "24h", label: "Last 24 hours", hours: 24 },
  { value: "7d", label: "Last 7 days", hours: 24 * 7 },
  { value: "custom", label: "Custom start", hours: null },
] as const;

function computeSinceIso(preset: WindowPreset, custom: string): string | null {
  if (preset === "custom") {
    if (!custom) return null;
    const parsed = new Date(custom);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }
  const match = WINDOW_PRESETS.find((item) => item.value === preset);
  if (!match?.hours) return null;
  return new Date(Date.now() - match.hours * 60 * 60 * 1000).toISOString();
}

export default function ActivityPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading activity...</div>}>
      <ActivityPageInner />
    </Suspense>
  );
}

function ActivityPageInner() {
  const [category, setCategory] = useUrlState<string>("category", "all");
  const [limit, setLimit] = useUrlStateNumber("limit", 100);
  const [sessionId, setSessionId] = useUrlState<string>("session_id", "");
  const [watchId, setWatchId] = useUrlState<string>("watch_id", "");
  const [windowPreset, setWindowPreset] = useUrlState<WindowPreset>("window", "24h");
  const [customSince, setCustomSince] = useUrlState<string>("since", "");

  // `sinceIso` is derived from the preset / custom-start. To keep render pure
  // (no `Date.now()` during render) the anchor is captured in an initializer
  // and updated from the input event handlers below.
  const [sinceIso, setSinceIso] = useState<string | null>(() =>
    computeSinceIso(windowPreset, customSince),
  );

  const applyWindowPreset = (next: WindowPreset) => {
    setWindowPreset(next);
    setSinceIso(computeSinceIso(next, customSince));
  };

  const applyCustomSince = (next: string) => {
    setCustomSince(next);
    if (windowPreset === "custom") {
      setSinceIso(computeSinceIso("custom", next));
    }
  };

  const params = new URLSearchParams();
  if (category !== "all") params.set("category", category);
  if (sinceIso) params.set("since", sinceIso);
  if (sessionId.trim()) params.set("session_id", sessionId.trim());
  if (watchId.trim()) params.set("watch_id", watchId.trim());
  params.set("limit", String(limit));
  const eventsKey = `/api/events?${params.toString()}`;

  const { data: events } = useSWR(
    eventsKey,
    () => apiGet<EventInfo[]>(eventsKey),
    { refreshInterval: 10000 }
  );
  const { data: sessions } = useSWR("/api/sessions?limit=100", () =>
    apiGet<SessionInfo[]>("/api/sessions?limit=100")
  );
  const { data: watchRuns } = useSWR("/api/watch/runs?per_page=100", () =>
    apiGet<WatchRunSummary[]>("/api/watch/runs?per_page=100")
  );

  const sessionOptions = useMemo(
    () => (sessions ?? []).map((session) => session.session_id),
    [sessions]
  );
  const watchOptions = useMemo(
    () => (watchRuns ?? []).map((run) => run.watch_id),
    [watchRuns]
  );

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl">Activity</h1>
          {events && <Badge variant="secondary">{events.length} events in window</Badge>}
        </div>
        <p className="text-sm text-muted-foreground">Live updates every 10s. Use filters to pivot into chat sessions and watch runs.</p>
      </div>

      <Card>
        <CardContent className="pt-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <div className="space-y-2">
              <Label>Window</Label>
              <Select
                value={windowPreset}
                onValueChange={(value) => applyWindowPreset(String(value ?? "24h") as WindowPreset)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WINDOW_PRESETS.map((preset) => (
                    <SelectItem key={preset.value} value={preset.value}>
                      {preset.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {windowPreset === "custom" && (
              <div className="space-y-2">
                <Label htmlFor="since">Start time</Label>
                <Input
                  id="since"
                  type="datetime-local"
                  className="w-full"
                  value={customSince}
                  onChange={(e) => applyCustomSince(e.target.value)}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={category} onValueChange={(v) => setCategory(String(v ?? "all"))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="session-filter">Session ID</Label>
              <Input
                id="session-filter"
                list="activity-session-options"
                className="w-full font-mono text-xs"
                placeholder="Optional chat session"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
              />
              <datalist id="activity-session-options">
                {sessionOptions.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
            <div className="space-y-2">
              <Label htmlFor="watch-filter">Watch ID</Label>
              <Input
                id="watch-filter"
                list="activity-watch-options"
                className="w-full font-mono text-xs"
                placeholder="Optional watch run"
                value={watchId}
                onChange={(e) => setWatchId(e.target.value)}
              />
              <datalist id="activity-watch-options">
                {watchOptions.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
            <div className="space-y-2">
              <Label htmlFor="limit">Limit</Label>
              <Input
                id="limit"
                type="number"
                className="w-full"
                min={1}
                max={1000}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <EventTimeline events={events ?? []} />
    </div>
  );
}
