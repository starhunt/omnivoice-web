"use client";

import { useEffect, useState } from "react";
import { CircleCheck, CircleX } from "lucide-react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">설정</h1>
        <p className="text-sm text-muted-foreground">환경 정보 및 엔진 상태</p>
      </header>

      {err && <div className="card border-destructive/40 text-sm text-destructive">{err}</div>}

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold">엔진 상태</h2>
        {!health ? (
          <p className="text-sm text-muted-foreground">로딩 중…</p>
        ) : (
          <dl className="grid gap-2 text-sm">
            <Row label="버전" value={health.version} />
            <Row label="디바이스" value={health.device} />
            <Row
              label="모드"
              value={
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${
                    health.engine.mode === "live"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-amber-500/20 text-amber-400"
                  }`}
                >
                  {health.engine.mode}
                </span>
              }
            />
            <Row
              label="엔진 경로"
              value={<Check ok={health.engine.engine_path_exists} />}
            />
            <Row
              label="엔진 Python"
              value={<Check ok={health.engine.engine_python_exists} />}
            />
            <Row
              label="브리지 스크립트"
              value={<Check ok={health.engine.bridge_script_exists} />}
            />
          </dl>
        )}
        {health?.engine.mode === "stub" && (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
            현재 stub 모드입니다. 실제 합성을 사용하려면 <code className="kbd">.env</code>의 <code className="kbd">OMNIVOICE_ENGINE_PATH</code> 및 <code className="kbd">OMNIVOICE_ENGINE_PYTHON</code> 경로를 확인하세요.
          </p>
        )}
      </section>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold">엔드포인트</h2>
        <dl className="grid gap-2 text-sm">
          <Row label="Web" value={<code className="font-mono">http://localhost:5320</code>} />
          <Row label="API" value={<code className="font-mono">http://localhost:8320</code>} />
          <Row label="OpenAPI" value={<a className="text-primary hover:underline" href="http://localhost:8320/docs" target="_blank" rel="noreferrer">/docs</a>} />
        </dl>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-2 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Check({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 text-emerald-400">
      <CircleCheck className="h-4 w-4" /> 존재
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-destructive">
      <CircleX className="h-4 w-4" /> 없음
    </span>
  );
}
