"use client";

import { Suspense } from "react";
import { WatchExplorer } from "@/components/watch/investigation-workbench";

export default function WatchExplorerPage() {
  return (
    <div className="space-y-4 animate-fade-in-up">
      <div>
        <h1 className="text-2xl">Watch Explorer</h1>
        <p className="text-sm text-muted-foreground">
          Navigate watch runs, watch sessions, cycles, and generated reports with evidence-first drill-down.
        </p>
      </div>
      <Suspense fallback={<div className="text-sm text-muted-foreground">Loading watch explorer…</div>}>
        <WatchExplorer />
      </Suspense>
    </div>
  );
}
