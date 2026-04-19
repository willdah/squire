"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { WatchApprovalCard } from "@/components/watch/watch-approval-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { apiGet, apiPost } from "@/lib/api";
import type {
  WatchConfigResponse,
  WatchIncident,
  WatchKillSwitchResponse,
  WatchMetricsResponse,
  WatchModeResponse,
} from "@/lib/types";

function summarizeOutcome(outcome: Record<string, unknown>): string {
  const verification = String(outcome.verification ?? "").trim();
  const actions = String(outcome.actions ?? "").trim();
  const escalation = String(outcome.escalation ?? "").trim();
  if (verification) return verification;
  if (actions) return actions;
  if (escalation) return escalation;
  return "No structured outcome summary yet.";
}

function severityVariant(severity: string): "default" | "secondary" | "destructive" | "outline" {
  const normalized = severity.toLowerCase();
  if (normalized === "critical" || normalized === "high") return "destructive";
  if (normalized === "medium") return "default";
  if (normalized === "low") return "secondary";
  return "outline";
}

function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${(value / 60).toFixed(1)}m`;
  return `${(value / 3600).toFixed(1)}h`;
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function MetricTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border border-border/60 bg-card/60 px-3 py-2">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="font-mono text-base">{value}</span>
      {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

function MetricsStrip({ metrics }: { metrics: WatchMetricsResponse | undefined }) {
  const windowLabel = metrics ? `${metrics.window_hours}h` : "24h";
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      <MetricTile
        label="Auto-resolve rate"
        value={metrics ? formatPercent(metrics.auto_resolve_rate) : "—"}
        hint={metrics ? `${metrics.auto_resolved}/${metrics.total_resolved} over ${windowLabel}` : undefined}
      />
      <MetricTile label="Median MTTR" value={metrics ? formatSeconds(metrics.median_mttr_seconds) : "—"} hint={windowLabel} />
      <MetricTile
        label="Approval latency"
        value={metrics ? formatSeconds(metrics.median_approval_latency_seconds) : "—"}
        hint={windowLabel}
      />
      <MetricTile
        label="Rate-ceiling hits"
        value={metrics ? String(metrics.rate_limit_hits) : "—"}
        hint={windowLabel}
      />
    </div>
  );
}

function IncidentCard({
  incident,
  approvalTimeoutSeconds,
  onLifecycleChange,
}: {
  incident: WatchIncident;
  approvalTimeoutSeconds: number;
  onLifecycleChange: () => void;
}) {
  const handleLifecycle = async (action: "ack" | "snooze" | "resolve") => {
    const path = `/api/watch/incidents/${encodeURIComponent(incident.incident_key)}/${action}`;
    const body = action === "snooze" ? { duration_seconds: 3600 } : undefined;
    await apiPost(path, body);
    onLifecycleChange();
  };

  return (
    <Card className="border-border/60">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="font-mono text-sm">{incident.incident_key}</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={severityVariant(incident.severity)}>{incident.severity}</Badge>
            <Badge variant="outline">{incident.cycle_count} cycles</Badge>
            <Badge variant={incident.status === "resolved" ? "secondary" : "default"}>{incident.status}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="text-muted-foreground">
          First seen {new Date(incident.first_seen).toLocaleString()} · Last seen{" "}
          {new Date(incident.last_seen).toLocaleString()}
        </div>
        <p>{summarizeOutcome(incident.latest_outcome_json)}</p>
        {incident.pending_approval && (
          <WatchApprovalCard
            requestId={incident.pending_approval.request_id}
            toolName={incident.pending_approval.tool_name}
            args={incident.pending_approval.args}
            riskLevel={incident.pending_approval.risk_level}
            countdownSeconds={approvalTimeoutSeconds}
          />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => handleLifecycle("ack")}>
            Acknowledge
          </Button>
          <Button size="sm" variant="outline" onClick={() => handleLifecycle("snooze")}>
            Snooze 1h
          </Button>
          <Button size="sm" variant="outline" onClick={() => handleLifecycle("resolve")}>
            Resolve
          </Button>
          <Link
            className="ml-auto text-xs text-primary underline underline-offset-2"
            href={`/activity?watch_id=${encodeURIComponent(incident.watch_id ?? "")}`}
          >
            View raw activity
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

export default function IncidentsPage() {
  const [showResolved, setShowResolved] = useState(false);
  const [autonomyDialogOpen, setAutonomyDialogOpen] = useState(false);
  const [autonomyConfirmText, setAutonomyConfirmText] = useState("");
  const { data: incidents, mutate: mutateIncidents } = useSWR(
    "/api/watch/incidents",
    () => apiGet<WatchIncident[]>("/api/watch/incidents"),
    { refreshInterval: 10000 },
  );
  const { data: mode, mutate: mutateMode } = useSWR("/api/watch/mode", () =>
    apiGet<WatchModeResponse>("/api/watch/mode"),
  );
  const { data: config } = useSWR("/api/watch/config", () => apiGet<WatchConfigResponse>("/api/watch/config"));
  const { data: killSwitch, mutate: mutateKillSwitch } = useSWR(
    "/api/watch/kill-switch",
    () => apiGet<WatchKillSwitchResponse>("/api/watch/kill-switch"),
    { refreshInterval: 15000 },
  );
  const { data: metrics } = useSWR("/api/watch/metrics", () => apiGet<WatchMetricsResponse>("/api/watch/metrics"), {
    refreshInterval: 60000,
  });
  const { data: digest } = useSWR(
    "/api/watch/digest",
    () =>
      apiGet<{
        window_hours: number;
        total_tool_calls: number;
        tools_used: Record<string, number>;
      }>("/api/watch/digest"),
    { refreshInterval: 60000 },
  );

  const needsYou = useMemo(
    () =>
      (incidents ?? []).filter(
        (incident) =>
          Boolean(incident.pending_approval) || incident.status === "needs_you" || incident.status === "escalated",
      ),
    [incidents],
  );
  const active = useMemo(() => (incidents ?? []).filter((incident) => incident.status === "active"), [incidents]);
  const resolved = useMemo(() => (incidents ?? []).filter((incident) => incident.status === "resolved"), [incidents]);

  const modeValue = mode?.mode ?? "supervised";
  const approvalTimeoutSeconds = config?.approval_timeout_seconds ?? 300;
  const killActive = Boolean(killSwitch?.active);

  const handleModeToggle = (nextChecked: boolean) => {
    if (nextChecked) {
      setAutonomyConfirmText("");
      setAutonomyDialogOpen(true);
      return;
    }
    void (async () => {
      await apiPost("/api/watch/mode", { mode: "supervised" });
      await Promise.all([mutateMode(), mutateIncidents()]);
    })();
  };

  const confirmAutonomous = async () => {
    if (autonomyConfirmText.trim().toUpperCase() !== "AUTONOMOUS") return;
    await apiPost("/api/watch/mode", { mode: "autonomous" });
    setAutonomyDialogOpen(false);
    setAutonomyConfirmText("");
    await Promise.all([mutateMode(), mutateIncidents()]);
  };

  const handleKillSwitch = async (nextActive: boolean) => {
    if (nextActive) {
      const ok = window.confirm("Halt autonomy? The watch loop will skip cycles until you un-halt it.");
      if (!ok) return;
    }
    await apiPost("/api/watch/kill-switch", { active: nextActive });
    await mutateKillSwitch();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl">Incidents</h1>
          <p className="text-sm text-muted-foreground">
            Incident inbox for watch mode approvals, active triage, and recent resolutions.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-border/60 px-3 py-2">
            <span className="text-sm font-medium">{modeValue === "autonomous" ? "Autonomous" : "Supervised"}</span>
            <Switch checked={modeValue === "autonomous"} onCheckedChange={handleModeToggle} />
          </div>
          <Button
            size="sm"
            variant={killActive ? "default" : "destructive"}
            onClick={() => handleKillSwitch(!killActive)}
          >
            {killActive ? (
              <>
                <ShieldCheck className="mr-1 h-4 w-4" />
                Resume autonomy
              </>
            ) : (
              <>
                <ShieldAlert className="mr-1 h-4 w-4" />
                Halt autonomy
              </>
            )}
          </Button>
        </div>
      </div>

      {killActive ? (
        <Card className="border-destructive/60 bg-destructive/10">
          <CardContent className="pt-4 text-sm">
            <strong>Kill switch active.</strong> Watch cycles are being skipped until autonomy is resumed.
          </CardContent>
        </Card>
      ) : null}

      <MetricsStrip metrics={metrics} />

      {digest && digest.total_tool_calls > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Autonomous digest · last {digest.window_hours}h
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Squire took {digest.total_tool_calls} tool actions.{" "}
            {Object.entries(digest.tools_used)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 4)
              .map(([k, v]) => `${k}×${v}`)
              .join(", ")}
          </CardContent>
        </Card>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Needs you</h2>
        {needsYou.length === 0 ? (
          <Card>
            <CardContent className="pt-4 text-sm text-muted-foreground">
              No incidents currently require intervention.
            </CardContent>
          </Card>
        ) : (
          needsYou.map((incident) => (
            <IncidentCard
              key={incident.incident_key}
              incident={incident}
              approvalTimeoutSeconds={approvalTimeoutSeconds}
              onLifecycleChange={() => void mutateIncidents()}
            />
          ))
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Active</h2>
        {active.length === 0 ? (
          <Card>
            <CardContent className="pt-4 text-sm text-muted-foreground">No active incidents.</CardContent>
          </Card>
        ) : (
          active.map((incident) => (
            <IncidentCard
              key={incident.incident_key}
              incident={incident}
              approvalTimeoutSeconds={approvalTimeoutSeconds}
              onLifecycleChange={() => void mutateIncidents()}
            />
          ))
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recently resolved</h2>
          <Button variant="ghost" size="sm" onClick={() => setShowResolved((s) => !s)}>
            {showResolved ? "Hide" : "Show"}
          </Button>
        </div>
        {!showResolved ? (
          <Card>
            <CardContent className="pt-4 text-sm text-muted-foreground">Collapsed by default.</CardContent>
          </Card>
        ) : resolved.length === 0 ? (
          <Card>
            <CardContent className="pt-4 text-sm text-muted-foreground">No resolved incidents yet.</CardContent>
          </Card>
        ) : (
          resolved.map((incident) => (
            <IncidentCard
              key={incident.incident_key}
              incident={incident}
              approvalTimeoutSeconds={approvalTimeoutSeconds}
              onLifecycleChange={() => void mutateIncidents()}
            />
          ))
        )}
      </section>

      <Dialog open={autonomyDialogOpen} onOpenChange={setAutonomyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enable autonomous mode</DialogTitle>
            <DialogDescription>
              Squire will remediate without routine approval prompts. Denylists, rate ceilings, and the kill switch
              still apply. Type <code className="font-mono">AUTONOMOUS</code> to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={autonomyConfirmText}
            onChange={(event) => setAutonomyConfirmText(event.target.value)}
            placeholder="AUTONOMOUS"
            autoFocus
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAutonomyDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={confirmAutonomous}
              disabled={autonomyConfirmText.trim().toUpperCase() !== "AUTONOMOUS"}
            >
              Enable
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
