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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ResearchLayout } from "@/components/ResearchLayout";
import { getResearchHistory, deleteResearchHistory } from "@/lib/api";
import type { ResearchHistoryItem } from "@/lib/types";

export default function ResearchHistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<ResearchHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    getResearchHistory()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(id: string) {
    setDeleting(id);
    try {
      await deleteResearchHistory(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch {
      // silently fail
    } finally {
      setDeleting(null);
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
          Research History
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
          Browse and review your completed research results.
        </p>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty State */}
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

      {/* History Grid */}
      {!loading && items.length > 0 && (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item, index) => (
            <div
              key={item.id}
              onClick={() => router.push(`/research/history/${item.id}`)}
              className="glass-card hover-lift cursor-pointer rounded-2xl p-6 group animate-fade-in-up"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              {/* Topic + Delete */}
              <div className="flex items-start justify-between mb-4">
                <h3 className="font-display text-lg text-foreground line-clamp-2 flex-1 mr-3 leading-snug">
                  {item.topic}
                </h3>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(item.id);
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

              {/* Date */}
              <p className="font-mono text-xs text-muted-foreground mb-4">
                {new Date(item.saved_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}{" "}
                at{" "}
                {new Date(item.saved_at).toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </p>

              {/* Stats Grid */}
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
            </div>
          ))}
        </div>
      )}
    </ResearchLayout>
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
        <p className="text-xs font-display text-foreground truncate">
          {value}
        </p>
      </div>
    </div>
  );
}
