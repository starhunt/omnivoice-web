import type {
  Generation,
  Health,
  LanguageEntry,
  Speaker,
  TTSRequest,
  TTSResponse,
  VoiceAttributeOptions,
} from "./types";

// 브라우저에서는 same-origin `/api/v1/...`로 프록시 (next.config.ts rewrites).
// SSR/서버 컴포넌트에서는 직접 백엔드 호출.
const isBrowser = typeof window !== "undefined";
const API_BASE = isBrowser
  ? "/api/v1"
  : `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8320"}/v1`;

const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "dev-key-change-me";

async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${API_KEY}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, body });
  if (!res.ok) {
    let detail: string = res.statusText;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) detail = err.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  health: () => request<Health>("/health"),
  languages: () => request<LanguageEntry[]>("/languages"),
  voiceAttributes: () => request<VoiceAttributeOptions>("/voice-attributes"),
  nonverbalTags: () => request<string[]>("/nonverbal-tags"),

  listSpeakers: () => request<Speaker[]>("/speakers"),
  getSpeaker: (id: string) => request<Speaker>(`/speakers/${id}`),
  deleteSpeaker: (id: string) =>
    request<void>(`/speakers/${id}`, { method: "DELETE" }),
  createSpeaker: (form: FormData) =>
    request<Speaker>("/speakers", { method: "POST", body: form }),
  patchSpeaker: (id: string, patch: Partial<Pick<Speaker, "name" | "tags" | "note" | "is_favorite">>) =>
    request<Speaker>(`/speakers/${id}`, { method: "PATCH", json: patch }),

  tts: (payload: TTSRequest) =>
    request<TTSResponse>("/tts", { method: "POST", json: payload }),

  listGenerations: (query: URLSearchParams = new URLSearchParams()) =>
    request<Generation[]>(`/generations${query.toString() ? `?${query.toString()}` : ""}`),
  getGeneration: (id: string) => request<Generation>(`/generations/${id}`),
  deleteGeneration: (id: string) =>
    request<void>(`/generations/${id}`, { method: "DELETE" }),
  cleanupStaleGenerations: () =>
    request<{ finalized: number }>("/generations/cleanup-stale", { method: "POST" }),
  generationStats: () =>
    request<{ total: number; succeeded: number; failed: number; total_audio_sec: number }>(
      "/generations/stats",
    ),
};

export function audioUrlFor(id: string, fmt: string): string {
  return `/api/v1/assets/${id}.${fmt}`;
}

export function speakerRefUrl(id: string): string {
  return `/api/v1/assets/speaker/${id}/ref`;
}
