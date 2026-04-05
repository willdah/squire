"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { EventTimeline } from "@/components/events/event-timeline";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { EventInfo } from "@/lib/types";

const CATEGORIES = [
  "all",
  "tool_call",
  "tool_result",
  "error",
  "watch.alert",
  "watch.blocked",
  "watch.start",
  "watch.stop",
];

export default function ActivityPage() {
  const [category, setCategory] = useState("all");
  const [limit, setLimit] = useState(100);

  const params = new URLSearchParams();
  if (category !== "all") params.set("category", category);
  params.set("limit", String(limit));

  const { data: events } = useSWR(
    `/api/events?${params.toString()}`,
    () => apiGet<EventInfo[]>(`/api/events?${params.toString()}`),
    { refreshInterval: 10000 }
  );

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl">Activity</h1>
        {events && (
          <Badge variant="secondary">{events.length}</Badge>
        )}
      </div>

      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={category} onValueChange={(v) => setCategory(v ?? "all")}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="limit">Limit</Label>
              <Input
                id="limit"
                type="number"
                className="w-24"
                min={1}
                max={1000}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <EventTimeline events={events ?? []} />
    </div>
  );
}
