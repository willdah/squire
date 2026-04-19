"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { InsightList } from "@/components/insights/insight-list";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const CATEGORIES: {
  value: string;
  label: string;
  title: string;
  blurb: string;
}[] = [
  {
    value: "reliability",
    label: "Reliability",
    title: "Reliability Center",
    blurb: "MTTR trends, repeat incidents, unresolved aging, noisy hosts, and autonomous-action success rate.",
  },
  {
    value: "maintenance",
    label: "Maintenance",
    title: "Maintenance Planner",
    blurb: "Patch and upgrade proposals, backup freshness, restore-drill suggestions, and scheduled windows.",
  },
  {
    value: "security",
    label: "Security",
    title: "Security Guard",
    blurb: "Exposed services, risky config, key and privilege drift, and hardening recommendations.",
  },
  {
    value: "design",
    label: "Design",
    title: "Design Copilot",
    blurb:
      "Capacity trends, integration suggestions, backup-strategy evolution, and post-incident architecture hardening — Squire's growth engine.",
  },
];

function InsightsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeValue = searchParams.get("category") ?? "reliability";
  const isKnown = CATEGORIES.some((c) => c.value === activeValue);
  const value = isKnown ? activeValue : "reliability";

  const handleChange = (next: string | number | null) => {
    if (typeof next !== "string") return;
    const url = next === "reliability" ? "/insights" : `/insights?category=${encodeURIComponent(next)}`;
    router.replace(url, { scroll: false });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl">Insights</h1>
        <p className="text-sm text-muted-foreground">
          Proactive surfaces derived from telemetry and observation skills. Pick a lens below.
        </p>
      </div>
      <Tabs value={value} onValueChange={handleChange}>
        <TabsList>
          {CATEGORIES.map((cat) => (
            <TabsTrigger key={cat.value} value={cat.value}>
              {cat.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {CATEGORIES.map((cat) => (
          <TabsContent key={cat.value} value={cat.value} className="pt-4">
            <InsightList category={cat.value} title={cat.title} blurb={cat.blurb} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

export default function InsightsPage() {
  return (
    <Suspense fallback={null}>
      <InsightsPageInner />
    </Suspense>
  );
}
