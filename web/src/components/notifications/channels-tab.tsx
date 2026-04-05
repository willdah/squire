"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { apiGet, apiPatch, apiPost } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, X, Loader2, Save, Mail, Webhook } from "lucide-react";
import type { ConfigDetailResponse } from "@/lib/types";

const REDACTED = "\u2022\u2022\u2022\u2022\u2022\u2022";

interface WebhookState {
  name: string;
  url: string;
  events: string[];
  headers: Record<string, string>;
  isNew?: boolean;
}

interface EmailState {
  enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  tls: boolean;
  smtp_user: string;
  smtp_password: string;
  from_address: string;
  to_addresses: string[];
  events: string[];
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

function parseEmail(raw: unknown): EmailState {
  const defaults: EmailState = {
    enabled: false,
    smtp_host: "",
    smtp_port: 587,
    tls: true,
    smtp_user: "",
    smtp_password: "",
    from_address: "",
    to_addresses: [],
    events: ["*"],
  };
  if (!raw || typeof raw !== "object") return defaults;
  const e = raw as Record<string, unknown>;
  return {
    enabled: Boolean(e.enabled ?? false),
    smtp_host: String(e.smtp_host ?? ""),
    smtp_port: Number(e.smtp_port ?? 587),
    tls: Boolean(e.tls ?? true),
    smtp_user: String(e.smtp_user ?? ""),
    smtp_password: String(e.smtp_password ?? ""),
    from_address: String(e.from_address ?? ""),
    to_addresses: Array.isArray(e.to_addresses) ? (e.to_addresses as string[]) : [],
    events: Array.isArray(e.events) ? (e.events as string[]) : ["*"],
  };
}

function TagInput({
  tags,
  onAdd,
  onRemove,
  placeholder,
}: {
  tags: string[];
  onAdd: (tag: string) => void;
  onRemove: (tag: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1">
        {tags.map((tag) => (
          <Badge key={tag} variant="secondary" className="text-xs gap-1">
            {tag}
            <button onClick={() => onRemove(tag)} className="hover:text-destructive">
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <Input
        placeholder={placeholder ?? "Type and press Enter"}
        className="text-xs"
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            const val = e.currentTarget.value.trim();
            if (val && !tags.includes(val)) {
              onAdd(val);
            }
            e.currentTarget.value = "";
          }
        }}
      />
    </div>
  );
}

export function ChannelsTab() {
  const { data: config, mutate } = useSWR("/api/config", () =>
    apiGet<ConfigDetailResponse>("/api/config")
  );

  const notifValues = config?.notifications?.values ?? {};

  const [enabled, setEnabled] = useState(false);
  const [webhooks, setWebhooks] = useState<WebhookState[]>([]);
  const [email, setEmail] = useState<EmailState>(parseEmail(null));
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Sync state when config loads
  useEffect(() => {
    if (!config) return;
    const values = config.notifications?.values ?? {};
    setEnabled(Boolean(values.enabled));
    setWebhooks(parseWebhooks(values.webhooks));
    setEmail(parseEmail(values.email));
    setInitialized(true);
  }, [config]);

  const origEnabled = Boolean(notifValues.enabled);
  const origWebhooks = parseWebhooks(notifValues.webhooks);
  const origEmail = parseEmail(notifValues.email);

  const isDirty =
    initialized &&
    (enabled !== origEnabled ||
      JSON.stringify(webhooks) !== JSON.stringify(origWebhooks) ||
      JSON.stringify(email) !== JSON.stringify(origEmail));

  const updateWebhook = (index: number, patch: Partial<WebhookState>) => {
    setWebhooks((prev) => prev.map((wh, i) => (i === index ? { ...wh, ...patch } : wh)));
  };

  const removeWebhook = (index: number) => {
    setWebhooks((prev) => prev.filter((_, i) => i !== index));
  };

  const addWebhook = () => {
    setWebhooks((prev) => [...prev, { name: "", url: "", events: ["*"], headers: {}, isNew: true }]);
  };

  const updateEmail = useCallback((patch: Partial<EmailState>) => {
    setEmail((prev) => ({ ...prev, ...patch }));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const changed: Record<string, unknown> = {};

      if (enabled !== origEnabled) changed.enabled = enabled;

      if (JSON.stringify(webhooks) !== JSON.stringify(origWebhooks)) {
        changed.webhooks = webhooks.map(({ isNew: _, ...wh }) => wh);
      }

      if (JSON.stringify(email) !== JSON.stringify(origEmail)) {
        changed.email = email;
      }

      await apiPatch("/api/config/notifications?persist=true", changed);
      setSuccess("Configuration saved successfully.");
      mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleTestEmail = async () => {
    setTesting(true);
    setError(null);
    setSuccess(null);
    try {
      await apiPost("/api/notifications/test-email");
      setSuccess("Test email sent successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send test email");
    } finally {
      setTesting(false);
    }
  };

  if (!config) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Master enable/disable */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm font-medium">Notifications</Label>
              <p className="text-xs text-muted-foreground">
                Enable or disable all notification channels globally.
              </p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
        </CardContent>
      </Card>

      {/* Webhooks section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Webhook className="h-4 w-4" />
              Webhooks
            </CardTitle>
            <Button variant="outline" size="sm" onClick={addWebhook}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add Webhook
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {webhooks.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No webhooks configured. Add one to receive notifications via HTTP.
            </p>
          )}

          {webhooks.map((wh, i) => (
            <div key={i} className="border rounded-lg p-3 space-y-3">
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
                <TagInput
                  tags={wh.events}
                  onAdd={(ev) => updateWebhook(i, { events: [...wh.events, ev] })}
                  onRemove={(ev) => updateWebhook(i, { events: wh.events.filter((e) => e !== ev) })}
                  placeholder="Add event, press Enter"
                />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Email section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Mail className="h-4 w-4" />
            Email
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">Enabled</Label>
              <p className="text-xs text-muted-foreground">Enable email notifications.</p>
            </div>
            <Switch
              checked={email.enabled}
              onCheckedChange={(v) => updateEmail({ enabled: v })}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">SMTP Host</Label>
              <Input
                value={email.smtp_host}
                onChange={(e) => updateEmail({ smtp_host: e.target.value })}
                placeholder="smtp.example.com"
                className="text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">SMTP Port</Label>
              <Input
                type="number"
                value={email.smtp_port}
                onChange={(e) => updateEmail({ smtp_port: Number(e.target.value) || 587 })}
                className="text-sm"
              />
            </div>
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-sm">TLS</Label>
            <Switch
              checked={email.tls}
              onCheckedChange={(v) => updateEmail({ tls: v })}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">SMTP User</Label>
              <Input
                value={email.smtp_user}
                onChange={(e) => updateEmail({ smtp_user: e.target.value })}
                placeholder="user@example.com"
                className="text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">SMTP Password</Label>
              <Input
                type="password"
                value={email.smtp_password}
                onChange={(e) => updateEmail({ smtp_password: e.target.value })}
                placeholder={email.smtp_password === REDACTED ? REDACTED : "Password"}
                className="text-sm"
              />
              {email.smtp_password === REDACTED && (
                <p className="text-xs text-muted-foreground">Password is hidden for security</p>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">From Address</Label>
            <Input
              value={email.from_address}
              onChange={(e) => updateEmail({ from_address: e.target.value })}
              placeholder="squire@example.com"
              className="text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">To Addresses</Label>
            <TagInput
              tags={email.to_addresses}
              onAdd={(addr) => updateEmail({ to_addresses: [...email.to_addresses, addr] })}
              onRemove={(addr) =>
                updateEmail({ to_addresses: email.to_addresses.filter((a) => a !== addr) })
              }
              placeholder="Add email address, press Enter"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Events</Label>
            <TagInput
              tags={email.events}
              onAdd={(ev) => updateEmail({ events: [...email.events, ev] })}
              onRemove={(ev) => updateEmail({ events: email.events.filter((e) => e !== ev) })}
              placeholder="Add event filter, press Enter"
            />
          </div>

          <div className="pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestEmail}
              disabled={testing || !email.enabled}
            >
              {testing ? (
                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <Mail className="h-3.5 w-3.5 mr-1" />
              )}
              Test Email
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Status messages & save */}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-green-600">{success}</p>}

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={!isDirty || saving}>
          {saving ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Save className="h-4 w-4 mr-2" />
          )}
          Save Changes
        </Button>
      </div>
    </div>
  );
}
