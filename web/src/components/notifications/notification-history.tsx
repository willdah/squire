"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";
import type { EventInfo } from "@/lib/types";

interface NotificationHistoryProps {
  events: EventInfo[];
}

const categoryVariant: Record<string, "default" | "secondary" | "destructive"> = {
  "watch.alert": "default",
  "watch.blocked": "destructive",
  "watch.start": "secondary",
  "watch.stop": "secondary",
  error: "destructive",
};

export function NotificationHistory({ events }: NotificationHistoryProps) {
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
        {events.map((event, i) => (
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
  );
}
