"use client";

import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";
import type { EventInfo } from "@/lib/types";

interface NotificationHistoryProps {
  events: EventInfo[];
}

const FILTER_OPTIONS = [
  "all",
  "watch.alert",
  "watch.blocked",
  "watch.start",
  "watch.stop",
  "error",
];

const categoryVariant: Record<string, "default" | "secondary" | "destructive"> = {
  "watch.alert": "default",
  "watch.blocked": "destructive",
  "watch.start": "secondary",
  "watch.stop": "secondary",
  error: "destructive",
};

export function NotificationHistory({ events }: NotificationHistoryProps) {
  const [category, setCategory] = useState("all");

  const filtered = category === "all"
    ? events
    : events.filter((e) => e.category === category);

  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
        <Bell className="h-8 w-8" />
        <p className="text-sm">No recent notifications</p>
        <p className="text-xs">
          Notifications appear here when watch mode fires alerts, risk gates deny tools, or approvals are requested.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Select value={category} onValueChange={(v) => setCategory(v ?? "all")}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FILTER_OPTIONS.map((c) => (
              <SelectItem key={c} value={c}>
                {c === "all" ? "All" : c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {filtered.length} event{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Summary</TableHead>
            <TableHead>Details</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.map((event, i) => (
            <TableRow key={event.id ?? i}>
              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                {event.timestamp.substring(0, 19)}
              </TableCell>
              <TableCell>
                <Badge variant={categoryVariant[event.category] ?? "secondary"}>
                  {event.category}
                </Badge>
              </TableCell>
              <TableCell className="font-medium">{event.summary}</TableCell>
              <TableCell className="text-xs text-muted-foreground max-w-[300px] truncate">
                {event.details}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
