"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiGet, apiPost } from "@/lib/api";
import type { WatchStatus } from "@/lib/types";
import { Loader2, Play, Square, Settings } from "lucide-react";

interface WatchStatusCardProps {
  status: WatchStatus | null;
  onConfigure: () => void;
  onRefresh: () => void;
}

export function WatchStatusCard({ status, onConfigure, onRefresh }: WatchStatusCardProps) {
  const [loading, setLoading] = useState<"starting" | "stopping" | null>(null);
  const isRunning = status?.status === "running";
  const cycle = status?.cycle ? parseInt(status.cycle) : 0;
  const interval = status?.interval_minutes ? parseInt(status.interval_minutes) : 5;
  const riskTolerance = status?.risk_tolerance || "—";

  const pollUntilStatus = async (target: string, maxAttempts = 15) => {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      onRefresh();
      const res = await apiGet<WatchStatus>("/api/watch/status");
      if (res.status === target) return;
    }
  };

  const handleStart = async () => {
    setLoading("starting");
    try {
      await apiPost("/api/watch/start");
      await pollUntilStatus("running");
    } finally {
      setLoading(null);
      onRefresh();
    }
  };

  const handleStop = async () => {
    setLoading("stopping");
    try {
      await apiPost("/api/watch/stop");
      await pollUntilStatus("stopped");
    } finally {
      setLoading(null);
      onRefresh();
    }
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Watch Mode</h2>
          <Badge variant={isRunning ? "default" : "secondary"}>
            {loading === "starting" ? "Starting…" : loading === "stopping" ? "Stopping…" : isRunning ? "● Running" : "● Stopped"}
          </Badge>
        </div>
        <div className="text-sm text-muted-foreground space-y-1">
          {isRunning ? (
            <>
              <p>Cycle {cycle} · Every {interval} min · Risk tolerance: {riskTolerance}</p>
              {status?.pid && <p className="text-xs">PID {status.pid}</p>}
            </>
          ) : (
            <>
              {status?.stopped_at && <p>Stopped at {new Date(status.stopped_at).toLocaleTimeString()}</p>}
              {cycle > 0 && <p>Last ran: {cycle} cycles</p>}
            </>
          )}
        </div>
        <div className="flex gap-2 mt-4">
          {isRunning ? (
            <Button variant="destructive" size="sm" onClick={handleStop} disabled={loading !== null}>
              {loading === "stopping" ? (
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              ) : (
                <Square className="h-3 w-3 mr-1" />
              )}
              {loading === "stopping" ? "Stopping…" : "Stop"}
            </Button>
          ) : (
            <Button size="sm" onClick={handleStart} disabled={loading !== null}>
              {loading === "starting" ? (
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              ) : (
                <Play className="h-3 w-3 mr-1" />
              )}
              {loading === "starting" ? "Starting…" : "Start Watch"}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={onConfigure}>
            <Settings className="h-3 w-3 mr-1" />
            Configure
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
