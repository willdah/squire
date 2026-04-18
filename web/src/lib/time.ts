import type { HostInfo } from "./types";

export const STALE_MINUTES = 6;

export type Connectivity = "reachable" | "unreachable" | "unknown";

export function formatRelative(iso?: string | null, now: Date = new Date()): string {
  if (!iso) return "never";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "never";

  const diffSec = Math.max(0, Math.floor((now.getTime() - parsed.getTime()) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export function getConnectivity(host: HostInfo, now: Date = new Date()): Connectivity {
  const snap = host.snapshot;
  if (!snap || !snap.checked_at) return "unknown";

  const checked = new Date(snap.checked_at);
  if (Number.isNaN(checked.getTime())) return "unknown";

  const ageMinutes = (now.getTime() - checked.getTime()) / 60_000;
  if (ageMinutes > STALE_MINUTES) return "unknown";
  if (snap.error) return "unreachable";
  return "reachable";
}
