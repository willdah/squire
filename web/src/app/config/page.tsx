"use client";

import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { ConfigEditor } from "@/components/config/config-editor";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConfigDetailResponse } from "@/lib/types";

function ConfigSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-10 w-full max-w-xl" />
      <Skeleton className="h-64 rounded-lg" />
    </div>
  );
}

export default function ConfigPage() {
  const { data: config, isLoading, mutate } = useSWR("/api/config", () =>
    apiGet<ConfigDetailResponse>("/api/config")
  );

  if (isLoading || !config) {
    return <ConfigSkeleton />;
  }

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="space-y-2">
        <h1 className="text-2xl">Configuration</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          In-memory settings update the running web process when you save. Use <strong>Save to disk</strong> on each tab
          to write <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">squire.toml</code> (when a path is
          known). Environment variables override TOML—see the banner above the tabs when any apply. Watch-only options
          need a running watch or restart to take effect there; database path and LLM secrets need a full process
          restart.
        </p>
      </div>
      <ConfigEditor config={config} onSaved={() => mutate()} />
    </div>
  );
}
