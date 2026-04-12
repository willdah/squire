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
  const cycleCount = Number(status?.cycle || 0);
  const totalActions = Number(status?.total_actions || 0);
  const totalBlocked = Number(status?.total_blocked || 0);
  const totalResolved = Number(status?.total_resolved || 0);
  const totalEscalated = Number(status?.total_escalated || 0);
  const totalInputTokens = Number(status?.total_input_tokens || 0);
  const totalOutputTokens = Number(status?.total_output_tokens || 0);
  const totalTokens = Number(status?.total_tokens || 0);
  const pace = `${status?.interval_minutes || "5"}m`;

  const renderMetric = (label: string, value: string | number, mono = false) => (
    <div className="rounded-lg border border-border/60 bg-background/50 p-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={mono ? "font-mono text-xs truncate" : "text-sm font-semibold"}>{value}</p>
    </div>
  );

  return (
    <Card className="relative h-full overflow-hidden border-border/70 bg-card/95">
      <div className="pointer-events-none absolute inset-0 opacity-35 [background-image:radial-gradient(circle_at_100%_0%,oklch(0.78_0.12_45/.18),transparent_45%)]" />
      <CardContent className="relative space-y-4 pt-5">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-display font-semibold">Status</h2>
        </div>

        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Pace</p>
          <div className="grid grid-cols-3 gap-2">
            {renderMetric("Uptime", isRunning ? formatUptime(status?.started_at) : "—")}
            {renderMetric("Cycle count", cycleCount)}
            {renderMetric("Interval", pace)}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Events</p>
          <div className="grid grid-cols-4 gap-2">
            {renderMetric("Actions", totalActions)}
            {renderMetric("Blocked", totalBlocked)}
            {renderMetric("Resolved", totalResolved)}
            {renderMetric("Escalated", totalEscalated)}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Tokens</p>
          <div className="grid grid-cols-3 gap-2">
            {renderMetric("Input", totalInputTokens.toLocaleString())}
            {renderMetric("Output", totalOutputTokens.toLocaleString())}
            {renderMetric("Total", totalTokens.toLocaleString())}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
