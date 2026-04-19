"use client";

import { startTransition, useEffect, useState } from "react";
import { Moon, Sun, Menu, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from "@/components/ui/sheet";
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
  Eye,
  Wrench,
  Lightbulb,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/sessions", label: "Sessions", icon: History },
  { href: "/watch", label: "Watch", icon: Eye },
  { href: "/incidents", label: "Incidents", icon: Activity },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/skills", label: "Skills", icon: ListChecks },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/hosts", label: "Hosts", icon: Server },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/config", label: "Config", icon: Settings },
];

export function Header() {
  const [dark, setDark] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const stored = localStorage.getItem("squire-theme");
    const isDark = stored
      ? stored === "dark"
      : document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", isDark);
    startTransition(() => setDark(isDark));
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("squire-theme", next ? "dark" : "light");
  };

  return (
    <header className="flex h-12 items-center justify-between border-b border-border/60 bg-card/80 backdrop-blur-sm px-4">
      {/* Mobile menu */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetTrigger
          render={<Button variant="ghost" size="icon" className="md:hidden" />}
        >
          <Menu className="h-5 w-5" />
        </SheetTrigger>
        <SheetContent side="left" className="w-60 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          {/* Mobile brand */}
          <div className="flex h-14 items-center gap-2.5 border-b px-4">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/12">
              <Shield className="h-3.5 w-3.5 text-primary" />
            </div>
            <span className="font-display text-base font-semibold tracking-tight">Squire</span>
          </div>
          <nav className="space-y-0.5 p-3">
            {navItems.map(({ href, label, icon: Icon }) => {
              const isActive =
                pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMobileOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-primary/12 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </SheetContent>
      </Sheet>

      <div className="flex-1" />

      {/* Theme toggle */}
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleTheme}
        className="h-8 w-8 rounded-lg"
      >
        <span className="relative h-4 w-4">
          <Sun
            className={cn(
              "absolute inset-0 h-4 w-4 transition-all duration-300",
              dark ? "rotate-0 scale-100 opacity-100" : "rotate-90 scale-0 opacity-0"
            )}
          />
          <Moon
            className={cn(
              "absolute inset-0 h-4 w-4 transition-all duration-300",
              dark ? "-rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100"
            )}
          />
        </span>
      </Button>
    </header>
  );
}
