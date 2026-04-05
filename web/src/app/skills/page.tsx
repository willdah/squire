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
import { SkillForm } from "@/components/skills/skill-form";
import {
  ListChecks,
  Plus,
  Pencil,
  Trash2,
  Play,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import type { Skill } from "@/lib/types";

export default function SkillsPage() {
  const router = useRouter();
  const { data: skills, mutate } = useSWR("/api/skills", () =>
    apiGet<Skill[]>("/api/skills")
  );

  const [formOpen, setFormOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);

  const handleCreate = async (data: {
    name: string;
    description: string;
    host: string;
    trigger: string;
    instructions: string;
  }) => {
    await apiPost("/api/skills", data);
    setFormOpen(false);
    mutate();
  };

  const handleUpdate = async (data: {
    name: string;
    description: string;
    host: string;
    trigger: string;
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

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl">Skills</h1>
          {skills && skills.length > 0 && (
            <Badge variant="secondary">{skills.length}</Badge>
          )}
        </div>
        <Button size="sm" onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Skill
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Define instructions for Squire to follow. Skills can be executed manually
        or attached to watch mode for automated checks.
      </p>

      {!skills || skills.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
          <ListChecks className="h-8 w-8" />
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
              <TableHead>Host</TableHead>
              <TableHead>Trigger</TableHead>
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
                <TableCell className="text-sm">{s.host}</TableCell>
                <TableCell>
                  <Badge variant={s.trigger === "watch" ? "secondary" : "outline"}>
                    {s.trigger}
                  </Badge>
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
      />

      {editingSkill && (
        <SkillForm
          open={!!editingSkill}
          onOpenChange={(open) => {
            if (!open) setEditingSkill(null);
          }}
          onSubmit={handleUpdate}
          skill={editingSkill}
        />
      )}
    </div>
  );
}
