"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ConfigResponse } from "@/lib/types";

interface ConfigEditorProps {
  config: ConfigResponse;
}

function ConfigKeyValue({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="space-y-2">
      {Object.entries(data).map(([key, value]) => {
        const display =
          typeof value === "object" && value !== null
            ? JSON.stringify(value, null, 2)
            : String(value ?? "—");
        const isComplex = typeof value === "object" && value !== null;

        return (
          <div key={key} className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium text-muted-foreground">{key}</dt>
            <dd>
              {isComplex ? (
                <pre className="text-xs font-mono bg-muted rounded p-2 overflow-auto max-h-32">
                  {display}
                </pre>
              ) : (
                <span className="text-sm font-mono">{display}</span>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function ConfigSection({
  title,
  data,
}: {
  title: string;
  data: Record<string, unknown> | Record<string, unknown>[];
}) {
  const [showRaw, setShowRaw] = useState(false);
  const isArray = Array.isArray(data);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!isArray && !showRaw && (
          <ConfigKeyValue data={data as Record<string, unknown>} />
        )}
        {(isArray || showRaw) && (
          <pre className="text-xs bg-muted rounded p-4 overflow-auto max-h-96 font-mono">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
        {!isArray && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowRaw(!showRaw)}
            className="text-xs text-muted-foreground"
          >
            {showRaw ? (
              <><ChevronDown className="h-3 w-3 mr-1" /> Hide raw JSON</>
            ) : (
              <><ChevronRight className="h-3 w-3 mr-1" /> Show raw JSON</>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function ConfigEditor({ config }: ConfigEditorProps) {
  const sections = [
    { key: "app", label: "App", data: config.app },
    { key: "llm", label: "LLM", data: config.llm },
    { key: "database", label: "Database", data: config.database },
    { key: "guardrails", label: "Guardrails", data: config.guardrails },
    { key: "watch", label: "Watch", data: config.watch },
    { key: "notifications", label: "Notifications", data: config.notifications },
    { key: "hosts", label: "Hosts", data: config.hosts },
  ];

  return (
    <Tabs defaultValue="app">
      <TabsList className="flex flex-wrap">
        {sections.map((s) => (
          <TabsTrigger key={s.key} value={s.key}>
            {s.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {sections.map((s) => (
        <TabsContent key={s.key} value={s.key}>
          <ConfigSection title={s.label} data={s.data} />
        </TabsContent>
      ))}
    </Tabs>
  );
}
