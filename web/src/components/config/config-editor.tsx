"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ConfigDetailResponse } from "@/lib/types";
import { ChannelsTab } from "@/components/notifications/channels-tab";
import { AppConfigForm } from "./app-config-form";
import { LLMConfigForm } from "./llm-config-form";
import { WatchConfigForm } from "./watch-config-form";
import { GuardrailsConfigForm } from "./guardrails-config-form";
import { SkillsConfigForm } from "./skills-config-form";
import { ConfigEnvOverrideNotice, ConfigIntro } from "./config-help";

interface ConfigEditorProps {
  config: ConfigDetailResponse;
  onSaved: () => void;
}

function ConfigKeyValue({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="space-y-2">
      {Object.entries(data).map(([key, value]) => {
        const display =
          typeof value === "object" && value !== null
            ? JSON.stringify(value, null, 2)
            : String(value ?? "\u2014");
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

function ReadOnlySection({
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

export function ConfigEditor({ config, onSaved }: ConfigEditorProps) {
  return (
    <div className="space-y-4">
      <ConfigEnvOverrideNotice config={config} />
      <Tabs defaultValue="app">
      <TabsList className="flex flex-wrap">
        <TabsTrigger value="app">App</TabsTrigger>
        <TabsTrigger value="llm">LLM</TabsTrigger>
        <TabsTrigger value="database">Database</TabsTrigger>
        <TabsTrigger value="notifications">Notifications</TabsTrigger>
        <TabsTrigger value="guardrails">Guardrails</TabsTrigger>
        <TabsTrigger value="watch">Watch</TabsTrigger>
        <TabsTrigger value="skills">Skills</TabsTrigger>
        <TabsTrigger value="hosts">Hosts</TabsTrigger>
      </TabsList>

      <TabsContent value="app">
        <AppConfigForm
          values={config.app.values}
          envOverrides={config.app.env_overrides}
          tomlPath={config.toml_path}
          onSaved={onSaved}
        />
      </TabsContent>

      <TabsContent value="llm">
        <LLMConfigForm
          values={config.llm.values}
          envOverrides={config.llm.env_overrides}
          tomlPath={config.toml_path}
          onSaved={onSaved}
        />
      </TabsContent>

      <TabsContent value="database">
        <div className="space-y-4">
          <div className="rounded-md border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Database settings are read-only here</p>
            <p className="mt-1 text-xs leading-relaxed">
              The SQLite path (<code className="font-mono">SQUIRE_DB_PATH</code> /{" "}
              <code className="font-mono">[db].path</code>) and snapshot interval are fixed when the web process
              starts. Changing them requires updating <code className="font-mono">squire.toml</code> or environment
              variables and restarting Squire. Provider API keys for LLMs are configured through LiteLLM environment
              variables, not through this UI.
            </p>
          </div>
          <ReadOnlySection title="Database" data={config.database.values} />
        </div>
      </TabsContent>

      <TabsContent value="notifications">
        <div className="space-y-4">
          <ConfigIntro title="What this controls">
            <p>
              Turn channels on or off, add webhooks, and configure email. Saving updates the running server immediately
              and rebuilds notification delivery. Use <strong>Save</strong> on this page to persist to{" "}
              <code>squire.toml</code> when a config file is present.
            </p>
          </ConfigIntro>
          <ChannelsTab />
        </div>
      </TabsContent>

      <TabsContent value="guardrails">
        <GuardrailsConfigForm
          values={config.guardrails.values}
          envOverrides={config.guardrails.env_overrides}
          tomlPath={config.toml_path}
          onSaved={onSaved}
        />
      </TabsContent>

      <TabsContent value="watch">
        <WatchConfigForm
          values={config.watch.values}
          envOverrides={config.watch.env_overrides}
          tomlPath={config.toml_path}
          onSaved={onSaved}
        />
      </TabsContent>

      <TabsContent value="skills">
        <SkillsConfigForm
          values={config.skills.values}
          envOverrides={config.skills.env_overrides}
          tomlPath={config.toml_path}
          onSaved={onSaved}
        />
      </TabsContent>

      <TabsContent value="hosts">
        <div className="space-y-4">
          <ConfigIntro title="Hosts">
            <p>
              Read-only snapshot of managed hosts. Add, remove, or enroll hosts on the <strong>Hosts</strong> page;
              refresh this page (or revisit the tab) after changes to see updates here.
            </p>
          </ConfigIntro>
          <ReadOnlySection title="Hosts" data={config.hosts} />
        </div>
      </TabsContent>
    </Tabs>
    </div>
  );
}
