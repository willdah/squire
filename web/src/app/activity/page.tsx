"use client";

import { useMemo, useState } from "react";
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
import type { EventInfo, SessionInfo, WatchRunSummary } from "@/lib/types";

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

export default function ActivityPage() {
  const [category, setCategory] = useState("all");
  const [limit, setLimit] = useState(100);
  const [sessionId, setSessionId] = useState("");
  const [watchId, setWatchId] = useState("");
  const [windowPreset, setWindowPreset] = useState<(typeof WINDOW_PRESETS)[number]["value"]>("24h");
  const [customSince, setCustomSince] = useState("");
  const [presetSinceIso, setPresetSinceIso] = useState<string | null>(null);

  const handleWindowPresetChange = (value: (typeof WINDOW_PRESETS)[number]["value"]) => {
    setWindowPreset(value);
    if (value === "custom") {
      setPresetSinceIso(null);
      return;
    }
    const preset = WINDOW_PRESETS.find((item) => item.value === value);
    const hours = preset?.hours;
    if (!hours) {
      setPresetSinceIso(null);
      return;
    }
    setPresetSinceIso(new Date(Date.now() - hours * 60 * 60 * 1000).toISOString());
  };

  let sinceIso: string | null = presetSinceIso;
  if (windowPreset === "custom") {
    if (!customSince) {
      sinceIso = null;
    } else {
      const parsed = new Date(customSince);
      sinceIso = Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
    }
  }

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
                onValueChange={(value) => handleWindowPresetChange(value as (typeof WINDOW_PRESETS)[number]["value"])}
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
                  onChange={(e) => setCustomSince(e.target.value)}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={category} onValueChange={(v) => setCategory(v ?? "all")}>
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
