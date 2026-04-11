"use client";

import { useState } from "react";
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

interface SkillsConfigFormProps {
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
          <p>
            Set by {prefix}
            {field.toUpperCase()}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function SkillsConfigForm({ values, envOverrides, tomlPath, onSaved }: SkillsConfigFormProps) {
  const [path, setPath] = useState(String(values.path ?? ""));
  const [persist, setPersist] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = (field: string) => envOverrides.includes(field);
  const isDirty = path !== String(values.path ?? "");

  const revert = () => {
    setPath(String(values.path ?? ""));
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const url = persist ? "/api/config/skills?persist=true" : "/api/config/skills";
      await apiPatch(url, { path });
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
        <CardTitle className="text-base">Skills</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          Directory for Open Agent Skills (each skill in a <code className="font-mono">NAME/SKILL.md</code>{" "}
          folder). Changes apply immediately to the API; the autonomous watch process reloads skills from disk each
          cycle.
        </p>
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>Skills directory</Label>
            {isLocked("path") && <EnvLock field="path" prefix="SQUIRE_SKILLS_" />}
          </div>
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            disabled={isLocked("path")}
            className="font-mono text-xs"
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
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5 mr-1" />
              )}
              Save
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
