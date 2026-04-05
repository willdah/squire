"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { AlertRuleForm } from "@/components/notifications/alert-rule-form";
import { Plus, Pencil, Trash2, ShieldAlert } from "lucide-react";
import type { AlertRule, AlertRuleCreate } from "@/lib/types";

const severityVariant: Record<string, "default" | "secondary" | "destructive"> = {
  critical: "destructive",
  warning: "default",
  info: "secondary",
};

export function AlertRulesTab() {
  const { data: rules, mutate } = useSWR("/api/alerts", () =>
    apiGet<AlertRule[]>("/api/alerts")
  );

  const [formOpen, setFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);

  const handleCreate = async (data: AlertRuleCreate) => {
    await apiPost("/api/alerts", data);
    setFormOpen(false);
    mutate();
  };

  const handleUpdate = async (data: AlertRuleCreate) => {
    const { name, ...rest } = data;
    await apiPut(`/api/alerts/${encodeURIComponent(name)}`, rest);
    setEditingRule(null);
    mutate();
  };

  const handleToggle = async (name: string) => {
    await apiPost(`/api/alerts/${encodeURIComponent(name)}/toggle`);
    mutate();
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete alert rule "${name}"?`)) return;
    await apiDelete(`/api/alerts/${encodeURIComponent(name)}`);
    mutate();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg">Alert Rules</h2>
          {rules && rules.length > 0 && (
            <Badge variant="secondary">{rules.length}</Badge>
          )}
        </div>
        <Button size="sm" onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Rule
        </Button>
      </div>

      {!rules || rules.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
          <ShieldAlert className="h-8 w-8" />
          <p className="text-sm">No alert rules configured</p>
          <p className="text-xs">
            Create a rule to trigger alerts when system metrics exceed thresholds.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Condition</TableHead>
              <TableHead>Host</TableHead>
              <TableHead>Severity</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead>Last Fired</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rules.map((r) => (
              <TableRow key={r.name} className="hover:bg-muted/50">
                <TableCell className="font-medium">{r.name}</TableCell>
                <TableCell className="text-sm font-mono text-muted-foreground max-w-xs truncate">
                  {r.condition}
                </TableCell>
                <TableCell className="text-sm">{r.host}</TableCell>
                <TableCell>
                  <Badge variant={severityVariant[r.severity] ?? "secondary"}>
                    {r.severity}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Switch
                    checked={r.enabled}
                    onCheckedChange={() => handleToggle(r.name)}
                  />
                </TableCell>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {r.last_fired_at ? r.last_fired_at.substring(0, 19) : "Never"}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Edit"
                      onClick={() => setEditingRule(r)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Delete"
                      onClick={() => handleDelete(r.name)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <AlertRuleForm
        open={formOpen}
        onOpenChange={setFormOpen}
        onSubmit={handleCreate}
      />

      {editingRule && (
        <AlertRuleForm
          open={!!editingRule}
          onOpenChange={(open) => {
            if (!open) setEditingRule(null);
          }}
          onSubmit={handleUpdate}
          rule={editingRule}
        />
      )}
    </div>
  );
}
