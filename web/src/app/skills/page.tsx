"use client";

import { useState } from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkillForm } from "@/components/skills/skill-form";
import {
  ListChecks,
  Loader2,
  Plus,
  Pencil,
  Trash2,
  Play,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import type { HostInfo, IncidentFamilyInfo, PlaybookDryRunSelection, Skill } from "@/lib/types";

export default function SkillsPage() {
  const router = useRouter();
  const { data: skills, mutate } = useSWR("/api/skills", () =>
    apiGet<Skill[]>("/api/skills")
  );
  const { data: incidentFamilies } = useSWR("/api/skills/incident-families", () =>
    apiGet<IncidentFamilyInfo[]>("/api/skills/incident-families")
  );
  const { data: hosts } = useSWR("/api/hosts", () => apiGet<HostInfo[]>("/api/hosts"));

  const [formOpen, setFormOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [dryRunKey, setDryRunKey] = useState("disk-pressure:local");
  const [dryRunHost, setDryRunHost] = useState("local");
  const availableHostNames = Array.from(
    new Set(["local", ...((hosts ?? []).map((h) => h.name).filter(Boolean))])
  ).sort((a, b) => (a === "local" ? -1 : b === "local" ? 1 : a.localeCompare(b)));

  const [dryRunResult, setDryRunResult] = useState<PlaybookDryRunSelection | null>(null);
  const [isDryRunning, setIsDryRunning] = useState(false);

  const handleCreate = async (data: {
    name: string;
    description: string;
    hosts: string[];
    trigger: string;
    incident_keys: string[];
    allow_custom_incident_prefixes: boolean;
    instructions: string;
  }) => {
    await apiPost("/api/skills", data);
    setFormOpen(false);
    mutate();
  };

  const handleUpdate = async (data: {
    name: string;
    description: string;
    hosts: string[];
    trigger: string;
    incident_keys: string[];
    allow_custom_incident_prefixes: boolean;
    instructions: string;
  }) => {
    const { name, ...rest } = data;
    await apiPut(`/api/skills/${name}`, rest);
    setEditingSkill(null);
    mutate();
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete skill "${name}"?`)) return;
    await apiDelete(`/api/skills/${name}`);
    mutate();
  };

  const handleToggle = async (name: string) => {
    await apiPost(`/api/skills/${name}/toggle`);
    mutate();
  };

  const handleExecute = async (name: string) => {
    const result = await apiPost<{ skill_name: string; instructions: string }>(
      `/api/skills/${encodeURIComponent(name)}/execute`
    );
    router.push(
      `/chat?skill=${encodeURIComponent(result.skill_name)}`
    );
  };

  const handleBootstrapPlaybooks = async () => {
    await apiPost("/api/skills/bootstrap-watch-playbooks");
    mutate();
  };

  const handleDryRun = async () => {
    setIsDryRunning(true);
    try {
      const response = await apiPost<{ selections: PlaybookDryRunSelection[] }>("/api/skills/playbooks/dry-run", {
        incidents: [
          {
            key: dryRunKey,
            host: dryRunHost,
            severity: "high",
            title: dryRunKey,
            detail: "",
          },
        ],
      });
      setDryRunResult(response.selections[0] ?? null);
    } finally {
      setIsDryRunning(false);
    }
  };

  const conflictEntries = (() => {
    if (!skills) return [];
    const map = new Map<string, string[]>();
    for (const skill of skills) {
      if (skill.trigger !== "watch" || !skill.enabled) continue;
      for (const key of skill.incident_keys || []) {
        const list = map.get(key) ?? [];
        list.push(skill.name);
        map.set(key, list);
      }
    }
    return Array.from(map.entries()).filter(([, names]) => names.length > 1);
  })();

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl">Skills</h1>
          {skills && skills.length > 0 && (
            <Badge variant="secondary">{skills.length}</Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={handleBootstrapPlaybooks}>
            Install Starter Watch Playbooks
          </Button>
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Skill
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Define instructions for Squire to follow. Skills can be executed manually
        or attached to watch mode for automated checks.
      </p>

      {conflictEntries.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
          <p className="font-medium mb-1">Routing conflicts detected</p>
          {conflictEntries.map(([key, names]) => (
            <p key={key} className="text-muted-foreground">
              <code>{key}</code>: {names.join(", ")}
            </p>
          ))}
        </div>
      )}

      <div className="w-full max-w-4xl mx-auto rounded-md border border-primary/30 bg-primary/5 p-4 space-y-3">
        <p className="font-medium text-sm text-primary">Playbook Router Dry Run</p>
        <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] gap-3 items-start">
          <div className="space-y-1">
            <Label htmlFor="dry-run-incident-key" className="text-xs text-muted-foreground">Incident Key</Label>
            <Input
              id="dry-run-incident-key"
              value={dryRunKey}
              onChange={(e) => setDryRunKey(e.target.value)}
              placeholder="disk-pressure:local"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="dry-run-host" className="text-xs text-muted-foreground">Host</Label>
            <Select value={dryRunHost} onValueChange={(v) => setDryRunHost(v ?? "local")}>
              <SelectTrigger id="dry-run-host" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableHostNames.map((hostName) => (
                  <SelectItem key={hostName} value={hostName}>
                    {hostName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs opacity-0 select-none">Run</Label>
            <Button
              variant="default"
              onClick={handleDryRun}
              disabled={isDryRunning}
              className="w-full md:w-auto min-w-36 px-6 whitespace-nowrap bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {isDryRunning ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Running...
                </>
              ) : (
                "Run Dry Run"
              )}
            </Button>
          </div>
        </div>
        {dryRunResult && (
          <pre className="text-xs bg-card border border-primary/20 rounded-md p-2 overflow-x-auto">
{JSON.stringify(dryRunResult, null, 2)}
          </pre>
        )}
      </div>

      {!skills || skills.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
          <ListChecks className="h-8 w-8 opacity-40" />
          <p className="text-sm">No skills configured</p>
          <p className="text-xs">
            Create a skill to give Squire guided, repeatable behavior.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Hosts</TableHead>
              <TableHead>Trigger</TableHead>
              <TableHead>Incident Keys</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {skills.map((s) => (
              <TableRow key={s.name} className="hover:bg-muted/50">
                <TableCell className="font-medium">{s.name}</TableCell>
                <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                  {s.description || "-"}
                </TableCell>
                <TableCell className="text-sm">{(s.hosts || []).join(", ")}</TableCell>
                <TableCell>
                  <Badge variant={s.trigger === "watch" ? "secondary" : "outline"}>
                    {s.trigger}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                  {(s.incident_keys || []).join(", ") || "—"}
                </TableCell>
                <TableCell>
                  <Badge variant={s.enabled ? "default" : "outline"}>
                    {s.enabled ? "enabled" : "disabled"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Execute"
                      disabled={!s.enabled}
                      onClick={() => handleExecute(s.name)}
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Edit"
                      onClick={() => setEditingSkill(s)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title={s.enabled ? "Disable" : "Enable"}
                      onClick={() => handleToggle(s.name)}
                    >
                      {s.enabled ? (
                        <ToggleRight className="h-4 w-4" />
                      ) : (
                        <ToggleLeft className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Delete"
                      onClick={() => handleDelete(s.name)}
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

      <SkillForm
        open={formOpen}
        onOpenChange={setFormOpen}
        onSubmit={handleCreate}
        incidentFamilies={incidentFamilies ?? []}
        availableHosts={hosts ?? []}
      />

      {editingSkill && (
        <SkillForm
          open={!!editingSkill}
          onOpenChange={(open) => {
            if (!open) setEditingSkill(null);
          }}
          onSubmit={handleUpdate}
          skill={editingSkill}
          incidentFamilies={incidentFamilies ?? []}
          availableHosts={hosts ?? []}
        />
      )}
    </div>
  );
}
