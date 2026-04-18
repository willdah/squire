"use client";

import { useEffect, useState } from "react";
import { Lock, Loader2, RotateCcw, Save } from "lucide-react";
import { apiGet, apiPatch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConfigSource, LLMModelsResponse } from "@/lib/types";
import { ConfigHint, ConfigIntro } from "./config-help";
import { SectionResetButton, SourceBadge } from "./provenance";

interface LLMConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  sources: Record<string, ConfigSource>;
  tomlPath: string | null;
  onSaved: () => void;
}

function EnvLock({ field, prefix }: { field: string; prefix: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
        </TooltipTrigger>
        <TooltipContent>
          <p>Set by {prefix}{field.toUpperCase()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

const REDACTED = "\u2022\u2022\u2022\u2022\u2022\u2022";

function apiBaseFromValues(v: unknown): string {
  if (v == null) return "";
  const s = String(v);
  return s === REDACTED ? "" : s;
}

export function LLMConfigForm({ values, envOverrides, sources, onSaved }: LLMConfigFormProps) {
  const [model, setModel] = useState(String(values.model ?? ""));
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelProvider, setModelProvider] = useState<string>("");
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelLookupError, setModelLookupError] = useState<string | null>(null);
  const [temperature, setTemperature] = useState(Number(values.temperature ?? 0.2));
  const [maxTokens, setMaxTokens] = useState(Number(values.max_tokens ?? 4096));
  const [apiBase, setApiBase] = useState(() => apiBaseFromValues(values.api_base));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setModel(String(values.model ?? ""));
    setTemperature(Number(values.temperature ?? 0.2));
    setMaxTokens(Number(values.max_tokens ?? 4096));
    setApiBase(apiBaseFromValues(values.api_base));
  }, [values.api_base, values.max_tokens, values.model, values.temperature]);

  useEffect(() => {
    let cancelled = false;
    setModelsLoading(true);
    setModelLookupError(null);
    apiGet<LLMModelsResponse>("/api/config/llm/models")
      .then((result) => {
        if (cancelled) return;
        setModelProvider(result.provider ?? "");
        const current = String(values.model ?? "");
        setModelOptions(Array.from(new Set([...(result.models ?? []), current])).filter(Boolean).sort());
        if (result.error) {
          setModelLookupError(`Provider model lookup failed: ${result.error}`);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setModelLookupError(err instanceof Error ? err.message : "Failed to load provider models.");
        setModelOptions([String(values.model ?? "")].filter(Boolean));
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [values]);

  const isLocked = (field: string) => envOverrides.includes(field);

  const origApiBase = apiBaseFromValues(values.api_base);

  const isDirty =
    model !== String(values.model ?? "") ||
    temperature !== Number(values.temperature ?? 0.2) ||
    maxTokens !== Number(values.max_tokens ?? 4096) ||
    apiBase !== origApiBase;

  const revert = () => {
    setModel(String(values.model ?? ""));
    setTemperature(Number(values.temperature ?? 0.2));
    setMaxTokens(Number(values.max_tokens ?? 4096));
    setApiBase(origApiBase);
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const changed: Record<string, unknown> = {};
      if (model !== String(values.model ?? "")) changed.model = model;
      if (temperature !== Number(values.temperature ?? 0.2)) changed.temperature = temperature;
      if (maxTokens !== Number(values.max_tokens ?? 4096)) changed.max_tokens = maxTokens;
      if (apiBase !== origApiBase) changed.api_base = apiBase.trim() === "" ? null : apiBase.trim();

      await apiPatch("/api/config/llm", changed);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-base">LLM</CardTitle>
          <CardDescription>
            LiteLLM model id and generation parameters for chat and the web-driven agent. Takes effect on the next
            request that builds the model client.
          </CardDescription>
        </div>
        <SectionResetButton section="llm" sources={sources} onReset={onSaved} />
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfigIntro title="Provider keys">
          <p>
            API keys for cloud providers are not stored here—configure them with environment variables as described in
            LiteLLM. This form only changes model id, sampling, and optional base URL.
          </p>
        </ConfigIntro>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Model{modelProvider ? ` (${modelProvider})` : ""}</Label>
            {isLocked("model") && <EnvLock field="model" prefix="SQUIRE_LLM_" />}
            <SourceBadge section="llm" field="model" sources={sources} onReset={onSaved} />
          </div>
          {modelsLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading provider models...
            </div>
          ) : (
            <Select value={model} onValueChange={(value) => setModel(value ?? "")}>
              <SelectTrigger className="w-full font-mono text-xs" disabled={isLocked("model") || modelOptions.length === 0}>
                <SelectValue placeholder="No models available" />
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((option) => (
                  <SelectItem key={option} value={option} className="font-mono text-xs">
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <ConfigHint>
            Models are loaded from the active provider. Selecting one saves the LiteLLM id (for example{" "}
            <code>ollama_chat/...</code> or <code>gemini/...</code>).
          </ConfigHint>
          {modelLookupError && <p className="text-xs text-muted-foreground">{modelLookupError}</p>}
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Temperature</Label>
            {isLocked("temperature") && <EnvLock field="temperature" prefix="SQUIRE_LLM_" />}
            <SourceBadge section="llm" field="temperature" sources={sources} onReset={onSaved} />
          </div>
          <Input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value) || 0)}
            disabled={isLocked("temperature")}
          />
          <ConfigHint>
            Randomness of completions: lower is more deterministic; higher explores more varied phrasing and tool
            arguments.
          </ConfigHint>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Max Tokens</Label>
            {isLocked("max_tokens") && <EnvLock field="max_tokens" prefix="SQUIRE_LLM_" />}
            <SourceBadge section="llm" field="max_tokens" sources={sources} onReset={onSaved} />
          </div>
          <Input
            type="number"
            min={1}
            value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value) || 1)}
            disabled={isLocked("max_tokens")}
          />
          <ConfigHint>Upper bound on tokens in each model response (output side). Raise if answers truncate.</ConfigHint>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>API Base URL</Label>
            {isLocked("api_base") && <EnvLock field="api_base" prefix="SQUIRE_LLM_" />}
            <SourceBadge section="llm" field="api_base" sources={sources} onReset={onSaved} />
          </div>
          <Input
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            disabled={isLocked("api_base")}
            placeholder="e.g. http://localhost:11434 (Ollama)"
            className="font-mono text-xs"
          />
          <ConfigHint>
            Override the default HTTP endpoint for the provider (e.g. local Ollama). Redacted values are hidden in the
            API; type a new URL to replace the stored base. Clearing the field removes the override.
          </ConfigHint>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex items-center justify-end pt-2 border-t">
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={revert} disabled={!isDirty}>
              <RotateCcw className="h-3.5 w-3.5 mr-1" />
              Revert
            </Button>
            <Button size="sm" onClick={handleSave} disabled={!isDirty || saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              Save
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
