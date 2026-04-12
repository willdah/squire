"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiGet, apiDelete } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Trash2, MessageSquare, History, Eraser } from "lucide-react";
import type { SessionInfo } from "@/lib/types";

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function SessionsPage() {
  const { data: sessions, mutate } = useSWR("/api/sessions", () =>
    apiGet<SessionInfo[]>("/api/sessions")
  );

  const handleDelete = async (sessionId: string) => {
    if (!confirm("Delete this session and all its messages?")) return;
    await apiDelete(`/api/sessions/${sessionId}`);
    mutate();
  };

  const handleClearAll = async () => {
    if (!confirm("Delete ALL sessions and their messages? This cannot be undone.")) return;
    await apiDelete("/api/sessions");
    mutate();
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl">Session History</h1>
        {sessions && sessions.length > 0 && (
          <Button variant="outline" size="sm" onClick={handleClearAll}>
            <Eraser className="h-4 w-4 mr-2" />
            Clear All
          </Button>
        )}
      </div>

      {!sessions || sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
          <History className="h-8 w-8" />
          <p className="text-sm">No sessions found</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Session ID</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Last Active</TableHead>
              <TableHead>Preview</TableHead>
              <TableHead className="text-right">Input Tokens</TableHead>
              <TableHead className="text-right">Output Tokens</TableHead>
              <TableHead className="text-right">Total Tokens</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.map((s) => (
              <TableRow key={s.session_id} className="hover:bg-muted/50">
                <TableCell className="font-mono text-xs">
                  {s.session_id.substring(0, 12)}...
                </TableCell>
                <TableCell className="text-sm" title={s.created_at}>
                  {relativeTime(s.created_at)}
                </TableCell>
                <TableCell className="text-sm" title={s.last_active}>
                  {relativeTime(s.last_active)}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                  {s.preview || "-"}
                </TableCell>
                <TableCell className="text-sm text-right">{s.input_tokens.toLocaleString()}</TableCell>
                <TableCell className="text-sm text-right">{s.output_tokens.toLocaleString()}</TableCell>
                <TableCell className="text-sm text-right">{s.total_tokens.toLocaleString()}</TableCell>
                <TableCell className="flex gap-1">
                  <Link href={`/chat?session=${s.session_id}`}>
                    <Button variant="ghost" size="icon" title="Resume">
                      <MessageSquare className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete"
                    onClick={() => handleDelete(s.session_id)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
