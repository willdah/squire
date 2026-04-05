"use client";

import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { NotificationHistory } from "@/components/notifications/notification-history";
import { AlertRulesTab } from "@/components/notifications/alert-rules-tab";
import { ChannelsTab } from "@/components/notifications/channels-tab";
import type { EventInfo } from "@/lib/types";

const NOTIFICATION_CATEGORIES = [
  "watch.alert",
  "watch.blocked",
  "watch.start",
  "watch.stop",
  "error",
];

function NotificationsSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-10 w-full max-w-xl" />
      <Skeleton className="h-64 rounded-lg" />
    </div>
  );
}

export default function NotificationsPage() {
  const { data: allEvents, isLoading } = useSWR(
    `/api/events?limit=200`,
    () => apiGet<EventInfo[]>(`/api/events?limit=200`),
    { refreshInterval: 15000 }
  );

  if (isLoading) {
    return <NotificationsSkeleton />;
  }

  const events = (allEvents ?? []).filter((e) =>
    NOTIFICATION_CATEGORIES.includes(e.category)
  );

  return (
    <div className="space-y-6 animate-fade-in-up">
      <h1 className="text-2xl">Notifications</h1>

      <Tabs defaultValue="history">
        <TabsList className="flex flex-wrap">
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="rules">Alert Rules</TabsTrigger>
          <TabsTrigger value="channels">Channels</TabsTrigger>
        </TabsList>

        <TabsContent value="history">
          <NotificationHistory events={events} />
        </TabsContent>

        <TabsContent value="rules">
          <AlertRulesTab />
        </TabsContent>

        <TabsContent value="channels">
          <ChannelsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
