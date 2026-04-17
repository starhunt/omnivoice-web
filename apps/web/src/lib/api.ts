import type {
  Generation,
  Health,
  Job,
  JobCreateResponse,
  LanguageEntry,
  PodcastJobRequest,
  Speaker,
  TTSRequest,
  TTSResponse,
  VoiceAttributeOptions,
} from "./types";

// 긴 TTS 요청은 Next.js rewrite 프록시에서 먼저 끊길 수 있으므로,
// 브라우저에서도 NEXT_PUBLIC_API_BASE가 있으면 FastAPI를 직접 호출한다.
const isBrowser = typeof window !== "undefined";
const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE;
const API_BASE = isBrowser
  ? `${PUBLIC_API_BASE ?? ""}${PUBLIC_API_BASE ? "/v1" : "/api/v1"}`
  : `${PUBLIC_API_BASE ?? "http://localhost:8320"}/v1`;

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

  createTtsJob: (payload: TTSRequest) =>
    request<JobCreateResponse>("/jobs/tts", { method: "POST", json: payload }),
  createPodcastJob: (payload: PodcastJobRequest) =>
    request<JobCreateResponse>("/jobs/podcast", { method: "POST", json: payload }),
  listJobs: (query: URLSearchParams = new URLSearchParams()) =>
    request<Job[]>(`/jobs${query.toString() ? `?${query.toString()}` : ""}`),
  getJob: (id: string) => request<Job>(`/jobs/${id}`),

  listGenerations: (query: URLSearchParams = new URLSearchParams()) =>
    request<Generation[]>(`/generations${query.toString() ? `?${query.toString()}` : ""}`),
  countGenerations: (query: URLSearchParams = new URLSearchParams()) =>
    request<{ total: number }>(`/generations/count${query.toString() ? `?${query.toString()}` : ""}`),
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
  if (isBrowser && PUBLIC_API_BASE) return `${PUBLIC_API_BASE}/v1/assets/${id}.${fmt}`;
  return `/api/v1/assets/${id}.${fmt}`;
}

export function speakerRefUrl(id: string): string {
  if (isBrowser && PUBLIC_API_BASE) return `${PUBLIC_API_BASE}/v1/assets/speaker/${id}/ref`;
  return `/api/v1/assets/speaker/${id}/ref`;
}
