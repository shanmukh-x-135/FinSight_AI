"use client";

import {
  Activity, BarChart3, Binoculars, Bot, BriefcaseBusiness, Command, FileText,
  Funnel, History, LineChart, LogOut, Menu, Moon, Newspaper, PanelLeftClose,
  Search, Settings, Sun, Telescope, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { CommandPalette } from "@/components/command-palette";
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

const mobilePrimary = new Set(["/dashboard", "/market", "/watchlist", "/history", "/chat"]);

function isActive(pathname: string, href: string) {
  return pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`));
}

function initials(email?: string) {
  return email?.slice(0, 2).toUpperCase() ?? "FS";
}

export function AppShell({ children, email, isAdmin = false, onLogout }: { children: ReactNode; email?: string; isAdmin?: boolean; onLogout: () => void }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [dark, setDark] = useState(() => typeof window === "undefined" || window.localStorage.getItem("finsight-theme") !== "light");
  const visibleNavigation = useMemo(() => isAdmin ? [...navigation, { href: "/operations", label: "Operations", icon: Activity }] : [...navigation], [isAdmin]);
  const activeRoute = visibleNavigation.find((item) => isActive(pathname, item.href));

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((value) => !value);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function toggleTheme() {
    setDark((current) => {
      window.localStorage.setItem("finsight-theme", current ? "light" : "dark");
      return !current;
    });
  }

  const navLinks = (mobile = false) => visibleNavigation.map((item) => {
    const active = isActive(pathname, item.href);
    const Icon = item.icon;
    return (
      <Link key={item.href} href={item.href} onClick={mobile ? () => setMobileOpen(false) : undefined} aria-current={active ? "page" : undefined} title={!mobile && collapsed ? item.label : undefined} className={cn("group flex items-center gap-3 rounded-lg text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", mobile ? "h-11 px-3" : "h-9 px-2.5", active ? "bg-primary/12 font-medium text-primary" : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-foreground")}>
        <Icon className="size-4 shrink-0" aria-hidden />
        {(mobile || !collapsed) && <span>{item.label}</span>}
        {active && <span className={cn("ml-auto size-1.5 rounded-full bg-primary", !mobile && collapsed && "hidden")} aria-hidden />}
      </Link>
    );
  });

  return (
    <div className={cn("min-h-screen bg-background text-foreground", dark && "dark")}>
      <div className="min-h-screen bg-background text-foreground">
        <aside className={cn("fixed inset-y-0 left-0 z-40 hidden bg-sidebar lg:flex lg:flex-col", collapsed ? "w-[4.5rem]" : "w-60")}>
          <div className="flex h-16 items-center px-4">
            <Link href="/dashboard" className="flex min-w-0 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-xs font-black text-primary-foreground shadow-sm shadow-primary/20">F</span>{!collapsed && <span className="truncate text-sm font-semibold tracking-tight">FinSight <span className="text-primary">AI</span></span>}</Link>
          </div>
          <div className="px-3 pb-3">
            <button type="button" onClick={() => setCommandOpen(true)} className={cn("flex h-9 w-full items-center gap-2 rounded-lg bg-sidebar-accent/65 px-2.5 text-xs text-muted-foreground outline-none transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring", collapsed && "justify-center px-0")} aria-label="Open command palette"><Search className="size-3.5 shrink-0" aria-hidden />{!collapsed && <><span className="truncate">Search or jump to</span><kbd className="ml-auto rounded border border-sidebar-border px-1.5 py-0.5 font-mono text-[9px]">⌘K</kbd></>}</button>
          </div>
          <nav aria-label="Primary navigation" className="flex-1 space-y-1 overflow-y-auto px-3 py-1">{navLinks()}</nav>
          <div className="space-y-1 px-3 pb-3 pt-2">
            <Link href="/settings" className={cn("flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm text-muted-foreground outline-none hover:bg-sidebar-accent/70 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring", isActive(pathname, "/settings") && "bg-primary/12 text-primary")}><Settings className="size-4 shrink-0" aria-hidden />{!collapsed && "Settings"}</Link>
            <button type="button" onClick={onLogout} className="flex h-9 w-full items-center gap-3 rounded-lg px-2.5 text-sm text-muted-foreground outline-none hover:bg-negative/10 hover:text-negative focus-visible:ring-2 focus-visible:ring-negative"><LogOut className="size-4 shrink-0" aria-hidden />{!collapsed && "Log out"}</button>
            {!collapsed && <div className="mt-3 flex items-center gap-2.5 border-t border-sidebar-border/70 px-1 pt-3"><span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/12 text-[10px] font-bold text-primary">{initials(email)}</span><div className="min-w-0"><p className="truncate text-xs font-medium text-sidebar-foreground">Research account</p><p className="truncate text-[10px] text-muted-foreground">{email}</p></div></div>}
          </div>
        </aside>

        <div className={cn("min-h-screen min-w-0 transition-[padding] duration-200 motion-reduce:transition-none", collapsed ? "lg:pl-[4.5rem]" : "lg:pl-60")}>
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border/45 bg-background/88 px-4 backdrop-blur-xl sm:px-6 lg:h-16">
            <div className="flex min-w-0 items-center gap-3"><Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu className="size-4" /></Button><Button variant="ghost" size="icon-sm" className="hidden lg:inline-flex" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}><PanelLeftClose className={cn("size-4 transition-transform", collapsed && "rotate-180")} /></Button><div className="min-w-0"><p className="truncate text-sm font-medium">{isActive(pathname, "/settings") ? "Settings" : activeRoute?.label ?? "FinSight AI"}</p><p className="hidden text-[10px] text-muted-foreground sm:block">End-of-day intelligence · evidence first</p></div></div>
            <div className="flex items-center gap-1.5"><Button variant="ghost" size="sm" className="hidden gap-2 text-xs text-muted-foreground sm:inline-flex" onClick={() => setCommandOpen(true)}><Command className="size-3.5" />Quick actions <kbd className="rounded border border-border/70 px-1 font-mono text-[9px]">⌘K</kbd></Button><Button variant="ghost" size="icon-sm" onClick={toggleTheme} aria-label={dark ? "Use light theme" : "Use dark theme"}>{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}</Button><Link href="/settings" aria-label="Open account settings" className="grid size-8 place-items-center rounded-full bg-primary/12 text-[10px] font-bold text-primary outline-none focus-visible:ring-2 focus-visible:ring-ring">{initials(email)}</Link></div>
          </header>
          <main className="mx-auto w-full min-w-0 max-w-[1680px] px-4 py-5 pb-24 sm:px-6 sm:py-6 lg:px-8 lg:pb-10">{children}</main>
        </div>

        <nav aria-label="Mobile primary navigation" className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-border/60 bg-background/94 px-1 pb-[max(.35rem,env(safe-area-inset-bottom))] pt-1 backdrop-blur-xl lg:hidden">
          {visibleNavigation.filter((item) => mobilePrimary.has(item.href)).map((item) => { const active = isActive(pathname, item.href); const Icon = item.icon; return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={cn("flex min-w-0 flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[10px] text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring", active && "bg-primary/10 font-medium text-primary")}><Icon className="size-4" aria-hidden /><span className="truncate">{item.label}</span></Link>; })}
        </nav>

        {mobileOpen && <div className="fixed inset-0 z-[70] bg-slate-950/70 backdrop-blur-sm lg:hidden" onMouseDown={() => setMobileOpen(false)}><aside role="dialog" aria-modal="true" aria-label="Application navigation" className="flex h-full w-[min(22rem,88vw)] flex-col bg-sidebar p-3 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex h-12 items-center justify-between px-2"><Link href="/dashboard" className="flex items-center gap-2.5 font-semibold"><span className="grid size-8 place-items-center rounded-lg bg-primary text-xs font-black text-primary-foreground">F</span>FinSight AI</Link><Button variant="ghost" size="icon-sm" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-4" /></Button></div><button type="button" onClick={() => { setMobileOpen(false); setCommandOpen(true); }} className="my-3 flex h-10 items-center gap-2 rounded-lg bg-sidebar-accent/70 px-3 text-xs text-muted-foreground"><Search className="size-4" />Search or quick action</button><nav aria-label="All navigation" className="flex-1 space-y-1 overflow-y-auto">{navLinks(true)}</nav><div className="border-t border-sidebar-border pt-2"><Link href="/settings" className="flex h-11 items-center gap-3 rounded-lg px-3 text-sm text-muted-foreground"><Settings className="size-4" />Settings</Link><button type="button" onClick={onLogout} className="flex h-11 w-full items-center gap-3 rounded-lg px-3 text-sm text-negative"><LogOut className="size-4" />Log out</button></div></aside></div>}
        <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
      </div>
    </div>
  );
}
