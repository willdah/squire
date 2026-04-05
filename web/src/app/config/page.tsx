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
      <h1 className="text-2xl">Configuration</h1>
      <ConfigEditor config={config} onSaved={() => mutate()} />
    </div>
  );
}
