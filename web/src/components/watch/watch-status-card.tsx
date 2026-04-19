"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { apiGet, apiPost } from "@/lib/api";
import type { WatchStatus } from "@/lib/types";
import { Loader2, Play, Square, Settings, Radar, Activity, CircleAlert, ShieldCheck, AlertTriangle } from "lucide-react";
import Link from "next/link";

interface WatchStatusCardProps {
  status: WatchStatus | null;
  onConfigure: () => void;
  onRefresh: () => void;
}

export function WatchStatusCard({ status, onConfigure, onRefresh }: WatchStatusCardProps) {
  const [loading, setLoading] = useState<"starting" | "stopping" | null>(null);
  const [autostartSaving, setAutostartSaving] = useState(false);
  const runtimeState = status?.state ?? "stopped";
  const isRunning = runtimeState === "running";
  const isFailed = runtimeState === "failed";
  const autostartEnabled = (status?.watch_autostart ?? "").toLowerCase() === "true";
  const interval = status?.interval_minutes ? parseInt(status.interval_minutes) : 5;
  const riskTolerance = status?.risk_tolerance || "—";
  const watchId = status?.watch_id || "—";
  const watchSessionId = status?.watch_session_id || "—";
  const cycleId = status?.cycle_id || "—";
  const totalErrors = Number(status?.total_errors || 0);
  const totalEscalated = Number(status?.total_escalated || 0);
  let lastOutcomeText = "";
  let missionState: "stable" | "attention" | "degraded" = "stable";
  let missionIcon = ShieldCheck;
  let missionLabel = "Stable";
  if (status?.last_outcome) {
    try {
      const parsed = JSON.parse(status.last_outcome) as { resolved?: boolean; escalated?: boolean; incident_count?: number };
      lastOutcomeText = `Last outcome: ${parsed.incident_count ?? 0} incidents, ${parsed.resolved ? "resolved" : parsed.escalated ? "escalated" : "monitoring"}`;
      if (parsed.escalated) {
        missionState = "degraded";
      } else if ((parsed.incident_count ?? 0) > 0 && !parsed.resolved) {
        missionState = "attention";
      }
    } catch {
      lastOutcomeText = "";
    }
  }
  if (totalErrors > 0 || totalEscalated > 0) missionState = "degraded";
  if (missionState === "attention") {
    missionLabel = "Attention needed";
    missionIcon = CircleAlert;
  } else if (missionState === "degraded") {
    missionLabel = "Degraded";
    missionIcon = Activity;
  }
  const MissionIcon = missionIcon;

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

  const handleAutostartToggle = async (enabled: boolean) => {
    setAutostartSaving(true);
    try {
      await apiPost("/api/watch/autostart", { enabled });
    } finally {
      setAutostartSaving(false);
      onRefresh();
    }
  };

  return (
    <Card className="relative h-full overflow-hidden border-border/70 bg-card/95">
      <CardContent className="relative space-y-4 pt-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radar className="h-4 w-4 text-primary" />
            <h2 className="text-base font-display font-semibold">Watch Control</h2>
          </div>
          <Badge
            variant={isRunning ? "default" : isFailed ? "destructive" : "secondary"}
            className="gap-1.5"
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                isRunning ? "bg-gauge-ok animate-pulse-dot" : isFailed ? "bg-destructive" : "bg-muted-foreground"
              }`}
            />
            {loading === "starting"
              ? "Starting…"
              : loading === "stopping"
                ? "Stopping…"
                : isRunning
                  ? "Running"
                  : isFailed
                    ? "Failed"
                    : "Stopped"}
          </Badge>
        </div>

        {isFailed && status?.last_error && (
          <div className="rounded-xl border border-destructive/60 bg-destructive/10 p-3 text-xs">
            <div className="mb-1 flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span className="font-semibold uppercase tracking-wide">Watch crashed</span>
            </div>
            <p className="font-mono text-destructive-foreground/80">{status.last_error}</p>
            <p className="mt-1 text-muted-foreground">Click Start Watch to try again.</p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 rounded-xl border border-border/60 bg-background/50 p-3 text-xs">
          <div>
            <p className="text-muted-foreground">Watch ID</p>
            <p className="font-mono">{watchId.slice(0, 12)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Cycle ID</p>
            <p className="font-mono">{cycleId === "—" ? "—" : cycleId.slice(0, 10)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Watch Session</p>
            <p className="font-mono">{watchSessionId === "—" ? "—" : watchSessionId.slice(0, 10)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Cycle cadence</p>
            <p>Every {interval} min</p>
          </div>
        </div>

        <div className="rounded-xl border border-border/60 bg-background/50 p-3">
          <div className="mb-2 flex items-center gap-2">
            <MissionIcon className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs uppercase tracking-wide text-muted-foreground">Operational health</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{missionLabel}</span>
            <Badge variant={missionState === "stable" ? "default" : "destructive"} className="text-[10px]">
              risk {riskTolerance}
            </Badge>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {lastOutcomeText || (isRunning ? "Collecting current watch telemetry and incident context." : "Watch is idle. Start to resume monitoring.")}
          </p>
        </div>

        <div className="flex flex-wrap justify-center gap-2">
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
          <Link href={`/watch-explorer?watch_id=${encodeURIComponent(status?.watch_id ?? "")}`}>
            <Button variant="secondary" size="sm">
              Open Watch Explorer
            </Button>
          </Link>
        </div>

        <div className="flex items-center justify-between rounded-xl border border-border/60 bg-background/50 p-3 text-xs">
          <div>
            <p className="font-medium">Auto-start on boot</p>
            <p className="text-muted-foreground">
              Resume watch when the container restarts, without a manual click.
            </p>
          </div>
          <Switch
            checked={autostartEnabled}
            disabled={autostartSaving}
            onCheckedChange={handleAutostartToggle}
          />
        </div>
      </CardContent>
    </Card>
  );
}
