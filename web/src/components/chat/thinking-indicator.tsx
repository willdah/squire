"use client";

/* eslint-disable @next/next/no-img-element */

interface ThinkingIndicatorProps {
  state: "thinking" | "tool" | "streaming" | null;
  toolName?: string;
}

export function ThinkingIndicator({ state, toolName }: ThinkingIndicatorProps) {
  if (!state) return null;

  return (
    <div className="flex items-center gap-3 animate-fade-in">
      <div className="h-8 w-8 rounded-full overflow-hidden bg-muted shrink-0 opacity-60 ring-1 ring-border/30">
        <img
          src="/squire-avatar.png"
          alt="Squire"
          className="h-full w-full object-cover"
        />
      </div>
      <div className="flex items-center gap-2.5">
        {/* Bouncing dots */}
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="block h-1.5 w-1.5 rounded-full bg-primary/60 animate-pulse-dot"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>
        {state === "tool" && toolName && (
          <span className="text-xs font-mono bg-primary/8 text-primary border border-primary/15 rounded-md px-2 py-0.5">
            {toolName}
          </span>
        )}
        {state === "thinking" && (
          <span className="text-xs text-muted-foreground">Thinking</span>
        )}
      </div>
    </div>
  );
}
