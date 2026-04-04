"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { WatchCycle, WatchEvent } from "@/lib/types";

function CycleDetail({ cycle }: { cycle: number }) {
  const { data: events } = useSWR(
    `/api/watch/cycles/${cycle}`,
    () => apiGet<WatchEvent[]>(`/api/watch/cycles/${cycle}`),
  );

  if (!events) return <div className="p-4 text-sm text-muted-foreground">Loading...</div>;

  return (
    <div className="p-4 border-t font-mono text-xs space-y-1">
      {events.map((event) => {
        let content: Record<string, unknown> = {};
        try { content = JSON.parse(event.content || "{}"); } catch { /* empty */ }

        switch (event.type) {
          case "tool_call":
            return (
              <div key={event.id}>
                <span className="text-yellow-500">⚙ {content.name as string}</span>
                <span className="text-muted-foreground ml-2">{JSON.stringify(content.args)}</span>
              </div>
            );
          case "tool_result":
            return (
              <div key={event.id} className="text-muted-foreground">
                → {(content.output as string)?.slice(0, 200)}
              </div>
            );
          case "token":
            return <span key={event.id}>{event.content}</span>;
          case "cycle_start":
          case "cycle_end":
            return null;
          default:
            return (
              <div key={event.id} className="text-muted-foreground">
                [{event.type}] {event.content?.slice(0, 100)}
              </div>
            );
        }
      })}
    </div>
  );
}

export function WatchCycleHistory() {
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);

  const { data: cycles } = useSWR(
    `/api/watch/cycles?page=${page}`,
    () => apiGet<WatchCycle[]>(`/api/watch/cycles?page=${page}&per_page=20`),
  );

  if (!cycles) {
    return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">Loading cycles...</div>;
  }

  if (cycles.length === 0) {
    return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">No cycles recorded yet.</div>;
  }

  return (
    <div className="rounded-lg border bg-card divide-y">
      {cycles.map((cycle) => {
        const isExpanded = expanded === cycle.cycle;
        const statusColor = cycle.status === "ok" ? "default" : "destructive";

        return (
          <div key={cycle.cycle}>
            <button
              className="w-full flex items-center gap-3 p-3 text-sm hover:bg-accent/50 transition-colors text-left"
              onClick={() => setExpanded(isExpanded ? null : cycle.cycle)}
            >
              {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
              <span className="font-medium">Cycle {cycle.cycle}</span>
              <span className="text-muted-foreground text-xs">
                {cycle.started_at ? new Date(cycle.started_at).toLocaleTimeString() : "—"}
              </span>
              <span className="text-muted-foreground text-xs">{cycle.tool_count} tools</span>
              <Badge variant={statusColor} className="text-xs">{cycle.status}</Badge>
              {cycle.duration_seconds && (
                <span className="text-muted-foreground text-xs ml-auto">{cycle.duration_seconds.toFixed(1)}s</span>
              )}
            </button>
            {isExpanded && <CycleDetail cycle={cycle.cycle} />}
          </div>
        );
      })}
      {cycles.length >= 20 && (
        <div className="p-3 text-center">
          <Button variant="ghost" size="sm" onClick={() => setPage((p) => p + 1)}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
