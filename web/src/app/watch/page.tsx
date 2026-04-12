"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WatchStatusCard } from "@/components/watch/watch-status-card";
import { WatchStatsCard } from "@/components/watch/watch-stats-card";
import { WatchLiveStream } from "@/components/watch/watch-live-stream";
import { WatchCycleHistory } from "@/components/watch/watch-cycle-history";
import { WatchConfigDrawer } from "@/components/watch/watch-config-drawer";
import type { WatchStatus } from "@/lib/types";

export default function WatchPage() {
  const [configOpen, setConfigOpen] = useState(false);

  const { data: status, mutate } = useSWR(
    "/api/watch/status",
    () => apiGet<WatchStatus>("/api/watch/status"),
    { refreshInterval: (latestData?: WatchStatus) => (latestData?.status === "running" ? 2000 : 5000) }
  );

  const isRunning = status?.status === "running";

  return (
    <div className="space-y-6 animate-fade-in-up">
      <h1 className="text-2xl">Watch</h1>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <div className="xl:col-span-2">
          <WatchStatusCard
            status={status ?? null}
            onConfigure={() => setConfigOpen(true)}
            onRefresh={() => mutate()}
          />
        </div>
        <div className="xl:col-span-3">
          <WatchStatsCard status={status ?? null} />
        </div>
      </div>

      <Tabs defaultValue="stream">
        <TabsList>
          <TabsTrigger value="stream">Live Stream</TabsTrigger>
          <TabsTrigger value="history">Cycle History</TabsTrigger>
        </TabsList>
        <TabsContent value="stream" className="mt-4">
          <WatchLiveStream enabled={isRunning} />
        </TabsContent>
        <TabsContent value="history" className="mt-4">
          <WatchCycleHistory watchId={status?.watch_id} watchSessionId={status?.watch_session_id} />
        </TabsContent>
      </Tabs>

      <WatchConfigDrawer open={configOpen} onOpenChange={setConfigOpen} />
    </div>
  );
}
