"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { apiGet } from "@/lib/api";
import type { AlertRule, AlertRuleCreate, HostInfo } from "@/lib/types";

interface AlertRuleFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: AlertRuleCreate) => void;
  rule?: AlertRule | null;
}

export function AlertRuleForm({ open, onOpenChange, onSubmit, rule }: AlertRuleFormProps) {
  const [name, setName] = useState(rule?.name ?? "");
  const [condition, setCondition] = useState(rule?.condition ?? "");
  const [host, setHost] = useState(rule?.host ?? "all");
  const [severity, setSeverity] = useState(rule?.severity ?? "warning");
  const [cooldownMinutes, setCooldownMinutes] = useState(rule?.cooldown_minutes ?? 30);

  const { data: hosts } = useSWR("/api/hosts", () => apiGet<HostInfo[]>("/api/hosts"));

  const isEdit = !!rule;

  const namePattern = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;
  const isNameValid =
    name.trim().length > 0 &&
    name.trim().length <= 64 &&
    namePattern.test(name.trim()) &&
    !name.includes("--");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isNameValid || !condition.trim()) return;
    onSubmit({
      name: name.trim(),
      condition: condition.trim(),
      host,
      severity,
      cooldown_minutes: cooldownMinutes,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit Alert Rule" : "New Alert Rule"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the alert rule condition and settings."
                : "Define a condition that triggers an alert during watch mode."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="rule-name">Name</Label>
              <Input
                id="rule-name"
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase())}
                placeholder="high-cpu-alert"
                disabled={isEdit}
                required
              />
              {!isEdit && name && !isNameValid && (
                <p className="text-xs text-destructive">
                  Lowercase letters, numbers, and hyphens only (max 64 chars).
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rule-condition">Condition</Label>
              <Input
                id="rule-condition"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                placeholder="cpu_percent > 90"
                required
              />
            </div>

            <div className="flex gap-4">
              <div className="space-y-2 flex-1">
                <Label>Host</Label>
                <Select value={host} onValueChange={(v) => v && setHost(v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">all</SelectItem>
                    {(hosts ?? []).map((h) => (
                      <SelectItem key={h.name} value={h.name}>
                        {h.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 flex-1">
                <Label>Severity</Label>
                <Select value={severity} onValueChange={(v) => v && setSeverity(v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="info">info</SelectItem>
                    <SelectItem value="warning">warning</SelectItem>
                    <SelectItem value="critical">critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="rule-cooldown">Cooldown (minutes)</Label>
              <Input
                id="rule-cooldown"
                type="number"
                min={1}
                value={cooldownMinutes}
                onChange={(e) => setCooldownMinutes(Number(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">
                Minimum time between consecutive firings of this rule.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit">{isEdit ? "Update" : "Create"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
