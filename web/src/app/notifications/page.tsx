"use client";

import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { NotificationHistory } from "@/components/notifications/notification-history";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Bell, Webhook, ShieldAlert, Eye } from "lucide-react";
import type { EventInfo, ConfigResponse } from "@/lib/types";

const NOTIFICATION_CATEGORIES = [
  "watch.alert",
  "watch.blocked",
  "watch.start",
  "watch.stop",
  "error",
];

export default function NotificationsPage() {
  const { data: allEvents } = useSWR(
    `/api/events?limit=200`,
    () => apiGet<EventInfo[]>(`/api/events?limit=200`),
    { refreshInterval: 15000 }
  );

  const { data: config } = useSWR("/api/config", () =>
    apiGet<ConfigResponse>("/api/config")
  );

  const notificationEvents = (allEvents ?? []).filter((e) =>
    NOTIFICATION_CATEGORIES.includes(e.category)
  );

  const webhookUrl =
    (config?.notifications as Record<string, unknown>)?.webhook_url as
      | string
      | undefined;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl">Notifications</h1>
        {notificationEvents.length > 0 && (
          <Badge variant="secondary">{notificationEvents.length}</Badge>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        Configure where Squire sends alerts and review recent notification history.
        Alert rules are managed conversationally — ask Squire to create or modify them.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Eye className="h-4 w-4" />
              Watch Mode Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Alerts fired during autonomous watch cycles, blocked tools, and watch start/stop events.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
              Risk Gate Denials
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Tool calls that exceeded the risk tolerance and were denied automatically.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Webhook className="h-4 w-4" />
              Webhook Destination
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs font-mono text-muted-foreground truncate">
              {webhookUrl || "Not configured"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Set <code className="text-xs">webhook_url</code> in{" "}
              <code className="text-xs">[notifications]</code> config.
            </p>
          </CardContent>
        </Card>
      </div>

      <Separator />

      <div className="flex items-center gap-3">
        <h2 className="text-lg">Recent Notifications</h2>
        <Bell className="h-4 w-4 text-muted-foreground" />
      </div>

      <NotificationHistory events={notificationEvents} />
    </div>
  );
}
