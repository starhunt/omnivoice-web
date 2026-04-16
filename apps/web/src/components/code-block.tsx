"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function CodeBlock({
  code,
  lang,
  maxHeight,
}: {
  code: string;
  lang?: string;
  maxHeight?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard 미지원 — 무시 */
    }
  };

  return (
    <div className="relative">
      {lang && (
        <span className="absolute left-3 top-2 select-none text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {lang}
        </span>
      )}
      <button
        type="button"
        onClick={handleCopy}
        className="absolute right-2 top-2 inline-flex items-center gap-1 rounded border border-border bg-muted px-2 py-1 text-xs text-muted-foreground hover:bg-card hover:text-foreground"
        aria-label="코드 복사"
      >
        {copied ? (
          <>
            <Check className="h-3 w-3 text-emerald-400" />
            복사됨
          </>
        ) : (
          <>
            <Copy className="h-3 w-3" />
            복사
          </>
        )}
      </button>
      <pre
        className="overflow-x-auto rounded-md border border-border bg-muted/40 p-4 pt-8 text-xs font-mono leading-relaxed"
        style={maxHeight ? { maxHeight, overflowY: "auto" } : undefined}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}
