"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Brain,
  Layers,
  FileText,
  Globe,
  BarChart3,
  Trash2,
  Loader2,
  Inbox,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Sidebar } from "@/components/Sidebar";
import { getResearchHistory, deleteResearchHistory } from "@/lib/api";
import type { ResearchHistoryItem } from "@/lib/types";

export default function ResearchHistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<ResearchHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

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
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-5xl animate-fade-in-up">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple/20">
                <Brain className="h-5 w-5 text-orange" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">
                Research History
              </h2>
              {!loading && items.length > 0 && (
                <span className="rounded-full bg-surface-3 px-2.5 py-0.5 text-xs font-medium text-warm-gray">
                  {items.length}
                </span>
              )}
            </div>
            <p className="text-sm text-warm-gray">
              Browse and review your past research results.
            </p>
          </div>

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-warm-gray" />
            </div>
          )}

          {/* Empty State */}
          {!loading && items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-2 mb-4">
                <Inbox className="h-8 w-8 text-warm-gray" />
              </div>
              <h3 className="text-sm font-semibold text-foreground mb-1">
                No research history yet
              </h3>
              <p className="text-xs text-warm-gray mb-4">
                Completed research will appear here automatically.
              </p>
              <button
                onClick={() => router.push("/research")}
                className="rounded-lg gradient-brand px-4 py-2 text-xs font-semibold text-white hover:opacity-90 transition-opacity"
              >
                Start Research
              </button>
            </div>
          )}

          {/* History Grid */}
          {!loading && items.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((item) => (
                <div
                  key={item.id}
                  onClick={() =>
                    router.push(`/research/history/${item.id}`)
                  }
                  className="glass-card-hover cursor-pointer p-5 transition-all hover:shadow-lg"
                >
                  {/* Topic + Delete */}
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-sm font-semibold text-foreground line-clamp-2 flex-1 mr-2 leading-snug">
                      {item.topic}
                    </h3>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(item.id);
                      }}
                      disabled={deleting === item.id}
                      className="flex-shrink-0 rounded-lg p-1.5 text-warm-gray hover:text-error hover:bg-error/10 transition-colors"
                    >
                      {deleting === item.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>

                  {/* Date */}
                  <p className="text-[11px] text-warm-gray mb-3">
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
                  <div className="grid grid-cols-2 gap-2">
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
        </div>
      </main>
    </div>
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
    <div className="flex items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5">
      <span className="text-warm-gray">{icon}</span>
      <div className="min-w-0">
        <p className="text-[9px] text-warm-gray uppercase tracking-wide">
          {label}
        </p>
        <p className="text-xs font-semibold text-foreground truncate">
          {value}
        </p>
      </div>
    </div>
  );
}
