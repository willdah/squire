"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiPost } from "@/lib/api";
import type { WatchStatus } from "@/lib/types";
import { Play, Square, Settings } from "lucide-react";

interface WatchStatusCardProps {
  status: WatchStatus | null;
  onConfigure: () => void;
  onRefresh: () => void;
}

export function WatchStatusCard({ status, onConfigure, onRefresh }: WatchStatusCardProps) {
  const isRunning = status?.status === "running";
  const cycle = status?.cycle ? parseInt(status.cycle) : 0;
  const interval = status?.interval_minutes ? parseInt(status.interval_minutes) : 5;
  const riskTolerance = status?.risk_tolerance || "—";

  const handleStart = async () => {
    await apiPost("/api/watch/start");
    onRefresh();
  };

  const handleStop = async () => {
    await apiPost("/api/watch/stop");
    onRefresh();
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Watch Mode</h2>
          <Badge variant={isRunning ? "default" : "secondary"}>
            {isRunning ? "● Running" : "● Stopped"}
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
            <Button variant="destructive" size="sm" onClick={handleStop}>
              <Square className="h-3 w-3 mr-1" />
              Stop
            </Button>
          ) : (
            <Button size="sm" onClick={handleStart}>
              <Play className="h-3 w-3 mr-1" />
              Start Watch
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
