"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ShieldAlert } from "lucide-react";
import type { WsApprovalRequest } from "@/lib/types";

interface ApprovalDialogProps {
  request: WsApprovalRequest | null;
  onRespond: (requestId: string, approved: boolean) => void;
}

const riskLabels: Record<number, string> = {
  1: "Info",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Critical",
};

const riskBadgeStyles: Record<number, string> = {
  1: "bg-green-500/15 text-green-700 dark:text-green-400",
  2: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  3: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  4: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  5: "bg-red-500/15 text-red-700 dark:text-red-400",
};

export function ApprovalDialog({ request, onRespond }: ApprovalDialogProps) {
  if (!request) return null;

  return (
    <Dialog open={!!request} onOpenChange={() => onRespond(request.request_id, false)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2.5 flex-wrap">
            <ShieldAlert className="h-4.5 w-4.5 text-primary" />
            Tool Approval Required
          </DialogTitle>
          <DialogDescription>
            Squire wants to execute a tool that requires your approval.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 min-w-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-muted-foreground">Tool</span>
            <span className="font-mono text-sm">{request.tool_name}</span>
            <Badge variant="outline" className={riskBadgeStyles[request.risk_level] ?? ""}>
              {riskLabels[request.risk_level] || `Risk ${request.risk_level}`}
            </Badge>
          </div>
          <div className="min-w-0">
            <span className="text-sm font-medium text-muted-foreground">Arguments</span>
            <pre className="mt-1.5 rounded-lg bg-muted/60 ring-1 ring-border/30 p-3 text-xs font-mono overflow-auto max-h-40 whitespace-pre-wrap break-all">
              {JSON.stringify(request.args, null, 2)}
            </pre>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onRespond(request.request_id, false)}
          >
            Deny
          </Button>
          <Button onClick={() => onRespond(request.request_id, true)}>
            Approve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
