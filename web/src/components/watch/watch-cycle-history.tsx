"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import { apiGet, apiDelete } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
          case "incident":
            return (
              <div key={event.id} className="text-orange-500">
                ⚠ {(content.severity as string)?.toUpperCase()} {(content.title as string)} ({content.host as string})
              </div>
            );
          case "phase":
            return (
              <div key={event.id} className="text-blue-500">
                ◇ {(content.phase as string)}: {(content.summary as string)}
              </div>
            );
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
  const [expanded, setExpanded] = useState<number | null>(null);
  const [extraCycles, setExtraCycles] = useState<WatchCycle[]>([]);
  const [nextPage, setNextPage] = useState(2);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const PER_PAGE = 20;

  const { data: firstPage, mutate } = useSWR(
    "/api/watch/cycles?page=1",
    () => apiGet<WatchCycle[]>(`/api/watch/cycles?page=1&per_page=${PER_PAGE}`),
  );

  const allCycles = firstPage ? [...firstPage, ...extraCycles] : null;
  const showLoadMore = hasMore && (firstPage?.length ?? 0) >= PER_PAGE;

  const handleLoadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const page = await apiGet<WatchCycle[]>(`/api/watch/cycles?page=${nextPage}&per_page=${PER_PAGE}`);
      setExtraCycles((prev) => [...prev, ...page]);
      setHasMore(page.length >= PER_PAGE);
      setNextPage((p) => p + 1);
    } finally {
      setLoadingMore(false);
    }
  }, [nextPage]);

  const handleBackToLatest = useCallback(() => {
    setExtraCycles([]);
    setNextPage(2);
    setHasMore(true);
    mutate();
  }, [mutate]);

  const handleClear = useCallback(async () => {
    setClearing(true);
    try {
      await apiDelete("/api/watch/cycles");
      setConfirmOpen(false);
      setExtraCycles([]);
      setNextPage(2);
      setHasMore(true);
      mutate();
    } finally {
      setClearing(false);
    }
  }, [mutate]);

  if (!allCycles) {
    return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">Loading cycles...</div>;
  }

  if (allCycles.length === 0) {
    return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">No cycles recorded yet.</div>;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          {nextPage > 2 && (
            <Button variant="ghost" size="sm" onClick={handleBackToLatest} className="text-xs text-muted-foreground">
              Back to Latest
            </Button>
          )}
        </div>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger
            render={
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground">
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Clear History
              </Button>
            }
          />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Clear cycle history?</DialogTitle>
              <DialogDescription>
                This will permanently delete all cycle history. This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleClear} disabled={clearing}>
                {clearing ? "Clearing..." : "Clear History"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      <div className="rounded-lg border bg-card divide-y">
        {allCycles.map((cycle) => {
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
                <span className="text-muted-foreground text-xs">{cycle.blocked_count || 0} blocked</span>
                <span className="text-muted-foreground text-xs">{cycle.incident_count || 0} incidents</span>
                <Badge variant={statusColor} className="text-xs">{cycle.status}</Badge>
                {cycle.resolved && <Badge variant="secondary" className="text-xs">resolved</Badge>}
                {cycle.escalated && <Badge variant="destructive" className="text-xs">escalated</Badge>}
                {cycle.duration_seconds && (
                  <span className="text-muted-foreground text-xs ml-auto">{cycle.duration_seconds.toFixed(1)}s</span>
                )}
              </button>
              {isExpanded && <CycleDetail cycle={cycle.cycle} />}
            </div>
          );
        })}
        {showLoadMore && (
          <div className="p-3 text-center">
            <Button variant="ghost" size="sm" onClick={handleLoadMore} disabled={loadingMore}>
              {loadingMore ? "Loading..." : "Load more"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
