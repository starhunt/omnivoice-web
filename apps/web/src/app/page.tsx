"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, CircleCheck, CircleX, Clock, Cpu, Mic2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Generation, Health } from "@/lib/types";

export default function DashboardPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<{ total: number; succeeded: number; failed: number; total_audio_sec: number } | null>(null);
  const [recent, setRecent] = useState<Generation[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.generationStats(), api.listGenerations(new URLSearchParams({ limit: "5" }))])
      .then(([h, s, g]) => {
        setHealth(h);
        setStats(s);
        setRecent(g);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">대시보드</h1>
          <p className="text-sm text-muted-foreground">OmniVoice-Web 실시간 상태</p>
        </div>
        <Link href="/studio" className="btn-primary">
          <Mic2 className="h-4 w-4" />
          새 합성 시작
        </Link>
      </header>

      {err && (
        <div className="card border-destructive/40 text-sm text-destructive">
          오류: {err}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard
          icon={<Cpu className="h-4 w-4" />}
          label="엔진 모드"
          value={health ? health.engine.mode.toUpperCase() : "…"}
          hint={health ? `device=${health.device}` : undefined}
        />
        <MetricCard
          icon={<Activity className="h-4 w-4" />}
          label="총 생성"
          value={stats ? stats.total.toString() : "…"}
        />
        <MetricCard
          icon={<CircleCheck className="h-4 w-4 text-emerald-400" />}
          label="성공"
          value={stats ? stats.succeeded.toString() : "…"}
          hint={stats ? `실패 ${stats.failed}` : undefined}
        />
        <MetricCard
          icon={<Clock className="h-4 w-4" />}
          label="누적 오디오"
          value={stats ? formatSeconds(stats.total_audio_sec) : "…"}
        />
      </section>

      <section className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">최근 생성</h2>
          <Link href="/history" className="text-xs text-primary hover:underline">
            전체 보기 →
          </Link>
        </div>
        <div className="divide-y divide-border">
          {recent.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              아직 생성이 없습니다. <Link href="/studio" className="text-primary hover:underline">스튜디오</Link>에서 시작하세요.
            </p>
          ) : (
            recent.map((g) => (
              <Link
                key={g.id}
                href={`/history?focus=${g.id}`}
                className="flex items-center justify-between py-3 text-sm hover:bg-muted/40"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  {g.status === "succeeded" ? (
                    <CircleCheck className="h-4 w-4 text-emerald-400" />
                  ) : g.status === "failed" ? (
                    <CircleX className="h-4 w-4 text-destructive" />
                  ) : (
                    <Clock className="h-4 w-4" />
                  )}
                  <span className="truncate">{g.text}</span>
                </div>
                <span className="whitespace-nowrap text-xs text-muted-foreground">
                  {g.duration_sec ? `${g.duration_sec.toFixed(1)}s` : "—"} · {new Date(g.created_at).toLocaleTimeString()}
                </span>
              </Link>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="label">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function formatSeconds(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 ${Math.round(sec % 60)}초`;
  const h = Math.floor(sec / 3600);
  const m = Math.round((sec % 3600) / 60);
  return `${h}시간 ${m}분`;
}
