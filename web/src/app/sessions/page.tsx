"use client";

import { Suspense } from "react";
import useSWR from "swr";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import { Badge } from "@/components/ui/badge";
import { Trash2, MessageSquare, History, Eraser, FileSearch, X } from "lucide-react";
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
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading sessions...</div>}>
      <SessionsPageInner />
    </Suspense>
  );
}

function SessionsPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const watchId = searchParams.get("watch_id");

  const fetchKey = watchId
    ? `/api/sessions?watch_id=${encodeURIComponent(watchId)}`
    : "/api/sessions";

  const { data: sessions, mutate } = useSWR(fetchKey, () => apiGet<SessionInfo[]>(fetchKey));

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

  const clearWatchFilter = () => {
    router.replace("/sessions");
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

      {watchId && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
          <span className="text-muted-foreground">Filtered by watch run:</span>
          <Badge variant="secondary" className="font-mono text-xs">
            {watchId}
          </Badge>
          <Button variant="ghost" size="sm" className="ml-auto h-7" onClick={clearWatchFilter}>
            <X className="mr-1 h-3.5 w-3.5" />
            Clear filter
          </Button>
        </div>
      )}

      {!sessions || sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
          <History className="h-8 w-8" />
          <p className="text-sm">
            {watchId ? "No sessions found for this watch run" : "No sessions found"}
          </p>
          {watchId && (
            <Link
              href={`/watch-explorer?watch_id=${encodeURIComponent(watchId)}`}
              className="text-xs text-primary underline-offset-4 hover:underline"
            >
              Back to Watch Explorer
            </Link>
          )}
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
                  <Link href={`/watch-explorer?chat_session_id=${encodeURIComponent(s.session_id)}`}>
                    <Button variant="ghost" size="icon" title="Investigate in watch explorer">
                      <FileSearch className="h-4 w-4" />
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
