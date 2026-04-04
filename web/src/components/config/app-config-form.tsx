"use client";

import { useState } from "react";
import { Lock, Loader2, RotateCcw, Save } from "lucide-react";
import { apiPatch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface AppConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  tomlPath: string | null;
  onSaved: () => void;
}

const RISK_OPTIONS = [
  { value: "read-only", label: "Read Only" },
  { value: "cautious", label: "Cautious" },
  { value: "standard", label: "Standard" },
  { value: "full-trust", label: "Full Trust" },
];

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

export function AppConfigForm({ values, envOverrides, tomlPath, onSaved }: AppConfigFormProps) {
  const [riskTolerance, setRiskTolerance] = useState(String(values.risk_tolerance ?? "cautious"));
  const [riskStrict, setRiskStrict] = useState(Boolean(values.risk_strict));
  const [historyLimit, setHistoryLimit] = useState(Number(values.history_limit ?? 50));
  const [maxToolRounds, setMaxToolRounds] = useState(Number(values.max_tool_rounds ?? 10));
  const [multiAgent, setMultiAgent] = useState(Boolean(values.multi_agent));
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = (field: string) => envOverrides.includes(field);

  const isDirty =
    riskTolerance !== String(values.risk_tolerance ?? "cautious") ||
    riskStrict !== Boolean(values.risk_strict) ||
    historyLimit !== Number(values.history_limit ?? 50) ||
    maxToolRounds !== Number(values.max_tool_rounds ?? 10) ||
    multiAgent !== Boolean(values.multi_agent);

  const revert = () => {
    setRiskTolerance(String(values.risk_tolerance ?? "cautious"));
    setRiskStrict(Boolean(values.risk_strict));
    setHistoryLimit(Number(values.history_limit ?? 50));
    setMaxToolRounds(Number(values.max_tool_rounds ?? 10));
    setMultiAgent(Boolean(values.multi_agent));
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const changed: Record<string, unknown> = {};
      if (riskTolerance !== String(values.risk_tolerance ?? "cautious")) changed.risk_tolerance = riskTolerance;
      if (riskStrict !== Boolean(values.risk_strict)) changed.risk_strict = riskStrict;
      if (historyLimit !== Number(values.history_limit ?? 50)) changed.history_limit = historyLimit;
      if (maxToolRounds !== Number(values.max_tool_rounds ?? 10)) changed.max_tool_rounds = maxToolRounds;
      if (multiAgent !== Boolean(values.multi_agent)) changed.multi_agent = multiAgent;

      const url = persist ? "/api/config/app?persist=true" : "/api/config/app";
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
        <CardTitle className="text-base">App</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Risk Tolerance</Label>
            {isLocked("risk_tolerance") && <EnvLock field="risk_tolerance" prefix="SQUIRE_" />}
          </div>
          <Select
            value={riskTolerance}
            onValueChange={(v) => v && setRiskTolerance(v)}
            disabled={isLocked("risk_tolerance")}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RISK_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Label>Risk Strict</Label>
            {isLocked("risk_strict") && <EnvLock field="risk_strict" prefix="SQUIRE_" />}
          </div>
          <Switch
            checked={riskStrict}
            onCheckedChange={setRiskStrict}
            disabled={isLocked("risk_strict")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>History Limit</Label>
            {isLocked("history_limit") && <EnvLock field="history_limit" prefix="SQUIRE_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={historyLimit}
            onChange={(e) => setHistoryLimit(parseInt(e.target.value) || 1)}
            disabled={isLocked("history_limit")}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Max Tool Rounds</Label>
            {isLocked("max_tool_rounds") && <EnvLock field="max_tool_rounds" prefix="SQUIRE_" />}
          </div>
          <Input
            type="number"
            min={1}
            value={maxToolRounds}
            onChange={(e) => setMaxToolRounds(parseInt(e.target.value) || 1)}
            disabled={isLocked("max_tool_rounds")}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Label>Multi-Agent</Label>
            {isLocked("multi_agent") && <EnvLock field="multi_agent" prefix="SQUIRE_" />}
          </div>
          <Switch
            checked={multiAgent}
            onCheckedChange={setMultiAgent}
            disabled={isLocked("multi_agent")}
          />
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
