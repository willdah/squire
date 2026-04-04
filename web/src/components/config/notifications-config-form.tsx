"use client";

import { useState } from "react";
import { Lock, Loader2, RotateCcw, Save, Plus, Trash2, X } from "lucide-react";
import { apiPatch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface NotificationsConfigFormProps {
  values: Record<string, unknown>;
  envOverrides: string[];
  tomlPath: string | null;
  onSaved: () => void;
}

interface WebhookState {
  name: string;
  url: string;
  events: string[];
  headers: Record<string, string>;
  isNew?: boolean;
}

const REDACTED = "\u2022\u2022\u2022\u2022\u2022\u2022";

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

function parseWebhooks(raw: unknown): WebhookState[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((wh) => ({
    name: String(wh.name ?? ""),
    url: String(wh.url ?? ""),
    events: Array.isArray(wh.events) ? (wh.events as string[]) : ["*"],
    headers: typeof wh.headers === "object" && wh.headers ? (wh.headers as Record<string, string>) : {},
  }));
}

export function NotificationsConfigForm({ values, envOverrides, tomlPath, onSaved }: NotificationsConfigFormProps) {
  const [enabled, setEnabled] = useState(Boolean(values.enabled));
  const [webhooks, setWebhooks] = useState<WebhookState[]>(parseWebhooks(values.webhooks));
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = (field: string) => envOverrides.includes(field);

  const origWebhooks = parseWebhooks(values.webhooks);
  const webhooksDirty = JSON.stringify(webhooks) !== JSON.stringify(origWebhooks);
  const isDirty = enabled !== Boolean(values.enabled) || webhooksDirty;

  const revert = () => {
    setEnabled(Boolean(values.enabled));
    setWebhooks(parseWebhooks(values.webhooks));
    setError(null);
  };

  const updateWebhook = (index: number, patch: Partial<WebhookState>) => {
    setWebhooks((prev) => prev.map((wh, i) => (i === index ? { ...wh, ...patch } : wh)));
  };

  const removeWebhook = (index: number) => {
    setWebhooks((prev) => prev.filter((_, i) => i !== index));
  };

  const addWebhook = () => {
    setWebhooks((prev) => [...prev, { name: "", url: "", events: ["*"], headers: {}, isNew: true }]);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const changed: Record<string, unknown> = {};
      if (enabled !== Boolean(values.enabled)) changed.enabled = enabled;
      if (webhooksDirty) {
        changed.webhooks = webhooks.map(({ isNew: _, ...wh }) => wh);
      }

      const url = persist ? "/api/config/notifications?persist=true" : "/api/config/notifications";
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
        <CardTitle className="text-base">Notifications</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Label>Enabled</Label>
            {isLocked("enabled") && <EnvLock field="enabled" prefix="SQUIRE_NOTIFICATIONS_" />}
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            disabled={isLocked("enabled")}
          />
        </div>

        <div className="border-t pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">Webhooks</Label>
            <Button variant="outline" size="sm" onClick={addWebhook}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add
            </Button>
          </div>

          {webhooks.length === 0 && (
            <p className="text-xs text-muted-foreground">No webhooks configured.</p>
          )}

          {webhooks.map((wh, i) => (
            <div key={i} className="border rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <Input
                  value={wh.name}
                  onChange={(e) => updateWebhook(i, { name: e.target.value })}
                  placeholder="Webhook name"
                  className="text-sm font-medium max-w-48"
                />
                <Button variant="ghost" size="sm" onClick={() => removeWebhook(i)}>
                  <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">URL</Label>
                {wh.isNew ? (
                  <Input
                    value={wh.url}
                    onChange={(e) => updateWebhook(i, { url: e.target.value })}
                    placeholder="https://..."
                    className="text-xs font-mono"
                  />
                ) : (
                  <Input value={wh.url} disabled className="text-xs font-mono" />
                )}
                {!wh.isNew && wh.url === REDACTED && (
                  <p className="text-xs text-muted-foreground">URL is hidden for security</p>
                )}
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Events</Label>
                <div className="flex flex-wrap gap-1">
                  {wh.events.map((ev) => (
                    <Badge key={ev} variant="secondary" className="text-xs gap-1">
                      {ev}
                      <button
                        onClick={() =>
                          updateWebhook(i, { events: wh.events.filter((e) => e !== ev) })
                        }
                        className="hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <Input
                  placeholder="Add event, press Enter"
                  className="text-xs"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      const val = e.currentTarget.value.trim();
                      if (val && !wh.events.includes(val)) {
                        updateWebhook(i, { events: [...wh.events, val] });
                      }
                      e.currentTarget.value = "";
                    }
                  }}
                />
              </div>
            </div>
          ))}
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
