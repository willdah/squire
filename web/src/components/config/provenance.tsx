"use client";

import { useState } from "react";
import { Database, RotateCcw } from "lucide-react";
import { apiDelete } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ConfigSource } from "@/lib/types";

interface SourceBadgeProps {
  section: string;
  field: string;
  sources: Record<string, ConfigSource>;
  onReset?: () => void;
}

/**
 * Small provenance pip shown next to a config field.
 *
 * Only renders for fields whose current value came from a UI-driven DB override.
 * Clicking the pip clears the override and reverts to TOML/defaults.
 */
export function SourceBadge({ section, field, sources, onReset }: SourceBadgeProps) {
  const source = sources[field];
  if (source !== "db") return null;

  const handleReset = async () => {
    await apiDelete(`/api/config/${section}/${encodeURIComponent(field)}`);
    onReset?.();
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          onClick={handleReset}
          aria-label={`Reset ${field}`}
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Database className="h-3 w-3" />
        </TooltipTrigger>
        <TooltipContent>
          <p>Overridden via UI (stored in DB). Click to revert.</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

interface SectionResetButtonProps {
  section: string;
  sources: Record<string, ConfigSource>;
  onReset?: () => void;
}

/**
 * "Reset to file defaults" button for a whole config section.
 *
 * Disabled when no field is currently DB-overridden. Uses a plain confirm()
 * rather than an AlertDialog to avoid pulling more components into the tree;
 * swap in shadcn's AlertDialog if we grow more surfaces needing this.
 */
export function SectionResetButton({ section, sources, onReset }: SectionResetButtonProps) {
  const [busy, setBusy] = useState(false);
  const hasOverrides = Object.values(sources).some((s) => s === "db");

  const handleClick = async () => {
    if (!hasOverrides) return;
    if (!window.confirm(`Reset all ${section} overrides to the values in squire.toml / code defaults?`)) return;
    setBusy(true);
    try {
      await apiDelete(`/api/config/${section}`);
      onReset?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={!hasOverrides || busy}
      onClick={handleClick}
      title={hasOverrides ? "Reset DB overrides for this section" : "No DB overrides in this section"}
    >
      <RotateCcw className="mr-1 h-3.5 w-3.5" />
      Reset
    </Button>
  );
}
