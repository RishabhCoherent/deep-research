"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Search,
  Clock,
  Home,
  Brain,
  History,
} from "lucide-react";
import { useHealth } from "@/hooks/useHealth";

export function Sidebar() {
  const pathname = usePathname();
  const { health, loading } = useHealth();

  const isResearch = pathname.startsWith("/research") && !pathname.startsWith("/research/history");
  const isHistory = pathname.startsWith("/research/history");

  return (
    <aside className="noise-overlay flex h-full w-72 flex-col border-r border-foreground/10 bg-surface-1">
      <div className="flex items-center border-b border-foreground/10 px-5 py-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-display tracking-tight">CoherentBot</span>
        </Link>
      </div>

      <div className="border-b border-foreground/10 px-5 py-4">
        <nav className="space-y-1">
          <NavLink
            href="/"
            icon={<Home className="h-3.5 w-3.5" />}
            label="Home"
            active={pathname === "/"}
          />
          <NavLink
            href="/research"
            icon={<Brain className="h-3.5 w-3.5" />}
            label="Research Agent"
            active={isResearch}
          />
          <NavLink
            href="/research/history"
            icon={<History className="h-3.5 w-3.5" />}
            label="Research History"
            active={isHistory}
          />
        </nav>
      </div>

      <div className="border-b border-foreground/10 px-5 py-4">
        <h3 className="mb-3 flex items-center gap-2 text-xs font-mono font-semibold uppercase tracking-wider text-muted-foreground">
          <Activity className="h-3.5 w-3.5" /> Status
        </h3>
        <div className="space-y-2">
          <StatusRow
            label="OpenAI"
            ok={health?.openai ?? false}
            loading={loading}
          />
          <StatusRow
            label="Tavily"
            ok={health?.tavily ?? false}
            loading={loading}
            fallback="SearXNG / DDG fallback"
          />
          <StatusRow
            label="SearXNG"
            ok={health?.searxng ?? false}
            loading={loading}
          />
        </div>
      </div>

      <div className="mt-auto px-5 py-4">
        <div className="rounded-xl bg-surface-2/50 p-3">
          <div className="flex items-center gap-2 text-[11px] text-warm-gray">
            <Clock className="h-3 w-3" />
            <span>3-layer research: 3-8 min</span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-warm-gray">
            <Search className="h-3 w-3" />
            <span>Baseline only: ~30 sec</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function NavLink({
  href,
  icon,
  label,
  active,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-mono font-medium tracking-wide transition-colors ${
        active
          ? "bg-purple/15 text-orange"
          : "text-warm-gray hover:bg-surface-2 hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </Link>
  );
}

function StatusRow({
  label,
  ok,
  loading,
  fallback,
}: {
  label: string;
  ok: boolean;
  loading: boolean;
  fallback?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      {loading ? (
        <span className="h-2 w-2 animate-pulse rounded-full bg-warm-gray" />
      ) : ok ? (
        <span className="flex items-center gap-1.5 text-[11px] text-success font-medium">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          Connected
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-[11px] text-warning font-medium">
          <span className="h-1.5 w-1.5 rounded-full bg-warning" />
          {fallback || "Missing"}
        </span>
      )}
    </div>
  );
}
