"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  Server,
  Bell,
  Settings,
  Activity,
  History,
  ListChecks,
} from "lucide-react";
import { cn } from "@/lib/utils";

const mainNav = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/sessions", label: "Sessions", icon: History },
  { href: "/skills", label: "Skills", icon: ListChecks },
];

const systemNav = [
  { href: "/hosts", label: "Hosts", icon: Server },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/config", label: "Config", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  const renderLink = ({ href, label, icon: Icon }: typeof mainNav[number]) => {
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

  return (
    <aside className="hidden md:flex w-56 flex-col border-r bg-card">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <span className="font-semibold text-lg tracking-tight">Squire</span>
      </div>
      <nav className="flex-1 flex flex-col p-2">
        <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Navigation
        </p>
        <div className="space-y-1">
          {mainNav.map(renderLink)}
        </div>

        <div className="my-3 mx-3 border-t" />

        <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          System
        </p>
        <div className="space-y-1">
          {systemNav.map(renderLink)}
        </div>

        <div className="mt-auto px-3 py-3">
          <p className="text-[10px] text-muted-foreground">Squire v0.4</p>
        </div>
      </nav>
    </aside>
  );
}
