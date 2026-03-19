"use client";

import { useEffect, useState } from "react";
import { Moon, Sun, Menu } from "lucide-react";
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
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/sessions", label: "Sessions", icon: History },
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
    if (stored) {
      const isDark = stored === "dark";
      setDark(isDark);
      document.documentElement.classList.toggle("dark", isDark);
    } else {
      const isDark = document.documentElement.classList.contains("dark");
      setDark(isDark);
    }
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("squire-theme", next ? "dark" : "light");
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-4">
      {/* Mobile menu */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetTrigger
          render={<Button variant="ghost" size="icon" className="md:hidden" />}
        >
          <Menu className="h-5 w-5" />
        </SheetTrigger>
        <SheetContent side="left" className="w-56 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <nav className="space-y-1 p-4 pt-10">
            {navItems.map(({ href, label, icon: Icon }) => {
              const isActive =
                pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMobileOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
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

      <Button variant="ghost" size="icon" onClick={toggleTheme}>
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
