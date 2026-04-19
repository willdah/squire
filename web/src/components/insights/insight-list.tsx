"use client";

import useSWR from "swr";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/api";

export interface Insight {
  id: number;
  category: string;
  host: string | null;
  summary: string;
  detail: string | null;
  severity: string | null;
  created_at: string;
  actioned_at: string | null;
  snoozed_until: string | null;
}

export function InsightList({
  category,
  title,
  blurb,
}: {
  category: string;
  title?: string;
  blurb?: string;
}) {
  const { data } = useSWR(
    `/api/watch/insights?category=${encodeURIComponent(category)}`,
    () => apiGet<{ items: Insight[] }>(`/api/watch/insights?category=${encodeURIComponent(category)}`),
    { refreshInterval: 60000 },
  );

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      {title || blurb ? (
        <div>
          {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
          {blurb ? <p className="text-sm text-muted-foreground">{blurb}</p> : null}
        </div>
      ) : null}
      {items.length === 0 ? (
        <Card>
          <CardContent className="pt-4 text-sm text-muted-foreground">
            No {category} insights yet. Squire will populate this surface as sweeps run and skills
            produce observations.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((insight) => (
            <Card key={insight.id} className="border-border/60">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">{insight.summary}</CardTitle>
                  <div className="flex items-center gap-2">
                    {insight.severity ? <Badge>{insight.severity}</Badge> : null}
                    {insight.host ? <Badge variant="outline">{insight.host}</Badge> : null}
                  </div>
                </div>
              </CardHeader>
              {insight.detail ? (
                <CardContent className="text-sm text-muted-foreground">{insight.detail}</CardContent>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
