"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { apiGet } from "@/lib/api";
import {
  MessageSquare,
  Server,
  Bell,
  Settings,
  Activity,
  History,
  ListChecks,
  Eye,
  Wrench,
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConfigDetailResponse } from "@/lib/types";

const chatNav = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/sessions", label: "Sessions", icon: History },
];

const monitorNav = [
  { href: "/watch", label: "Watch", icon: Eye },
  { href: "/activity", label: "Activity", icon: Activity },
];

const systemNav = [
  { href: "/skills", label: "Skills", icon: ListChecks },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/hosts", label: "Hosts", icon: Server },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/config", label: "Config", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: config } = useSWR("/api/config", () =>
    apiGet<ConfigDetailResponse>("/api/config")
  );
  const version = config?.app?.values?.version as string | undefined;

  const renderLink = ({ href, label, icon: Icon }: typeof chatNav[number]) => {
    const isActive = pathname === href || pathname.startsWith(href + "/");
    return (
      <Link
        key={href}
        href={href}
        className={cn(
          "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
          isActive
            ? "bg-primary/12 text-primary"
            : "text-muted-foreground hover:bg-accent hover:text-foreground"
        )}
      >
        {isActive && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-primary" />
        )}
        <Icon className={cn(
          "h-4 w-4 shrink-0 transition-colors",
          isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
        )} />
        {label}
      </Link>
    );
  };

  const renderGroup = (label: string, items: typeof chatNav) => (
    <div className="space-y-0.5">
      <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
        {label}
      </p>
      {items.map(renderLink)}
    </div>
  );

  return (
    <aside className="hidden md:flex w-56 flex-col border-r border-border/60 bg-sidebar backdrop-blur-sm">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border/60 px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/12">
          <Shield className="h-3.5 w-3.5 text-primary" />
        </div>
        <span className="font-display text-base font-semibold tracking-tight">Squire</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-4 p-3 pt-4">
        {renderGroup("Chat", chatNav)}
        {renderGroup("Monitoring", monitorNav)}
        {renderGroup("System", systemNav)}

        {/* Version footer */}
        <div className="mt-auto px-3 pb-1">
          <p className="text-[10px] text-muted-foreground/50 font-medium tracking-wide">
            {version ? `v${version}` : ""}
          </p>
        </div>
      </nav>
    </aside>
  );
}
