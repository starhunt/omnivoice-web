"use client";

import { useEffect, useMemo, useState } from "react";
import { Search, Trash2, Wand2 } from "lucide-react";
import { api, audioUrlFor } from "@/lib/api";
import type { Generation } from "@/lib/types";

export default function HistoryPage() {
  const [rows, setRows] = useState<Generation[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [cleanupBusy, setCleanupBusy] = useState(false);

  const staleCount = useMemo(() => rows.filter((r) => r.status === "running").length, [rows]);

  const load = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set("q", q.trim());
      qs.set("limit", "100");
      setRows(await api.listGenerations(qs));
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = async (g: Generation) => {
    const preview = g.text.slice(0, 40);
    if (!window.confirm(`삭제하시겠습니까?\n\n"${preview}${g.text.length > 40 ? "…" : ""}"`)) {
      return;
    }
    setBusyId(g.id);
    try {
      await api.deleteGeneration(g.id);
      setRows((prev) => prev.filter((r) => r.id !== g.id));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleCleanupStale = async () => {
    if (!window.confirm(`running 상태로 남은 ${staleCount}건을 실패(중단) 처리하시겠습니까?`)) {
      return;
    }
    setCleanupBusy(true);
    try {
      const { finalized } = await api.cleanupStaleGenerations();
      await load();
      setErr(null);
      window.alert(`${finalized}건 정리 완료.`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setCleanupBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">히스토리</h1>
        <p className="text-sm text-muted-foreground">과거 생성 결과를 검색·재생·재현합니다.</p>
      </header>

      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            className="input pl-9"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="텍스트 검색"
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <button type="button" onClick={load} className="btn-outline">
          검색
        </button>
        {staleCount > 0 && (
          <button
            type="button"
            onClick={handleCleanupStale}
            disabled={cleanupBusy}
            className="btn-outline flex items-center gap-1 text-amber-600 disabled:opacity-50"
            title="running 상태로 남은 찌꺼기를 일괄 정리"
          >
            <Wand2 className="h-4 w-4" />
            찌꺼기 정리 ({staleCount})
          </button>
        )}
      </div>

      {err && <div className="card border-destructive/40 text-sm text-destructive">{err}</div>}

      <div className="space-y-2">
        {loading ? (
          <p className="text-sm text-muted-foreground">로딩 중…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">결과가 없습니다.</p>
        ) : (
          rows.map((g) => (
            <div key={g.id} className="card space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 overflow-hidden">
                  <p className="truncate text-sm font-medium">{g.text}</p>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>모드: {g.mode}</span>
                    <span>상태: {g.status}</span>
                    {g.language && <span>언어: {g.language}</span>}
                    {g.duration_sec !== null && <span>길이: {g.duration_sec.toFixed(2)}s</span>}
                    {g.rtf !== null && <span>RTF: {g.rtf.toFixed(3)}</span>}
                    <span>{new Date(g.created_at).toLocaleString()}</span>
                  </div>
                  {g.error && (
                    <p className="mt-1 text-xs text-destructive">{g.error}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => handleDelete(g)}
                  disabled={busyId === g.id}
                  className="shrink-0 rounded-md p-2 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                  title="삭제"
                  aria-label="삭제"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              {g.audio_path && (
                <audio
                  controls
                  preload="none"
                  src={audioUrlFor(g.id, g.audio_format)}
                  className="w-full"
                />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
