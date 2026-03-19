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

const riskColors: Record<number, string> = {
  1: "default",
  2: "default",
  3: "secondary",
  4: "destructive",
  5: "destructive",
};

export function ApprovalDialog({ request, onRespond }: ApprovalDialogProps) {
  if (!request) return null;

  return (
    <Dialog open={!!request} onOpenChange={() => onRespond(request.request_id, false)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            Tool Approval Required
            <Badge variant={riskColors[request.risk_level] as "default" | "secondary" | "destructive"}>
              Risk: {riskLabels[request.risk_level] || request.risk_level}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            Squire wants to execute a tool that requires your approval.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 min-w-0">
          <div>
            <span className="text-sm font-medium">Tool:</span>
            <span className="ml-2 font-mono text-sm">{request.tool_name}</span>
          </div>
          <div className="min-w-0">
            <span className="text-sm font-medium">Arguments:</span>
            <pre className="mt-1 rounded bg-muted p-2 text-xs overflow-auto max-h-40 whitespace-pre-wrap break-all">
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
