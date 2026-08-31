"use client";

import {
  BarChart3,
  Activity,
  Binoculars,
  Bot,
  BriefcaseBusiness,
  ChevronRight,
  FileText,
  Funnel,
  History,
  LineChart,
  LogOut,
  Moon,
  Newspaper,
  PanelLeftClose,
  Settings,
  Sun,
  Telescope,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/dashboard", label: "Overview", icon: BarChart3 },
  { href: "/market", label: "Market", icon: Binoculars },
  { href: "/news", label: "News", icon: Newspaper },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness },
  { href: "/watchlist", label: "Watchlist", icon: Telescope },
  { href: "/history", label: "Research", icon: History },
  { href: "/strategies", label: "Strategies", icon: LineChart },
  { href: "/discover", label: "Discover", icon: Funnel },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/chat", label: "AI", icon: Bot },
] as const;

function isActive(pathname: string, href: string) {
  return pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`));
}

export function AppShell({ children, email, isAdmin = false, onLogout }: { children: ReactNode; email?: string; isAdmin?: boolean; onLogout: () => void }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(true);
  const visibleNavigation = isAdmin ? [...navigation, { href: "/operations", label: "Operations", icon: Activity }] : navigation;

  function toggleTheme() {
    setDark((current) => !current);
  }

  return (
    <div className={cn("min-h-screen bg-background text-foreground", dark && "dark")}>
      <div className="min-h-screen bg-background text-foreground">
        <aside className={cn("fixed inset-y-0 left-0 z-40 hidden border-r border-border/70 bg-sidebar/95 backdrop-blur lg:flex lg:flex-col", collapsed ? "w-16" : "w-52")}>
          <div className="flex h-14 items-center border-b border-border/70 px-3">
            <Link href="/dashboard" className="flex min-w-0 items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-primary">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-xs font-black text-primary-foreground">F</span>
              {!collapsed && <span className="truncate text-sm font-semibold tracking-tight">FinSight <span className="text-primary">AI</span></span>}
            </Link>
          </div>
          <nav aria-label="Primary navigation" className="flex-1 space-y-1 p-2">
            {visibleNavigation.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined} className={cn("group flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring", active && "bg-primary/10 font-medium text-primary")}><Icon className="size-4 shrink-0" aria-hidden />{!collapsed && <span>{item.label}</span>}{active && !collapsed && <ChevronRight className="ml-auto size-3.5" aria-hidden />}</Link>;
            })}
          </nav>
          <div className="space-y-1 border-t border-border/70 p-2">
            <Link href="/settings" className={cn("flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground", isActive(pathname, "/settings") && "bg-primary/10 text-primary")}><Settings className="size-4" />{!collapsed && "Settings"}</Link>
            <button type="button" onClick={onLogout} className="flex h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-sm text-muted-foreground hover:bg-negative/10 hover:text-negative"><LogOut className="size-4" />{!collapsed && "Log out"}</button>
          </div>
        </aside>

        <div className={cn("min-h-screen min-w-0 transition-[padding]", collapsed ? "lg:pl-16" : "lg:pl-52")}>
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border/70 bg-background/90 px-4 backdrop-blur-xl sm:px-6">
            <div className="flex items-center gap-3">
              <Link href="/dashboard" className="flex items-center gap-2 lg:hidden"><span className="grid size-7 place-items-center rounded-md bg-primary text-xs font-black text-primary-foreground">F</span><span className="text-sm font-semibold">FinSight AI</span></Link>
              <Button variant="ghost" size="icon-sm" className="hidden lg:inline-flex" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}><PanelLeftClose className={cn("size-4 transition-transform", collapsed && "rotate-180")} /></Button>
              <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex"><span className="size-1.5 rounded-full bg-positive" aria-hidden /><span>End-of-day research workspace</span></div>
            </div>
            <div className="flex items-center gap-2">
              {email && <span className="hidden max-w-56 truncate text-xs text-muted-foreground md:block">{email}</span>}
              <Button variant="ghost" size="icon-sm" onClick={toggleTheme} aria-label={dark ? "Use light theme" : "Use dark theme"}>{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}</Button>
            </div>
          </header>
          <main className="mx-auto w-full min-w-0 max-w-[1600px] px-4 py-5 pb-24 sm:px-6 lg:pb-8">{children}</main>
        </div>

        <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-50 flex overflow-x-auto border-t border-border/80 bg-background/95 px-2 pb-[max(.4rem,env(safe-area-inset-bottom))] pt-1.5 backdrop-blur-xl lg:hidden">
          {visibleNavigation.map((item) => { const active = isActive(pathname, item.href); const Icon = item.icon; return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={cn("flex min-w-[4.25rem] flex-1 flex-col items-center gap-0.5 rounded-md px-2 py-1.5 text-[10px] text-muted-foreground", active && "bg-primary/10 text-primary")}><Icon className="size-4" aria-hidden /><span>{item.label}</span></Link>; })}
        </nav>
      </div>
    </div>
  );
}
