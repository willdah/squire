"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { WatchStatus } from "@/lib/types";

interface WatchStatsCardProps {
  status: WatchStatus | null;
}

function formatUptime(startedAt: string | null | undefined): string {
  if (!startedAt) return "—";
  const diff = Date.now() - new Date(startedAt).getTime();
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function WatchStatsCard({ status }: WatchStatsCardProps) {
  const isRunning = status?.status === "running";

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="text-lg font-semibold mb-3">Session Stats</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-muted-foreground">Uptime</span>
            <p>{isRunning ? formatUptime(status?.started_at) : "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Cycles</span>
            <p>{status?.cycle || "0"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Session</span>
            <p className="font-mono text-xs truncate">{status?.session_id?.slice(0, 8) || "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Interval</span>
            <p>{status?.interval_minutes || "5"}m</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
