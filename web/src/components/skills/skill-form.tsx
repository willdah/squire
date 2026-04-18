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
import type { Effect, HostInfo, IncidentFamilyInfo, Skill } from "@/lib/types";

interface SkillFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: {
    name: string;
    description: string;
    hosts: string[];
    trigger: string;
    incident_keys: string[];
    allow_custom_incident_prefixes: boolean;
    effect: Effect;
    instructions: string;
  }) => void;
  skill?: Skill | null;
  incidentFamilies: IncidentFamilyInfo[];
  availableHosts: HostInfo[];
}

export function SkillForm({ open, onOpenChange, onSubmit, skill, incidentFamilies, availableHosts }: SkillFormProps) {
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [selectedHost, setSelectedHost] = useState(skill?.hosts?.[0] ?? "all");
  const [trigger, setTrigger] = useState(skill?.trigger ?? "manual");
  const [effect, setEffect] = useState<Effect>(skill?.effect ?? "mixed");
  const [incidentKeys, setIncidentKeys] = useState<string[]>(skill?.incident_keys ?? []);
  const [customIncidentKeys, setCustomIncidentKeys] = useState("");
  const [allowCustomIncidentPrefixes, setAllowCustomIncidentPrefixes] = useState(false);
  const [instructions, setInstructions] = useState(skill?.instructions ?? "");

  const isEdit = !!skill;

  const namePattern = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;
  const isNameValid = name.trim().length > 0 && name.trim().length <= 64
    && namePattern.test(name.trim()) && !name.includes("--");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isNameValid || !description.trim() || !instructions.trim()) return;
    const extraIncidentKeys = customIncidentKeys
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);
    const mergedIncidentKeys = Array.from(new Set([...incidentKeys, ...extraIncidentKeys]));
    onSubmit({
      name: name.trim(),
      description: description.trim(),
      hosts: [selectedHost || "all"],
      trigger,
      incident_keys: trigger === "watch" ? mergedIncidentKeys : [],
      allow_custom_incident_prefixes: trigger === "watch" ? allowCustomIncidentPrefixes : false,
      effect,
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
                <Select value={selectedHost} onValueChange={(v) => setSelectedHost(v ?? "all")}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">all</SelectItem>
                    <SelectItem value="local">local</SelectItem>
                    {(availableHosts ?? [])
                      .filter((h) => h.name !== "local")
                      .map((h) => (
                        <SelectItem key={h.name} value={h.name}>
                          {h.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">Choose a specific host or `all`.</p>
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

            {trigger === "watch" && (
              <div className="space-y-2">
                <Label>Incident Families (Playbook Routing)</Label>
                <div className="rounded-md border p-3 space-y-2 max-h-40 overflow-y-auto">
                  {incidentFamilies.map((family) => {
                    const checked = incidentKeys.includes(family.prefix);
                    return (
                      <label key={family.prefix} className="flex items-start gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setIncidentKeys((prev) => [...prev, family.prefix]);
                            } else {
                              setIncidentKeys((prev) => prev.filter((k) => k !== family.prefix));
                            }
                          }}
                        />
                        <span>
                          <code>{family.prefix}</code> — {family.description}
                        </span>
                      </label>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  A watch skill becomes a playbook candidate when at least one incident family is selected.
                </p>
                <div className="space-y-2">
                  <Label htmlFor="custom-incident-keys">Custom Incident Prefixes (advanced)</Label>
                  <Input
                    id="custom-incident-keys"
                    value={customIncidentKeys}
                    onChange={(e) => setCustomIncidentKeys(e.target.value)}
                    placeholder="power-event:, network-latency:"
                  />
                  <label className="text-xs text-muted-foreground flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={allowCustomIncidentPrefixes}
                      onChange={(e) => setAllowCustomIncidentPrefixes(e.target.checked)}
                    />
                    Allow non-catalog prefixes for this save
                  </label>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>Effect</Label>
              <Select value={effect} onValueChange={(v) => setEffect((v ?? "mixed") as Effect)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="read">Read — observes only</SelectItem>
                  <SelectItem value="write">Write — mutates state</SelectItem>
                  <SelectItem value="mixed">Mixed — both, or depends</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Declare what this skill does to system state. Used for filtering in the catalog.
              </p>
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
