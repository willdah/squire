import type { ReactNode } from "react";
import type { ConfigDetailResponse } from "@/lib/types";

const hintClass =
  "text-xs text-muted-foreground leading-relaxed [&_code]:rounded-sm [&_code]:bg-muted [&_code]:px-1 [&_code]:py-px [&_code]:text-[11px] [&_code]:font-mono";

/** Short explanation under a field or block. */
export function ConfigHint({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={`${hintClass}${className ? ` ${className}` : ""}`}>{children}</p>;
}

/** Callout for section-level context (how saving works, warnings). */
export function ConfigIntro({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-muted/40 px-4 py-3">
      {title ? <p className="text-sm font-medium text-foreground">{title}</p> : null}
      <div className={`${title ? "mt-1.5 " : ""}space-y-2 text-xs text-muted-foreground leading-relaxed [&_code]:rounded-sm [&_code]:bg-muted [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[11px]`}>
        {children}
      </div>
    </div>
  );
}

/** When any section has env-forced values, list them so users know why Save may fail or fields are locked. */
export function ConfigEnvOverrideNotice({ config }: { config: ConfigDetailResponse }) {
  const sections: { label: string; vars: string[] }[] = [];
  const add = (label: string, prefix: string, keys: string[]) => {
    if (keys.length === 0) return;
    sections.push({ label, vars: keys.map((k) => `${prefix}${k.toUpperCase()}`) });
  };

  add("App", "SQUIRE_", config.app.env_overrides);
  add("LLM", "SQUIRE_LLM_", config.llm.env_overrides);
  add("Database", "SQUIRE_DB_", config.database.env_overrides);
  add("Notifications", "SQUIRE_NOTIFICATIONS_", config.notifications.env_overrides);
  add("Guardrails", "SQUIRE_GUARDRAILS_", config.guardrails.env_overrides);
  add("Watch", "SQUIRE_WATCH_", config.watch.env_overrides);
  add("Skills", "SQUIRE_SKILLS_", config.skills.env_overrides);

  if (sections.length === 0) return null;

  return (
    <div className="rounded-md border border-amber-500/25 bg-amber-500/5 px-4 py-3 dark:border-amber-500/20 dark:bg-amber-500/10">
      <p className="text-sm font-medium text-foreground">Some values are set by environment variables</p>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
        {sections.map((s) => (
          <li key={s.label}>
            <span className="font-medium text-foreground">{s.label}:</span> {s.vars.join(", ")}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Locked fields show a lock icon. To change them from the UI, unset the variable and restart Squire, or edit your
        deploy configuration.
      </p>
    </div>
  );
}
