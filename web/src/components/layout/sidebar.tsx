"use client";

import { Suspense, useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
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
  FileText,
  Lightbulb,
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
  { href: "/incidents", label: "Incidents", icon: Activity },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/watch-explorer", label: "Watch Explorer", icon: FileText },
  { href: "/activity", label: "Activity", icon: Activity },
];

const systemNav = [
  { href: "/skills", label: "Skills", icon: ListChecks },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/hosts", label: "Hosts", icon: Server },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/config", label: "Config", icon: Settings },
];

const STORAGE_KEY = "squire_last_url_by_section";

type NavItem = (typeof chatNav)[number];

/**
 * Remembers the last full URL (path + search) visited within each top-level
 * section, stored in sessionStorage. Clicking a sidebar link for a section
 * then resolves to the stored URL so the user lands back in the same
 * tab/filter they left.
 */
function useSectionMemory(): (href: string) => string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const mapRef = useRef<Record<string, string>>({});

  // Hydrate from sessionStorage on mount.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) mapRef.current = JSON.parse(raw);
    } catch {
      mapRef.current = {};
    }
  }, []);

  // Record the current URL for its owning section whenever path or query changes.
  useEffect(() => {
    const sections = [...chatNav, ...monitorNav, ...systemNav].map((i) => i.href);
    const section = sections.find((href) => pathname === href || pathname.startsWith(href + "/"));
    if (!section) return;
    const qs = searchParams.toString();
    const full = qs ? `${pathname}?${qs}` : pathname;
    mapRef.current = { ...mapRef.current, [section]: full };
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(mapRef.current));
    } catch {
      // sessionStorage may be unavailable (private mode, etc.) — fall through
    }
  }, [pathname, searchParams]);

  return useCallback((href: string) => mapRef.current[href] ?? href, []);
}

function SidebarNav() {
  const pathname = usePathname();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const resolve = useSectionMemory();

  const renderLink = ({ href, label, icon: Icon }: NavItem) => {
    // Active state keys off pathname only, so the highlight stays correct
    // regardless of which sub-state the resolved href points at.
    const isActive = mounted && (pathname === href || pathname.startsWith(href + "/"));
    return (
      <Link
        key={href}
        href={resolve(href)}
        className={cn(
          "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
          isActive
            ? "bg-primary/12 text-primary"
            : "text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
      >
        {isActive && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-primary" />
        )}
        <Icon
          className={cn(
            "h-4 w-4 shrink-0 transition-colors",
            isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
          )}
        />
        {label}
      </Link>
    );
  };

  const renderGroup = (label: string, items: NavItem[]) => (
    <div className="space-y-0.5">
      <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
        {label}
      </p>
      {items.map(renderLink)}
    </div>
  );

  return (
    <>
      {renderGroup("Chat", chatNav)}
      {renderGroup("Monitoring", monitorNav)}
      {renderGroup("System", systemNav)}
    </>
  );
}

function SidebarNavFallback() {
  // Bare nav rendered while SidebarNav suspends on useSearchParams.
  const items: [string, NavItem[]][] = [
    ["Chat", chatNav],
    ["Monitoring", monitorNav],
    ["System", systemNav],
  ];
  return (
    <>
      {items.map(([label, group]) => (
        <div key={label} className="space-y-0.5">
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
            {label}
          </p>
          {group.map(({ href, label: itemLabel, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-all duration-200 hover:bg-accent hover:text-foreground"
            >
              <Icon className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground" />
              {itemLabel}
            </Link>
          ))}
        </div>
      ))}
    </>
  );
}

export function Sidebar() {
  const { data: config } = useSWR("/api/config", () => apiGet<ConfigDetailResponse>("/api/config"));
  const version = config?.app?.values?.version as string | undefined;

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
        <Suspense fallback={<SidebarNavFallback />}>
          <SidebarNav />
        </Suspense>

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
