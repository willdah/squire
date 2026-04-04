"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api";
import { AlertTriangle } from "lucide-react";

const riskLabels: Record<number, string> = {
  1: "Info", 2: "Low", 3: "Moderate", 4: "High", 5: "Critical",
};

interface WatchApprovalCardProps {
  requestId: string;
  toolName: string;
  args: Record<string, unknown>;
  riskLevel: number;
  resolved?: boolean;
  resolvedStatus?: string;
}

export function WatchApprovalCard({
  requestId, toolName, args, riskLevel, resolved, resolvedStatus,
}: WatchApprovalCardProps) {
  const [countdown, setCountdown] = useState(60);
  const [responding, setResponding] = useState(false);

  useEffect(() => {
    if (resolved) return;
    const timer = setInterval(() => {
      setCountdown((c) => Math.max(0, c - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resolved]);

  const handleRespond = async (approved: boolean) => {
    setResponding(true);
    try {
      await apiPost(`/api/watch/approve/${requestId}`, { approved });
    } catch {
      // May already be resolved
    }
    setResponding(false);
  };

  if (resolved) {
    return (
      <div className="border rounded-lg p-3 my-2 bg-muted/50">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{toolName}</span>
          <Badge variant={resolvedStatus === "approved" ? "default" : "destructive"} className="text-xs">
            {resolvedStatus}
          </Badge>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-orange-500/50 rounded-lg p-3 my-2 bg-orange-500/5">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="h-4 w-4 text-orange-500" />
        <span className="font-medium text-sm">Approval Required</span>
        <Badge variant={riskLevel >= 4 ? "destructive" : "secondary"} className="text-xs">
          Risk {riskLevel} — {riskLabels[riskLevel]}
        </Badge>
        <span className="text-xs text-muted-foreground ml-auto">{countdown}s</span>
      </div>
      <div className="mb-2">
        <span className="text-sm text-yellow-500 font-mono">{toolName}</span>
      </div>
      <pre className="rounded bg-muted p-2 text-xs overflow-auto max-h-20 mb-3">
        {JSON.stringify(args, null, 2)}
      </pre>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => handleRespond(true)} disabled={responding || countdown === 0}>
          Approve
        </Button>
        <Button size="sm" variant="destructive" onClick={() => handleRespond(false)} disabled={responding}>
          Deny
        </Button>
      </div>
    </div>
  );
}
