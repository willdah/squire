"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { apiDelete, apiGet } from "@/lib/api";
import type {
  WatchCycleSummary,
  WatchEvent,
  WatchReportInfo,
  WatchRunSummary,
  WatchSessionSummary,
  WatchTimelineItem,
} from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Eraser, History } from "lucide-react";

function parseJson(value: string | null | undefined): Record<string, unknown> {
  if (!value) return {};
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}

function useWorkbenchQuery() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const watchId = searchParams.get("watch_id");
  const watchSessionId = searchParams.get("watch_session_id");
  const chatSessionId = searchParams.get("chat_session_id");
  const cycleId = searchParams.get("cycle_id");
  const reportId = searchParams.get("report_id");
  const view = searchParams.get("view") || "hierarchy";

  const setQuery = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (!value) next.delete(key);
      else next.set(key, value);
    }
    router.replace(`${pathname}?${next.toString()}`);
  };

  return { watchId, watchSessionId, chatSessionId, cycleId, reportId, view, setQuery };
}

export function WatchExplorer() {
  const { watchId, watchSessionId, chatSessionId, cycleId, reportId, view, setQuery } = useWorkbenchQuery();
  const [activeDetailTab, setActiveDetailTab] = useState("summary");
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const { mutate } = useSWRConfig();
  const sessionLookupKey = chatSessionId ? `/api/watch/sessions/by-adk/${encodeURIComponent(chatSessionId)}` : null;
  const { data: lookedUpSession } = useSWR(
    sessionLookupKey,
    (key: string) => apiGet<WatchSessionSummary>(key),
    { revalidateOnFocus: false },
  );
  const { data: runs } = useSWR("/api/watch/runs?per_page=50", () => apiGet<WatchRunSummary[]>("/api/watch/runs?per_page=50"), {
    refreshInterval: 5000,
  });
  const selectedWatchId = watchId || lookedUpSession?.watch_id || runs?.[0]?.watch_id || null;
  const sessionsKey = selectedWatchId
    ? `/api/watch/runs/${encodeURIComponent(selectedWatchId)}/sessions?per_page=200`
    : null;
  const { data: sessions } = useSWR(
    sessionsKey,
    (key: string) => apiGet<WatchSessionSummary[]>(key),
    { refreshInterval: 5000 },
  );
  const reportedSessions = useMemo(
    () => (sessions ?? []).filter((session) => Boolean(session.session_report_id)),
    [sessions],
  );
  const selectedWatchSessionId =
    watchSessionId
    || lookedUpSession?.watch_session_id
    || reportedSessions[0]?.watch_session_id
    || sessions?.[0]?.watch_session_id
    || null;
  const cyclesKey =
    selectedWatchId && selectedWatchSessionId
      ? `/api/watch/runs/${encodeURIComponent(selectedWatchId)}/sessions/${encodeURIComponent(selectedWatchSessionId)}/cycles?per_page=500`
      : null;
  const { data: cycles } = useSWR(cyclesKey, (key: string) => apiGet<WatchCycleSummary[]>(key), {
    refreshInterval: 5000,
  });
  const selectedCycleId = cycleId || cycles?.[0]?.cycle_id || null;
  const selectedCycle = useMemo(
    () => (selectedCycleId ? (cycles ?? []).find((cycle) => cycle.cycle_id === selectedCycleId) ?? null : null),
    [cycles, selectedCycleId],
  );
  const reportsQuery = new URLSearchParams({ per_page: "100" });
  if (selectedWatchId) reportsQuery.set("watch_id", selectedWatchId);
  const reportsKey = `/api/watch/reports?${reportsQuery.toString()}`;
  const { data: reports } = useSWR(reportsKey, () => apiGet<WatchReportInfo[]>(reportsKey), {
    refreshInterval: 5000,
  });
  const reportsForWatch = useMemo(
    () => (reports ?? []).filter((report) => report.watch_id === selectedWatchId),
    [reports, selectedWatchId],
  );
  const watchReport = useMemo(
    () =>
      reportsForWatch.find((report) => report.report_type === "watch")
      ?? reportsForWatch.find((report) => !report.watch_session_id),
    [reportsForWatch],
  );
  const sessionReport = useMemo(
    () =>
      reportsForWatch.find(
        (report) => report.watch_session_id === selectedWatchSessionId && report.report_type === "session",
      ),
    [reportsForWatch, selectedWatchSessionId],
  );
  const selectedReport = useMemo(() => {
    if (reportId) return reportsForWatch.find((report) => report.report_id === reportId) ?? null;
    return sessionReport ?? watchReport ?? reportsForWatch[0] ?? null;
  }, [reportId, reportsForWatch, sessionReport, watchReport]);
  const detailPayload = parseJson(selectedReport?.report_json);
  const cycleEventsKey =
    selectedCycleId && selectedWatchId
      ? `/api/watch/cycles/${encodeURIComponent(selectedCycleId)}?watch_id=${encodeURIComponent(selectedWatchId)}`
      : null;
  const { data: cycleEvents } = useSWR(cycleEventsKey, (key: string) => apiGet<WatchEvent[]>(key), {
    refreshInterval: 5000,
  });

  useEffect(() => {
    if (!selectedWatchId || !runs?.length || watchId) return;
    setQuery({ watch_id: selectedWatchId });
  }, [runs, selectedWatchId, setQuery, watchId]);

  useEffect(() => {
    if (!chatSessionId || !lookedUpSession) return;
    if (watchId && watchSessionId) return;
    setQuery({
      watch_id: lookedUpSession.watch_id,
      watch_session_id: lookedUpSession.watch_session_id,
    });
  }, [chatSessionId, lookedUpSession, setQuery, watchId, watchSessionId]);

  useEffect(() => {
    if (!selectedWatchSessionId || !sessions?.length || watchSessionId) return;
    setQuery({ watch_session_id: selectedWatchSessionId });
  }, [selectedWatchSessionId, sessions, setQuery, watchSessionId]);

  useEffect(() => {
    if (!selectedCycleId || !cycles?.length || cycleId) return;
    setQuery({ cycle_id: selectedCycleId });
  }, [cycleId, cycles, selectedCycleId, setQuery]);

  useEffect(() => {
    if (!selectedReport?.report_id || reportId) return;
    setQuery({ report_id: selectedReport.report_id });
  }, [reportId, selectedReport, setQuery]);

  const timelineQuery = new URLSearchParams();
  if (selectedWatchId) timelineQuery.set("watch_id", selectedWatchId);
  if (selectedWatchSessionId) timelineQuery.set("watch_session_id", selectedWatchSessionId);
  timelineQuery.set("per_page", "40");
  const timelineKey = `/api/watch/timeline?${timelineQuery.toString()}`;
  const { data: timeline } = useSWR(
    view === "timeline" ? timelineKey : null,
    (key: string) => apiGet<WatchTimelineItem[]>(key),
    { refreshInterval: 5000 },
  );

  const clearWatchHistory = async () => {
    if (isClearingHistory) return;
    if (!confirm("Clear all watch history? This removes runs, sessions, cycles, reports, and watch events.")) return;
    setIsClearingHistory(true);
    try {
      await apiDelete("/api/watch/cycles");
      setQuery({
        watch_id: null,
        watch_session_id: null,
        cycle_id: null,
        report_id: null,
        chat_session_id: null,
      });
      await mutate((key) => typeof key === "string" && key.startsWith("/api/watch/"), undefined, {
        revalidate: true,
      });
    } finally {
      setIsClearingHistory(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[260px_1fr_1.2fr]">
      <Card className="min-w-0 xl:h-[calc(100vh-11rem)]">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">Watch Runs</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={clearWatchHistory}
              disabled={isClearingHistory}
            >
              <Eraser className="mr-2 h-4 w-4" />
              {isClearingHistory ? "Clearing..." : "Clear"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <Tabs value={view} onValueChange={(value) => setQuery({ view: value })}>
            <TabsList className="w-full">
              <TabsTrigger value="hierarchy" className="flex-1">Hierarchy</TabsTrigger>
              <TabsTrigger value="timeline" className="flex-1">Timeline</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="pt-2">
            <label className="text-xs text-muted-foreground">Filter watch ID</label>
            <Input
              className="mt-1"
              value={watchId ?? ""}
              onChange={(e) => setQuery({ watch_id: e.target.value || null, watch_session_id: null, cycle_id: null })}
              placeholder="watch_ab12..."
            />
          </div>
          <div className="space-y-2 overflow-auto pt-2 xl:max-h-[calc(100vh-20rem)]">
            {(runs ?? []).map((run) => (
              <button
                key={run.watch_id}
                type="button"
                onClick={() => setQuery({ watch_id: run.watch_id, watch_session_id: null, cycle_id: null })}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${
                  run.watch_id === selectedWatchId ? "border-primary/50 bg-accent/30" : "hover:bg-accent/20"
                }`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant={run.status === "running" ? "default" : "secondary"}>{run.status}</Badge>
                  <span className="ml-auto text-xs text-muted-foreground">{run.started_at.slice(0, 19)}</span>
                </div>
                <p className="font-mono text-xs">{run.watch_id}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {run.session_count} sessions · {run.cycle_count} cycles · {run.report_count} reports
                </p>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="min-w-0 xl:h-[calc(100vh-11rem)]">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">
              {view === "timeline" ? "Timeline View" : "Sessions & Cycles"}
            </CardTitle>
            {selectedWatchId && (
              <Link href={`/sessions?watch_id=${encodeURIComponent(selectedWatchId)}`}>
                <Button variant="outline" size="sm">
                  <History className="mr-2 h-4 w-4" />
                  Open in Sessions
                </Button>
              </Link>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-2 overflow-auto xl:max-h-[calc(100vh-15rem)]">
          {view === "timeline" &&
            (timeline ?? []).map((item) => {
              const payload = parseJson(item.payload_json);
              const summary =
                item.kind === "report"
                  ? String((payload.executive_summary as string) ?? (payload.run_summary as string) ?? "Report")
                  : `Cycle ${item.cycle ?? "?"} ${item.status ?? "unknown"}`;
              return (
                <button
                  type="button"
                  key={`${item.kind}-${item.item_id}`}
                  className="w-full rounded-lg border bg-card p-3 text-left hover:bg-accent/40"
                  onClick={() =>
                    {
                      const cycleTarget =
                        item.kind === "cycle" ? (item.item_id || (item.cycle ? String(item.cycle) : null)) : null;
                      const reportTarget = item.kind === "report" ? item.item_id : null;
                      setQuery({
                        watch_id: item.watch_id ?? null,
                        watch_session_id: item.watch_session_id ?? null,
                        cycle_id: cycleTarget,
                        report_id: reportTarget,
                      });
                      setActiveDetailTab(item.kind === "cycle" ? "evidence" : "summary");
                    }
                  }
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <Badge variant={item.status === "error" ? "destructive" : "secondary"}>{item.kind}</Badge>
                    {item.status && <Badge variant={item.status === "ok" ? "default" : "destructive"}>{item.status}</Badge>}
                    <span className="ml-auto text-xs text-muted-foreground">{item.created_at.slice(0, 19)}</span>
                  </div>
                  <p className="text-sm">{summary}</p>
                </button>
              );
            })}

          {view === "hierarchy" &&
            (sessions ?? []).map((session) => (
              <div key={session.watch_session_id} className="rounded-lg border bg-card/40 p-3">
                <button
                  type="button"
                  onClick={() => setQuery({ watch_session_id: session.watch_session_id, cycle_id: null, report_id: null })}
                  className={`mb-2 w-full rounded-md p-2 text-left ${
                    session.watch_session_id === selectedWatchSessionId ? "bg-accent/30" : "hover:bg-accent/20"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <Badge variant={session.status === "running" ? "default" : "secondary"}>watch session</Badge>
                    <span className="ml-auto text-xs text-muted-foreground">{session.started_at.slice(0, 19)}</span>
                  </div>
                  <p className="font-mono text-xs">{session.watch_session_id}</p>
                  <p className="text-xs text-muted-foreground">{session.cycle_count} cycles</p>
                </button>
                {session.watch_session_id === selectedWatchSessionId && (
                  <div className="space-y-2 pl-2">
                    {(cycles ?? []).map((cycle) => (
                      <button
                        type="button"
                        key={cycle.cycle_id}
                        className={`w-full rounded-md border p-2 text-left text-sm ${
                          cycle.cycle_id === selectedCycleId ? "border-primary/50 bg-accent/20" : "hover:bg-accent/10"
                        }`}
                        onClick={() => {
                          setQuery({ cycle_id: cycle.cycle_id });
                          setActiveDetailTab("evidence");
                        }}
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <Badge variant={cycle.status === "ok" ? "default" : "destructive"}>cycle {cycle.cycle_number}</Badge>
                          <span className="ml-auto text-xs text-muted-foreground">{cycle.started_at.slice(0, 19)}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          incidents {cycle.incident_count} · tools {cycle.tool_count} · tokens {cycle.total_tokens ?? "—"}
                        </p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
        </CardContent>
      </Card>

      <Card className="min-w-0 xl:h-[calc(100vh-11rem)]">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Report Detail</CardTitle>
        </CardHeader>
        <CardContent className="min-w-0 overflow-auto xl:max-h-[calc(100vh-15rem)]">
          <div className="mb-3 space-y-2">
            {selectedCycle && (
              <div className="rounded-md border border-primary/30 bg-accent/10 p-2 text-xs">
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant={selectedCycle.status === "ok" ? "default" : "destructive"}>
                    Cycle {selectedCycle.cycle_number}
                  </Badge>
                  <span className="text-muted-foreground">{selectedCycle.started_at.slice(0, 19)}</span>
                </div>
                <p className="text-muted-foreground">
                  incidents {selectedCycle.incident_count} · tools {selectedCycle.tool_count} · tokens{" "}
                  {selectedCycle.total_tokens ?? "—"}
                </p>
              </div>
            )}
            {watchReport && (
              <button
                type="button"
                className={`w-full rounded-md border p-2 text-left ${
                  selectedReport?.report_id === watchReport.report_id ? "border-primary/50 bg-accent/20" : "hover:bg-accent/10"
                }`}
                onClick={() => setQuery({ report_id: watchReport.report_id })}
              >
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Watch Report</Badge>
                  <Badge variant={watchReport.status === "ok" ? "default" : "destructive"}>{watchReport.status}</Badge>
                </div>
                <p className="mt-1 text-sm">{watchReport.title}</p>
              </button>
            )}
            {sessionReport && (
              <button
                type="button"
                className={`w-full rounded-md border p-2 text-left ${
                  selectedReport?.report_id === sessionReport.report_id
                    ? "border-primary/50 bg-accent/20"
                    : "hover:bg-accent/10"
                }`}
                onClick={() => setQuery({ report_id: sessionReport.report_id })}
              >
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Session Report</Badge>
                  <Badge variant={sessionReport.status === "ok" ? "default" : "destructive"}>{sessionReport.status}</Badge>
                </div>
                <p className="mt-1 text-sm">{sessionReport.title}</p>
              </button>
            )}
          </div>
          {!selectedReport && !selectedCycleId ? (
            <p className="text-sm text-muted-foreground">Select a watch run/session/cycle to inspect details.</p>
          ) : (
            <Tabs value={activeDetailTab} onValueChange={setActiveDetailTab}>
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="evidence">Evidence</TabsTrigger>
                <TabsTrigger value="memory">Memory</TabsTrigger>
                <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
              </TabsList>
              <TabsContent value="summary" className="space-y-3">
                {selectedReport ? (
                  <>
                    <h3 className="font-semibold">{selectedReport.title}</h3>
                    <p className="text-sm text-muted-foreground">{selectedReport.digest}</p>
                    <div className="space-y-2 text-sm">
                      <p>
                        <strong>Executive Summary:</strong>{" "}
                        {String(detailPayload.executive_summary ?? detailPayload.run_summary ?? "—")}
                      </p>
                      <p>
                        <strong>Incidents:</strong> {String(detailPayload.incidents_seen ?? detailPayload.session_rollup ?? "—")}
                      </p>
                      <p>
                        <strong>Actions Taken:</strong> {String(detailPayload.actions_taken ?? detailPayload.major_actions ?? "—")}
                      </p>
                      <p>
                        <strong>Actions Avoided:</strong> {String(detailPayload.blocked_or_denied_actions ?? "—")}
                      </p>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No report selected for this scope yet. Open Evidence to inspect cycle-level events.
                  </p>
                )}
              </TabsContent>
              <TabsContent value="evidence">
                {selectedCycleId ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">Cycle evidence ({selectedCycleId})</p>
                    {!cycleEvents?.length ? (
                      <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
                        No cycle events captured for this cycle yet.
                      </p>
                    ) : (
                      (cycleEvents ?? []).slice(0, 15).map((event) => (
                        <pre key={event.id} className="overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-muted p-2 text-xs">
                          [{event.type}] {event.content?.slice(0, 200)}
                        </pre>
                      ))
                    )}
                  </div>
                ) : (
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">
                    {String(detailPayload.verification_results ?? detailPayload.error_and_timeout_analysis ?? "No evidence")}
                  </pre>
                )}
              </TabsContent>
              <TabsContent value="memory">
                {selectedReport ? (
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">
                    {String(detailPayload.learning_memory_rollup ?? detailPayload.open_risks ?? "No memory updates")}
                  </pre>
                ) : (
                  <p className="text-sm text-muted-foreground">No report memory available for this selection.</p>
                )}
              </TabsContent>
              <TabsContent value="recommendations">
                {selectedReport ? (
                  <p className="text-sm">
                    {String(detailPayload.recommended_follow_ups ?? detailPayload.next_watch_recommendations ?? "—")}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">No recommendations available until a report is selected.</p>
                )}
              </TabsContent>
            </Tabs>
          )}
          <div className="mt-4 flex gap-2">
            {selectedWatchId && (
              <Link href={`/watch`}>
                <Button size="sm" variant="outline">Open Watch</Button>
              </Link>
            )}
            {selectedWatchSessionId && (
              <Link href={`/sessions`}>
                <Button size="sm" variant="outline">Open Sessions</Button>
              </Link>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
