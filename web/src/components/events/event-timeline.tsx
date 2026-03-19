"use client";

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

export function EventTimeline({ events }: EventTimelineProps) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
        <Activity className="h-8 w-8" />
        <p className="text-sm">No events found</p>
      </div>
    );
  }

  return (
    <div className="relative pl-6">
      {/* Vertical timeline line */}
      <div className="absolute left-2.5 top-2 bottom-2 w-px bg-border" />

      <div className="space-y-2">
        {events.map((event) => (
          <div
            key={event.id}
            className="relative flex items-start gap-3 rounded-md border p-3 animate-fade-in"
          >
            {/* Timeline dot */}
            <div
              className={`absolute -left-[14px] top-4 h-2.5 w-2.5 rounded-full ring-2 ring-background ${
                dotColors[event.category] || "bg-muted-foreground"
              }`}
            />

            <div className="flex flex-col gap-1 flex-1 min-w-0">
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
                  <span className="text-xs font-mono text-muted-foreground">
                    {event.tool_name}
                  </span>
                )}
                <span className="text-xs text-muted-foreground ml-auto shrink-0">
                  {event.timestamp.substring(0, 19)}
                </span>
              </div>
              <p className="text-sm">{event.summary}</p>
              {event.details && (
                <pre className="text-xs text-muted-foreground bg-muted rounded p-2 overflow-auto max-h-24 mt-1">
                  {event.details.substring(0, 500)}
                </pre>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
