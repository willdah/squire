"use client";

import { useEffect, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import { useWatchWebSocket } from "@/hooks/use-watch-websocket";
import type { WatchEvent } from "@/lib/types";

interface WatchLiveStreamProps {
  enabled: boolean;
}

function parseContent(content: string | null): Record<string, unknown> {
  if (!content) return {};
  try {
    return JSON.parse(content);
  } catch {
    return { text: content };
  }
}

function EventRow({ event }: { event: WatchEvent }) {
  const content = parseContent(event.content);

  switch (event.type) {
    case "cycle_start":
      return (
        <div className="text-primary font-medium py-1">
          ── Cycle {event.cycle} started ──
        </div>
      );
    case "cycle_end": {
      const status = (content.status as string) || "unknown";
      const duration = content.duration_seconds as number;
      const blocked = (content.blocked_count as number) || 0;
      const incidentCount = ((content.outcome as Record<string, unknown>)?.incident_count as number) || 0;
      return (
        <div className="text-primary font-medium py-1">
          ── Cycle {event.cycle} ended ({status}{duration ? `, ${duration.toFixed(1)}s` : ""}, incidents:{" "}
          {incidentCount}, blocked: {blocked}) ──
        </div>
      );
    }
    case "incident":
      return (
        <div className="py-0.5 text-orange-500">
          ⚠ {(content.severity as string)?.toUpperCase()} {(content.title as string)} ({content.host as string}) -{" "}
          {content.detail as string}
        </div>
      );
    case "phase":
      return (
        <div className="py-0.5 text-blue-500">
          ◇ {(content.phase as string)}: {(content.summary as string)}
        </div>
      );
    case "tool_call":
      return (
        <div className="py-0.5">
          <span className="text-yellow-500">⚙ {content.name as string}</span>
          <span className="text-muted-foreground ml-2 text-xs">
            {JSON.stringify(content.args)}
          </span>
        </div>
      );
    case "tool_result":
      return (
        <div className="py-0.5 text-muted-foreground text-xs">
          → {(content.output as string)?.slice(0, 200)}
        </div>
      );
    case "token":
      return <span>{(content.text as string) || event.content}</span>;
    case "error":
      return (
        <div className="py-0.5 text-destructive">
          Error: {content.message as string}
        </div>
      );
    case "approval_request":
      return null;
    default:
      return (
        <div className="py-0.5 text-muted-foreground text-xs">
          [{event.type}] {event.content?.slice(0, 100)}
        </div>
      );
  }
}

export function WatchLiveStream({ enabled }: WatchLiveStreamProps) {
  const { status, events, clearEvents } = useWatchWebSocket(enabled);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  useEffect(() => {
    if (!enabled) clearEvents();
  }, [enabled, clearEvents]);

  if (!enabled) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">
        Watch is not running. Start watch mode to see live activity.
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <Badge variant={status === "connected" ? "default" : "secondary"} className="text-xs">
            {status}
          </Badge>
          <span className="text-xs text-muted-foreground">{events.length} events</span>
        </div>
        {events.length > 0 && (
          <Button variant="ghost" size="sm" onClick={clearEvents} className="text-xs text-muted-foreground">
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Clear Stream
          </Button>
        )}
      </div>
      <div ref={scrollRef} className="p-4 font-mono text-sm max-h-[500px] overflow-y-auto">
        {events.length === 0 ? (
          <p className="text-muted-foreground">Waiting for events...</p>
        ) : (
          events.map((event) => <EventRow key={event.id} event={event} />)
        )}
      </div>
    </div>
  );
}
