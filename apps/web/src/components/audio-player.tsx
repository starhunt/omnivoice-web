"use client";

import { Download } from "lucide-react";

export function AudioPlayer({
  src,
  downloadName,
  meta,
}: {
  src: string;
  downloadName?: string;
  meta?: { label: string; value: string }[];
}) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-4">
      <audio controls src={src} className="w-full" preload="metadata" />
      {meta && meta.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
          {meta.map((m) => (
            <span key={m.label}>
              <span className="font-medium text-foreground">{m.label}</span>
              <span className="mx-2">·</span>
              {m.value}
            </span>
          ))}
        </div>
      )}
      <a href={src} download={downloadName} className="btn-outline w-fit">
        <Download className="h-4 w-4" />
        다운로드
      </a>
    </div>
  );
}
