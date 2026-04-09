"use client";

import { useMemo } from "react";
import useSWR from "swr";

import { buildMentionData } from "@/lib/chat/mention-candidates";
import { apiGet } from "@/lib/api";
import type { HostInfo, SystemStatusResponse, ToolInfo } from "@/lib/types";

export function useChatAutocompleteData() {
  const { data: hosts } = useSWR("/api/hosts", () => apiGet<HostInfo[]>("/api/hosts"));
  const { data: systemStatus } = useSWR("/api/system/status", () =>
    apiGet<SystemStatusResponse>("/api/system/status")
  );
  const { data: tools } = useSWR("/api/tools", () => apiGet<ToolInfo[]>("/api/tools"));

  return useMemo(() => buildMentionData(hosts, systemStatus, tools), [hosts, systemStatus, tools]);
}
