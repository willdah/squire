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
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-primary/10 text-primary border-l-[3px] border-primary"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground border-l-[3px] border-transparent"
        )}
      >
        <Icon className="h-4 w-4" />
        {label}
      </Link>
    );
  };

  const renderGroup = (label: string, items: typeof chatNav) => (
    <>
      <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <div className="space-y-1">
        {items.map(renderLink)}
      </div>
    </>
  );

  return (
    <aside className="hidden md:flex w-56 flex-col border-r bg-card">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <span className="font-semibold text-lg tracking-tight">Squire</span>
      </div>
      <nav className="flex-1 flex flex-col p-2">
        {renderGroup("Chat", chatNav)}
        <div className="my-3 mx-3 border-t" />
        {renderGroup("Monitoring", monitorNav)}
        <div className="my-3 mx-3 border-t" />
        {renderGroup("System", systemNav)}

        <div className="mt-auto px-3 py-3">
          <p className="text-[10px] text-muted-foreground">
            Squire{version ? ` v${version}` : ""}
          </p>
        </div>
      </nav>
    </aside>
  );
}
