"use client";

import { useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Skill } from "@/lib/types";

interface SkillFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: {
    name: string;
    description: string;
    host: string;
    trigger: string;
    instructions: string;
  }) => void;
  skill?: Skill | null;
}

export function SkillForm({ open, onOpenChange, onSubmit, skill }: SkillFormProps) {
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [host, setHost] = useState(skill?.host ?? "all");
  const [trigger, setTrigger] = useState(skill?.trigger ?? "manual");
  const [instructions, setInstructions] = useState(skill?.instructions ?? "");

  const isEdit = !!skill;

  const namePattern = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;
  const isNameValid = name.trim().length > 0 && name.trim().length <= 64
    && namePattern.test(name.trim()) && !name.includes("--");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isNameValid || !description.trim() || !instructions.trim()) return;
    onSubmit({
      name: name.trim(),
      description: description.trim(),
      host,
      trigger,
      instructions: instructions.trim(),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit Skill" : "New Skill"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the skill configuration and instructions."
                : "Define instructions for Squire to follow."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="skill-name">Name</Label>
              <Input
                id="skill-name"
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase())}
                placeholder="restart-on-error"
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
              <Label htmlFor="skill-desc">Description</Label>
              <Input
                id="skill-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this skill does and when to use it..."
                required
              />
            </div>

            <div className="flex gap-4">
              <div className="space-y-2 flex-1">
                <Label>Host</Label>
                <Input
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="all"
                />
              </div>
              <div className="space-y-2 flex-1">
                <Label>Trigger</Label>
                <Select value={trigger} onValueChange={(v) => setTrigger(v ?? "manual")}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="watch">Watch</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="skill-instructions">Instructions</Label>
              <Textarea
                id="skill-instructions"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="Check the status of all Docker containers on the target host..."
                rows={10}
                className="font-mono text-sm"
                required
              />
              <p className="text-xs text-muted-foreground">
                Freeform Markdown instructions for the agent to follow.
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
