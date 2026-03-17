"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import {
  Activity,
  Search,
  Settings,
  FileText,
  Clock,
  Home,
  Brain,
  History,
} from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { useWizardStore } from "@/lib/store";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function Sidebar() {
  const pathname = usePathname();
  const { health, loading } = useHealth();
  const reportTitle = useWizardStore((s) => s.reportTitle);
  const sectionPlans = useWizardStore((s) => s.sectionPlans);
  const skipContent = useWizardStore((s) => s.skipContent);
  const topicOverride = useWizardStore((s) => s.topicOverride);
  const setSkipContent = useWizardStore((s) => s.setSkipContent);
  const setTopicOverride = useWizardStore((s) => s.setTopicOverride);

  const isWizard = ["/upload", "/extract", "/generate", "/download"].some((p) =>
    pathname.startsWith(p)
  );
  const isResearch = pathname.startsWith("/research") && !pathname.startsWith("/research/history");
  const isHistory = pathname.startsWith("/research/history");

  return (
    <aside className="flex h-full w-72 flex-col border-r border-surface-3 bg-surface-1">
      {/* Logo */}
      <div className="flex items-center border-b border-surface-3 px-5 py-5">
        <Image
          src="/cmi-logo.svg"
          alt="Coherent Market Insights"
          width={210}
          height={50}
          className="h-10 w-auto"
          priority
        />
      </div>

      {/* Navigation */}
      <div className="border-b border-surface-3 px-5 py-4">
        <nav className="space-y-1">
          <NavLink
            href="/"
            icon={<Home className="h-3.5 w-3.5" />}
            label="Home"
            active={pathname === "/"}
          />
          <NavLink
            href="/upload"
            icon={<FileText className="h-3.5 w-3.5" />}
            label="Report Generator"
            active={isWizard}
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

      {/* API Status */}
      <div className="border-b border-surface-3 px-5 py-4">
        <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-warm-gray">
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

      {/* Generation Settings (wizard context) */}
      {isWizard && (
        <div className="border-b border-surface-3 px-5 py-4">
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-warm-gray">
            <Settings className="h-3.5 w-3.5" /> Settings
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Label
                htmlFor="skip-content"
                className="text-xs text-muted-foreground cursor-pointer"
              >
                Charts only (skip LLM)
              </Label>
              <Switch
                id="skip-content"
                checked={skipContent}
                onCheckedChange={setSkipContent}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="topic" className="text-xs text-muted-foreground">
                Topic override
              </Label>
              <Input
                id="topic"
                placeholder="Auto-detect from TOC"
                value={topicOverride}
                onChange={(e) => setTopicOverride(e.target.value)}
                className="h-8 bg-surface-2 text-xs"
              />
            </div>
          </div>
        </div>
      )}

      {/* Report Info (wizard context) */}
      {isWizard && reportTitle && (
        <div className="border-b border-surface-3 px-5 py-4">
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-warm-gray">
            <FileText className="h-3.5 w-3.5" /> Report
          </h3>
          <p className="text-xs text-foreground font-medium leading-relaxed">
            {reportTitle}
          </p>
          {sectionPlans.length > 0 && (
            <p className="mt-1 text-[11px] text-warm-gray">
              {sectionPlans.length} sections
            </p>
          )}
        </div>
      )}

      {/* Bottom info */}
      <div className="mt-auto px-5 py-4">
        <div className="rounded-xl bg-surface-2/50 p-3">
          <div className="flex items-center gap-2 text-[11px] text-warm-gray">
            <Clock className="h-3 w-3" />
            <span>Full report: 15-30 min</span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-warm-gray">
            <Search className="h-3 w-3" />
            <span>Charts only: ~1 min</span>
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
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
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
