"use client";

import { HelpCircle, Wifi, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { HostInfo } from "@/lib/types";
import { formatRelative, getConnectivity } from "@/lib/time";

interface Props {
  host: HostInfo;
  iconOnly?: boolean;
}

export function ConnectivityBadge({ host, iconOnly = false }: Props) {
  const state = getConnectivity(host);
  const relative = formatRelative(host.snapshot?.checked_at);
  const title =
    state === "unknown" && !host.snapshot?.checked_at
      ? "Never checked"
      : `Checked ${relative}`;

  if (iconOnly) {
    const iconLabel =
      state === "reachable"
        ? "Reachable"
        : state === "unreachable"
          ? "Unreachable"
          : "Reachability unknown";
    const Icon = state === "reachable" ? Wifi : state === "unreachable" ? WifiOff : HelpCircle;
    const colorClass =
      state === "reachable"
        ? "text-green-500"
        : state === "unreachable"
          ? "text-destructive"
          : "text-muted-foreground";
    return (
      <span className="inline-flex" title={title} aria-label={iconLabel}>
        <Icon className={`h-3 w-3 ${colorClass}`} aria-hidden />
      </span>
    );
  }

  if (state === "reachable") {
    return (
      <Badge variant="secondary" className="gap-1" title={title}>
        <Wifi className="h-3 w-3 text-green-500" />
        Reachable
      </Badge>
    );
  }
  if (state === "unreachable") {
    return (
      <Badge variant="destructive" className="gap-1" title={title}>
        <WifiOff className="h-3 w-3" />
        Unreachable
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground" title={title}>
      <HelpCircle className="h-3 w-3" />
      Unknown
    </Badge>
  );
}
