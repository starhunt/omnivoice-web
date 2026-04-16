"use client";

import { useState } from "react";
import clsx from "clsx";
import { CodeBlock } from "./code-block";

export type Sample = {
  lang: "cURL" | "JavaScript" | "Python";
  code: string;
};

export type Endpoint = {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  title: string;
  description: string;
  auth?: boolean;
  requestNotes?: string;
  samples: Sample[];
  response?: { status: number; body: string };
};

const methodColors: Record<Endpoint["method"], string> = {
  GET: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  POST: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  PATCH: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  DELETE: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

export function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
  const [activeTab, setActiveTab] = useState<Sample["lang"]>(endpoint.samples[0].lang);
  const sample = endpoint.samples.find((s) => s.lang === activeTab) ?? endpoint.samples[0];

  return (
    <article className="card space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <span
          className={clsx(
            "rounded-md border px-2 py-0.5 font-mono text-[11px] font-bold tracking-wider",
            methodColors[endpoint.method],
          )}
        >
          {endpoint.method}
        </span>
        <code className="font-mono text-sm">{endpoint.path}</code>
        {endpoint.auth === false && (
          <span className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            인증 불필요
          </span>
        )}
      </header>

      <div>
        <h3 className="text-sm font-semibold">{endpoint.title}</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">{endpoint.description}</p>
        {endpoint.requestNotes && (
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">요청 노트:</span> {endpoint.requestNotes}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-1 rounded-md bg-muted p-1">
          {endpoint.samples.map((s) => (
            <button
              key={s.lang}
              type="button"
              onClick={() => setActiveTab(s.lang)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs font-medium transition",
                activeTab === s.lang
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {s.lang}
            </button>
          ))}
        </div>
        <CodeBlock code={sample.code} lang={sample.lang.toLowerCase()} />
      </div>

      {endpoint.response && (
        <div>
          <p className="mb-1 text-xs text-muted-foreground">
            응답 예시 · <span className="font-mono">{endpoint.response.status}</span>
          </p>
          <CodeBlock code={endpoint.response.body} lang="json" />
        </div>
      )}
    </article>
  );
}
