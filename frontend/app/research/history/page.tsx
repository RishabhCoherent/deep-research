"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Layers,
  FileText,
  Globe,
  BarChart3,
  Trash2,
  Loader2,
  Inbox,
  ArrowRight,
  Cpu,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ResearchLayout } from "@/components/ResearchLayout";
import {
  getLegacyHistoryDirect,
  getAgenticHistoryDirect,
  deleteLegacyHistoryDirect,
  deleteAgenticHistoryDirect,
} from "@/lib/api";
import type { ResearchHistoryItem } from "@/lib/types";
import type { Backend2HistoryItem } from "@/lib/types-backend2";

// Discriminated union — one card type per source.
type MergedItem =
  | (ResearchHistoryItem & { source: "legacy" })
  | Backend2HistoryItem;

export default function ResearchHistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<MergedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [legacyRes, agenticRes] = await Promise.allSettled([
        getLegacyHistoryDirect(),
        getAgenticHistoryDirect(),
      ]);

      const legacy: MergedItem[] =
        legacyRes.status === "fulfilled"
          ? legacyRes.value.map((i) => ({ ...i, source: "legacy" as const }))
          : [];
      const agentic: MergedItem[] =
        agenticRes.status === "fulfilled" ? agenticRes.value : [];

      const merged = [...legacy, ...agentic].sort((a, b) => {
        const ta = Date.parse(a.saved_at) || 0;
        const tb = Date.parse(b.saved_at) || 0;
        return tb - ta;
      });
      if (!cancelled) {
        setItems(merged);
        setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleDelete(item: MergedItem) {
    setDeleting(item.id);
    try {
      if (item.source === "agentic") {
        await deleteAgenticHistoryDirect(item.id);
      } else {
        await deleteLegacyHistoryDirect(item.id);
      }
      setItems((prev) => prev.filter((i) => !(i.id === item.id && i.source === item.source)));
    } catch {
      // silently fail
    } finally {
      setDeleting(null);
    }
  }

  function openDetail(item: MergedItem) {
    if (item.source === "agentic") {
      router.push(`/research/history/${item.id}?source=agentic`);
    } else {
      router.push(`/research/history/${item.id}`);
    }
  }

  return (
    <ResearchLayout>
      {/* Header */}
      <div
        className={`mb-12 transition-all duration-700 ${
          isVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-8"
        }`}
      >
        <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-4">
          <span className="w-8 h-px bg-foreground/30" />
          Research History · all backends
        </span>
        <div className="flex items-center gap-3">
          <h1 className="text-3xl lg:text-4xl font-display leading-[1.1] tracking-tight">
            Past research
          </h1>
          {!loading && items.length > 0 && (
            <span className="rounded-full bg-foreground/5 px-3 py-1 text-xs font-mono text-muted-foreground">
              {items.length}
            </span>
          )}
        </div>
        <p className="mt-3 text-base text-muted-foreground">
          Browse and review your completed research results. Items from the
          legacy 3-layer backend and the agentic backend2 are merged.
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-foreground/5 mb-6">
            <Inbox className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="font-display text-xl mb-2">No research yet</h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm">
            Completed research will appear here automatically.
          </p>
          <button
            onClick={() => router.push("/research")}
            className="inline-flex items-center gap-2 bg-foreground hover:bg-foreground/90 text-background rounded-full px-6 h-12 text-sm font-medium group transition-colors"
          >
            Start Research
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </button>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item, index) => (
            <div
              key={`${item.source}-${item.id}`}
              onClick={() => openDetail(item)}
              className="glass-card hover-lift cursor-pointer rounded-2xl p-6 group animate-fade-in-up"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              {/* Source badge + delete */}
              <div className="flex items-center justify-between mb-3">
                <SourceBadge source={item.source} />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(item);
                  }}
                  disabled={deleting === item.id}
                  className="shrink-0 rounded-full p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors opacity-0 group-hover:opacity-100"
                >
                  {deleting === item.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>

              {/* Topic */}
              <h3 className="font-display text-lg text-foreground line-clamp-2 mb-3 leading-snug">
                {item.topic || <span className="text-muted-foreground italic">untitled</span>}
              </h3>

              {/* Date */}
              {item.saved_at && (
                <p className="font-mono text-xs text-muted-foreground mb-4">
                  {new Date(item.saved_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}
                  {" at "}
                  {new Date(item.saved_at).toLocaleTimeString("en-US", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              )}

              {/* Source-specific stats */}
              {item.source === "legacy" ? (
                <div className="grid grid-cols-2 gap-3">
                  <MiniStat
                    icon={<Layers className="h-3 w-3" />}
                    label="Layers"
                    value={item.layer_count}
                  />
                  <MiniStat
                    icon={<FileText className="h-3 w-3" />}
                    label="Words"
                    value={item.total_words.toLocaleString()}
                  />
                  <MiniStat
                    icon={<Globe className="h-3 w-3" />}
                    label="Sources"
                    value={item.total_sources}
                  />
                  <MiniStat
                    icon={<BarChart3 className="h-3 w-3" />}
                    label="Score"
                    value={`${item.avg_score}/10`}
                  />
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <MiniStat
                    icon={<FileText className="h-3 w-3" />}
                    label="Words"
                    value={item.word_count.toLocaleString()}
                  />
                  <MiniStat
                    icon={<BarChart3 className="h-3 w-3" />}
                    label="Clusters"
                    value={item.n_dimensional_clusters}
                  />
                  <MiniStat
                    icon={<Globe className="h-3 w-3" />}
                    label="Claims"
                    value={item.n_validated_claims}
                  />
                  <MiniStat
                    icon={<ShieldCheck className="h-3 w-3" />}
                    label="Grounding"
                    value={
                      item.grounding_score != null
                        ? `${Math.round(item.grounding_score * 100)}%`
                        : "—"
                    }
                  />
                </div>
              )}

              {/* Status footer */}
              <div className="mt-4 pt-3 border-t border-foreground/5 flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  {item.source === "agentic"
                    ? item.is_complete
                      ? "complete"
                      : `at ${item.latest_node || "—"}`
                    : "complete"}
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-all group-hover:translate-x-1" />
              </div>
            </div>
          ))}
        </div>
      )}
    </ResearchLayout>
  );
}

function SourceBadge({ source }: { source: "legacy" | "agentic" }) {
  if (source === "agentic") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-purple/10 text-purple border border-purple/20">
        <Cpu className="h-3 w-3" />
        agentic
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-foreground/5 text-muted-foreground border border-foreground/10">
      <Layers className="h-3 w-3" />
      legacy
    </span>
  );
}

function MiniStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-foreground/5 px-2.5 py-2">
      <span className="text-muted-foreground">{icon}</span>
      <div className="min-w-0">
        <p className="text-[9px] font-mono text-muted-foreground uppercase tracking-wide">
          {label}
        </p>
        <p className={cn("text-xs font-display text-foreground truncate")}>
          {value}
        </p>
      </div>
    </div>
  );
}
