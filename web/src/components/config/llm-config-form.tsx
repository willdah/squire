"use client";

import { useEffect, useState } from "react";
import { Lock, Loader2, RotateCcw, Save } from "lucide-react";
import { apiPatch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface LLMConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
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

export function LLMConfigForm({ values, envOverrides, tomlPath, onSaved }: LLMConfigFormProps) {
  const [model, setModel] = useState(String(values.model ?? ""));
  const [temperature, setTemperature] = useState(Number(values.temperature ?? 0.2));
  const [maxTokens, setMaxTokens] = useState(Number(values.max_tokens ?? 4096));
  const [apiBase, setApiBase] = useState(() => apiBaseFromValues(values.api_base));
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setModel(String(values.model ?? ""));
    setTemperature(Number(values.temperature ?? 0.2));
    setMaxTokens(Number(values.max_tokens ?? 4096));
    setApiBase(apiBaseFromValues(values.api_base));
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

      const url = persist ? "/api/config/llm?persist=true" : "/api/config/llm";
      await apiPatch(url, changed);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">LLM</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Model</Label>
            {isLocked("model") && <EnvLock field="model" prefix="SQUIRE_LLM_" />}
          </div>
          <Input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={isLocked("model")}
            placeholder="e.g. ollama_chat/llama3.1:8b"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Temperature</Label>
            {isLocked("temperature") && <EnvLock field="temperature" prefix="SQUIRE_LLM_" />}
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
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Max Tokens</Label>
            {isLocked("max_tokens") && <EnvLock field="max_tokens" prefix="SQUIRE_LLM_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value) || 1)}
            disabled={isLocked("max_tokens")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>API Base URL</Label>
            {isLocked("api_base") && <EnvLock field="api_base" prefix="SQUIRE_LLM_" />}
          </div>
          <Input
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            disabled={isLocked("api_base")}
            placeholder="e.g. http://localhost:11434 (Ollama)"
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">
            Optional LiteLLM API base. Provider API keys are usually set via environment variables (see LiteLLM docs).
            Redacted values in the API response are omitted here; enter a new URL to replace the stored one.
          </p>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex items-center justify-between pt-2 border-t">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={persist}
              onChange={(e) => setPersist(e.target.checked)}
              disabled={!tomlPath}
              className="rounded"
            />
            Save to disk{tomlPath ? "" : " (no squire.toml found)"}
          </label>
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
