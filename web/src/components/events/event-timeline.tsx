"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Activity } from "lucide-react";
import type { EventInfo } from "@/lib/types";

interface EventTimelineProps {
  events: EventInfo[];
}

const categoryColors: Record<string, string> = {
  tool_call: "default",
  tool_result: "secondary",
  error: "destructive",
  "watch.alert": "destructive",
  "watch.blocked": "secondary",
  "watch.start": "default",
  "watch.stop": "default",
};

const dotColors: Record<string, string> = {
  error: "bg-gauge-crit",
  "watch.alert": "bg-gauge-crit",
  "watch.blocked": "bg-gauge-warn",
  tool_call: "bg-primary",
  tool_result: "bg-muted-foreground",
  "watch.start": "bg-gauge-ok",
  "watch.stop": "bg-muted-foreground",
};

function parseDetails(details: string | undefined): Record<string, unknown> {
  if (!details) return {};
  try {
    const parsed = JSON.parse(details);
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function formatTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return timestamp;
  return parsed.toLocaleString();
}

export function EventTimeline({ events }: EventTimelineProps) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <Activity className="h-8 w-8 opacity-40" />
        <p className="text-sm">No events found</p>
      </div>
    );
  }

  return (
    <div className="relative pl-6">
      {/* Vertical timeline line */}
      <div className="absolute left-2.5 top-2 bottom-2 w-px bg-border/60" />

      <div className="space-y-2">
        {events.map((event, i) => (
          (() => {
            const parsedDetails = parseDetails(event.details);
            const sessionId = event.session_id ?? String(parsedDetails.session_id ?? "");
            const watchId = event.watch_id ?? String(parsedDetails.watch_id ?? "");
            const watchSessionId = event.watch_session_id ?? String(parsedDetails.watch_session_id ?? "");
            const cycleId = event.cycle_id ?? String(parsedDetails.cycle_id ?? "");
            return (
              <div
                key={event.id}
                className="relative flex items-start gap-3 rounded-lg ring-1 ring-border/40 bg-card/50 p-3 animate-fade-in-up"
                style={{ animationDelay: `${Math.min(i * 0.03, 0.3)}s` }}
              >
                {/* Timeline dot */}
                <div
                  className={`absolute -left-[14px] top-4 h-2.5 w-2.5 rounded-full ring-2 ring-background ${
                    dotColors[event.category] || "bg-muted-foreground"
                  }`}
                />

                <div className="flex flex-col gap-1.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge
                      variant={
                        (categoryColors[event.category] as "default" | "secondary" | "destructive") ??
                        "secondary"
                      }
                    >
                      {event.category}
                    </Badge>
                    {event.tool_name && (
                      <span className="text-xs font-mono text-muted-foreground bg-muted/60 rounded-md px-1.5 py-0.5">
                        {event.tool_name}
                      </span>
                    )}
                    <span className="text-[11px] text-muted-foreground/60 ml-auto shrink-0 tabular-nums" title={event.timestamp}>
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {sessionId && (
                      <Link
                        href={`/chat?session=${encodeURIComponent(sessionId)}`}
                        className="rounded-md bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-muted-foreground hover:text-foreground"
                      >
                        session {sessionId.slice(0, 12)}
                      </Link>
                    )}
                    {watchId && (
                      <Link
                        href={`/watch-explorer?watch_id=${encodeURIComponent(watchId)}`}
                        className="rounded-md bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-muted-foreground hover:text-foreground"
                      >
                        watch {watchId.slice(0, 12)}
                      </Link>
                    )}
                    {watchSessionId && (
                      <Link
                        href={`/watch-explorer?watch_id=${encodeURIComponent(watchId)}&watch_session_id=${encodeURIComponent(watchSessionId)}`}
                        className="rounded-md bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-muted-foreground hover:text-foreground"
                      >
                        wss {watchSessionId.slice(0, 10)}
                      </Link>
                    )}
                    {cycleId && (
                      <Link
                        href={`/watch-explorer?watch_id=${encodeURIComponent(watchId)}&watch_session_id=${encodeURIComponent(watchSessionId)}&cycle_id=${encodeURIComponent(cycleId)}`}
                        className="rounded-md bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-muted-foreground hover:text-foreground"
                      >
                        cycle {cycleId.slice(0, 10)}
                      </Link>
                    )}
                    {watchId && (
                      <Link
                        href="/watch"
                        className="rounded-md bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
                      >
                        open watch
                      </Link>
                    )}
                  </div>
                  <p className="text-sm text-foreground/90">{event.summary}</p>
                  {event.details && (
                    <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground bg-muted/40 ring-1 ring-border/20 rounded-lg p-2.5 mt-0.5 font-mono">
                      {event.details.substring(0, 700)}
                    </pre>
                  )}
                </div>
              </div>
            );
          })()
        ))}
      </div>
    </div>
  );
}
