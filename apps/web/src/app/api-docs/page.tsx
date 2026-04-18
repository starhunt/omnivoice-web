"use client";

import { useMemo } from "react";
import Link from "next/link";
import { BookOpen, ExternalLink, ShieldCheck } from "lucide-react";
import { CodeBlock } from "@/components/code-block";
import { EndpointCard, type Endpoint } from "@/components/endpoint-card";

const API_BASE = "http://localhost:8320";
const API_KEY_HINT = "dev-key-change-me";

export default function ApiDocsPage() {
  const sections = useMemo(() => buildSections(API_BASE, API_KEY_HINT), []);

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">API 레퍼런스</h1>
        <p className="text-sm text-muted-foreground">
          OmniVoice-Web REST API v1의 엔드포인트·요청/응답 샘플. 대화형 스펙은{" "}
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-primary hover:underline"
          >
            OpenAPI UI <ExternalLink className="h-3 w-3" />
          </a>
          에서 확인할 수 있습니다.
        </p>
      </header>

      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">시작하기</h2>
        </div>
        <dl className="grid gap-2 text-sm md:grid-cols-2">
          <Row label="Base URL" value={<code className="font-mono">{API_BASE}/v1</code>} />
          <Row label="OpenAPI" value={<a className="text-primary hover:underline" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">{API_BASE}/docs</a>} />
          <Row label="Content-Type" value={<code className="font-mono">application/json</code>} />
          <Row label="오디오 응답" value={<code className="font-mono">audio/wav | audio/mpeg</code>} />
        </dl>
        <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            <ShieldCheck className="h-3.5 w-3.5 text-primary" /> 인증
          </div>
          <p className="mt-1 text-muted-foreground">
            모든 엔드포인트(일부 메타 제외)는 API Key가 필요합니다. 두 가지 헤더 중 하나:
          </p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-muted-foreground">
            <li><code className="font-mono">Authorization: Bearer {API_KEY_HINT}</code></li>
            <li><code className="font-mono">X-API-Key: {API_KEY_HINT}</code></li>
          </ul>
          <p className="mt-2 text-muted-foreground">
            키는 <code className="kbd">.env</code>의 <code className="font-mono">OMNIVOICE_API_KEY</code>로 설정됩니다.
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">에러 규격</h2>
        <CodeBlock
          lang="json"
          code={`HTTP 4xx | 5xx
{
  "detail": "speaker_not_found"
}`}
        />
        <p className="text-xs text-muted-foreground">
          대표 코드: <code className="font-mono">invalid_api_key</code>,{" "}
          <code className="font-mono">speaker_not_found</code>,{" "}
          <code className="font-mono">unsupported_audio_format</code>,{" "}
          <code className="font-mono">audio_too_large</code>,{" "}
          <code className="font-mono">engine_timeout</code>,{" "}
          <code className="font-mono">ffmpeg_not_found</code>,{" "}
          <code className="font-mono">engine_failed</code>.
        </p>
      </section>

      {sections.map((sec) => (
        <section key={sec.title} className="space-y-4">
          <div className="flex items-end justify-between">
            <h2 className="text-lg font-semibold">{sec.title}</h2>
            <p className="text-xs text-muted-foreground">{sec.subtitle}</p>
          </div>
          {sec.endpoints.map((ep, idx) => (
            <EndpointCard
              key={`${sec.title}-${idx}-${ep.method}-${ep.path}-${ep.title}`}
              endpoint={ep}
            />
          ))}
        </section>
      ))}

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold">클라이언트 레시피</h2>
        <p className="text-xs text-muted-foreground">
          재사용 가능한 최소 클라이언트 스니펫 — 각 언어의 공통 헤더/에러 처리를 함수로 뽑아두면 편합니다.
        </p>
        <CodeBlock
          lang="python"
          code={`# requirements: httpx
import httpx

BASE = "${API_BASE}/v1"
KEY = "${API_KEY_HINT}"

def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {KEY}"}, timeout=900)

def tts(text: str, speaker_id: str | None = None, language: str | None = None) -> dict:
    with client() as c:
        r = c.post("/tts", json={
            "text": text,
            "speaker_id": speaker_id,
            "language": language,
            "format": "wav",
            "params": {"num_step": 32, "guidance_scale": 2.0, "denoise": True},
        })
        r.raise_for_status()
        return r.json()

def download(generation_id: str, out_path: str) -> None:
    with client() as c, c.stream("GET", f"/assets/{generation_id}.wav") as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

if __name__ == "__main__":
    meta = tts("파이썬에서 호출하는 합성 예시입니다.", language="ko")
    print(meta)
    download(meta["generation_id"], "out.wav")
    print("저장됨: out.wav")`}
        />
        <CodeBlock
          lang="javascript"
          code={`// 브라우저·Node 공통 (fetch 내장 환경)
const BASE = "${API_BASE}/v1";
const KEY = "${API_KEY_HINT}";

export async function tts({ text, speakerId = null, language = "ko" }) {
  const res = await fetch(BASE + "/tts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + KEY,
    },
    body: JSON.stringify({
      text,
      speaker_id: speakerId,
      language,
      format: "wav",
      params: { num_step: 32, guidance_scale: 2.0, denoise: true },
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { generation_id, audio_url, duration_sec, rtf, ... }
}

export function audioUrl(generationId, fmt = "wav") {
  return \`\${BASE}/assets/\${generationId}.\${fmt}\`;
}

// 사용
// const meta = await tts({ text: "안녕하세요", language: "ko" });
// new Audio(audioUrl(meta.generation_id)).play();`}
        />
      </section>

      <footer className="pb-8 text-center text-xs text-muted-foreground">
        <Link href="/studio" className="text-primary hover:underline">
          스튜디오에서 직접 실행 →
        </Link>
      </footer>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-1.5 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 엔드포인트 데이터
// ---------------------------------------------------------------------------

function buildSections(base: string, key: string): { title: string; subtitle: string; endpoints: Endpoint[] }[] {
  const authH = `-H "Authorization: Bearer ${key}"`;

  return [
    {
      title: "헬스 · 메타",
      subtitle: "서버 상태와 선택지 조회",
      endpoints: [
        {
          method: "GET",
          path: "/v1/health",
          title: "헬스체크",
          description: "서버 가동 여부, 엔진 모드(live/stub), 디바이스 정보를 반환합니다.",
          auth: false,
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/health ${authH}` },
            {
              lang: "JavaScript",
              code: `const r = await fetch("${base}/v1/health", {
  headers: { Authorization: "Bearer ${key}" }
});
console.log(await r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
r = httpx.get("${base}/v1/health", headers={"Authorization": "Bearer ${key}"})
print(r.json())`,
            },
          ],
          response: {
            status: 200,
            body: `{
  "status": "ok",
  "version": "0.1.0",
  "engine": {
    "engine_path_exists": true,
    "engine_python_exists": true,
    "bridge_script_exists": true,
    "mode": "live"
  },
  "device": "mps"
}`,
          },
        },
        {
          method: "GET",
          path: "/v1/languages",
          title: "지원 언어 (상위 30)",
          description: "UI에 노출할 언어 프리셋 목록. 전체 646개는 엔진 docs 참조.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/languages ${authH}` },
            {
              lang: "JavaScript",
              code: `const langs = await fetch("${base}/v1/languages", {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
langs = httpx.get("${base}/v1/languages", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `[
  { "code": "ko", "name": "한국어", "english_name": "Korean" },
  { "code": "en", "name": "영어",   "english_name": "English" }
]`,
          },
        },
        {
          method: "GET",
          path: "/v1/voice-attributes",
          title: "보이스 디자인 속성",
          description: "gender / age / pitch / style / accent / dialect 선택지.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/voice-attributes ${authH}` },
            {
              lang: "JavaScript",
              code: `const opts = await fetch("${base}/v1/voice-attributes", {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
opts = httpx.get("${base}/v1/voice-attributes", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `{
  "gender": ["male", "female"],
  "age":    ["child", "teenager", "young adult", "middle-aged", "elderly"],
  "pitch":  ["very low", "low", "moderate", "high", "very high"],
  "style":  ["whisper"],
  "english_accent":  ["american", "british", "...", "korean"],
  "chinese_dialect": ["河南话", "陕西话", "..."]
}`,
          },
        },
        {
          method: "GET",
          path: "/v1/nonverbal-tags",
          title: "비언어 태그 목록",
          description: "에디터에 삽입 가능한 태그 13종.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/nonverbal-tags ${authH}` },
            {
              lang: "JavaScript",
              code: `const tags = await fetch("${base}/v1/nonverbal-tags", {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
tags = httpx.get("${base}/v1/nonverbal-tags", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `["[laughter]", "[chuckle]", "[sigh]", "[breath]", "[cough]", "..."]`,
          },
        },
        {
          method: "GET",
          path: "/v1/engines",
          title: "TTS 엔진 감지",
          description:
            "OmniVoice/Qwen3-TTS 설치 상태, 기본 엔진, capability를 반환합니다. Studio의 엔진 선택 UI도 이 응답을 사용합니다.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/engines ${authH}` },
            {
              lang: "JavaScript",
              code: `const engines = await fetch("${base}/v1/engines", {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
engines = httpx.get("${base}/v1/engines", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `{
  "default_engine": "auto",
  "selected_engine": "omnivoice",
  "engines": [
    { "id": "omnivoice", "available": true,  "mode": "live" },
    { "id": "qwen3-tts", "available": false, "reason": "QWEN3_TTS_PYTHON missing" }
  ]
}`,
          },
        },
      ],
    },
    {
      title: "TTS 합성",
      subtitle: "텍스트 → 오디오 파일",
      endpoints: [
        {
          method: "POST",
          path: "/v1/tts",
          title: "동기 합성",
          description:
            "텍스트를 합성하여 generation_id와 audio_url을 반환합니다. 화자/보이스디자인/오토 모드 모두 이 엔드포인트로 처리.",
          requestNotes:
            "speaker_id 지정 → 등록 화자 복제 / voice_id 지정 → 엔진 기본 voice / design 지정 → 보이스 디자인. Qwen3-TTS API 방식에서는 voice_id는 CustomVoice 1.7B, speaker_id는 Base 0.6B clone 서버를 사용합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST ${base}/v1/tts \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "안녕하세요, OmniVoice입니다.",
    "speaker_id": null,
    "language": "ko",
    "format": "wav",
    "params": {
      "num_step": 32,
      "guidance_scale": 2.0,
      "speed": 1.0,
      "denoise": true
    }
  }'`,
            },
            {
              lang: "JavaScript",
              code: `const res = await fetch("${base}/v1/tts", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: "Bearer ${key}",
  },
  body: JSON.stringify({
    text: "안녕하세요, OmniVoice입니다.",
    language: "ko",
    format: "wav",
    params: { num_step: 32, guidance_scale: 2.0, denoise: true },
  }),
});
if (!res.ok) throw new Error(await res.text());
const meta = await res.json();
// 재생
new Audio(\`${base}/v1/assets/\${meta.generation_id}.wav\`).play();`,
            },
            {
              lang: "Python",
              code: `import httpx

r = httpx.post(
    "${base}/v1/tts",
    headers={"Authorization": "Bearer ${key}"},
    json={
        "text": "안녕하세요, OmniVoice입니다.",
        "language": "ko",
        "format": "wav",
        "params": {"num_step": 32, "guidance_scale": 2.0, "denoise": True},
    },
    timeout=900,
)
r.raise_for_status()
print(r.json())`,
            },
          ],
          response: {
            status: 200,
            body: `{
  "generation_id": "8f4d790b9baa40478a82b3f06403fc91",
  "audio_url":     "/v1/assets/8f4d790b9baa40478a82b3f06403fc91.wav",
  "duration_sec":  1.88,
  "rtf":           0.21,
  "status":        "succeeded",
  "created_at":    "2026-04-16T09:08:40.918071"
}`,
          },
        },
        {
          method: "POST",
          path: "/v1/tts",
          title: "보이스 디자인 모드",
          description:
            "design 객체로 화자 특성을 파라미터 지정. 서버가 쉼표 구분 instruct 문자열로 조립해 엔진에 전달합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST ${base}/v1/tts \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "Good morning, welcome to the show.",
    "language": "en",
    "format": "wav",
    "design": {
      "gender": "female",
      "age":    "young adult",
      "pitch":  "high",
      "english_accent": "british"
    },
    "params": { "num_step": 32, "guidance_scale": 2.0 }
  }'`,
            },
            {
              lang: "JavaScript",
              code: `await fetch("${base}/v1/tts", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: "Bearer ${key}" },
  body: JSON.stringify({
    text: "Good morning, welcome to the show.",
    language: "en",
    format: "wav",
    design: { gender: "female", age: "young adult", pitch: "high", english_accent: "british" },
    params: { num_step: 32, guidance_scale: 2.0 },
  }),
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
httpx.post(
    "${base}/v1/tts",
    headers={"Authorization": "Bearer ${key}"},
    json={
        "text": "Good morning, welcome to the show.",
        "language": "en",
        "format": "wav",
        "design": {
            "gender": "female", "age": "young adult",
            "pitch": "high", "english_accent": "british",
        },
        "params": {"num_step": 32, "guidance_scale": 2.0},
    },
    timeout=900,
).json()`,
            },
          ],
        },
        {
          method: "POST",
          path: "/v1/tts",
          title: "등록된 화자로 합성",
          description:
            "speaker_id로 라이브러리에 저장된 화자를 재사용합니다. engine이 qwen3-tts이면 source_audio_path가 있는 화자를 Base 0.6B clone 서버로 합성합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST ${base}/v1/tts \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "이 목소리로 말해주세요.",
    "speaker_id": "SPEAKER_ID_HERE",
    "language": "ko",
    "format": "mp3",
    "params": { "num_step": 32, "guidance_scale": 2.0, "speed": 1.1 }
  }'`,
            },
            {
              lang: "JavaScript",
              code: `await fetch("${base}/v1/tts", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: "Bearer ${key}" },
  body: JSON.stringify({
    text: "이 목소리로 말해주세요.",
    speaker_id: "SPEAKER_ID_HERE",
    language: "ko",
    format: "mp3",
    params: { num_step: 32, guidance_scale: 2.0, speed: 1.1 },
  }),
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
httpx.post(
    "${base}/v1/tts",
    headers={"Authorization": "Bearer ${key}"},
    json={
        "text": "이 목소리로 말해주세요.",
        "speaker_id": "SPEAKER_ID_HERE",
        "language": "ko",
        "format": "mp3",
        "params": {"num_step": 32, "guidance_scale": 2.0, "speed": 1.1},
    },
    timeout=900,
).json()`,
            },
          ],
        },
      ],
    },
    {
      title: "ElevenLabs 호환",
      subtitle: "외부 클라이언트 호환용 shim",
      endpoints: [
        {
          method: "GET",
          path: "/v1/voices",
          title: "ElevenLabs 스타일 화자 목록",
          description:
            "등록된 OmniVoice-Web 화자를 ElevenLabs voices 응답 형태로 반환합니다. xi-api-key 헤더를 지원합니다.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/voices -H "xi-api-key: ${key}"` },
            {
              lang: "JavaScript",
              code: `const voices = await fetch("${base}/v1/voices", {
  headers: { "xi-api-key": "${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
voices = httpx.get("${base}/v1/voices", headers={"xi-api-key": "${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `{
  "voices": [
    {
      "voice_id": "SPEAKER_ID",
      "name": "Starhunter",
      "category": "cloned",
      "preview_url": "http://localhost:8320/v1/assets/speaker/SPEAKER_ID/ref"
    }
  ]
}`,
          },
        },
        {
          method: "GET",
          path: "/v2/voices",
          title: "ElevenLabs v2 화자 검색",
          description:
            "최신 ElevenLabs List voices 형태에 맞춰 voices, has_more, total_count, next_page_token을 반환합니다.",
          samples: [
            { lang: "cURL", code: `curl "${base}/v2/voices?page_size=20" -H "xi-api-key: ${key}"` },
            {
              lang: "JavaScript",
              code: `const voices = await fetch("${base}/v2/voices?page_size=20", {
  headers: { "xi-api-key": "${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
voices = httpx.get("${base}/v2/voices", headers={"xi-api-key": "${key}"}).json()`,
            },
          ],
        },
        {
          method: "GET",
          path: "/v1/models",
          title: "ElevenLabs 스타일 모델 목록",
          description:
            "일반 ElevenLabs 클라이언트가 모델 목록을 조회할 때 깨지지 않도록 호환 model_id를 반환합니다.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/models -H "xi-api-key: ${key}"` },
            {
              lang: "JavaScript",
              code: `const models = await fetch("${base}/v1/models", {
  headers: { "xi-api-key": "${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
models = httpx.get("${base}/v1/models", headers={"xi-api-key": "${key}"}).json()`,
            },
          ],
        },
        {
          method: "POST",
          path: "/v1/text-to-speech/{voice_id}",
          title: "ElevenLabs 스타일 TTS",
          description:
            "ElevenLabs Create speech와 같은 경로로 요청을 받고 JSON이 아니라 오디오 바이트를 직접 반환합니다.",
          requestNotes:
            "model_id, stability, similarity_boost 등은 호환 목적으로 수신하되 현재 OmniVoice 엔진에서는 일부만 반영합니다. voice_settings.speed는 params.speed로 매핑합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST "${base}/v1/text-to-speech/SPEAKER_ID?output_format=mp3_44100_128" \\
  -H "xi-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "일레븐랩스 호환 API 테스트입니다.",
    "model_id": "eleven_multilingual_v2",
    "language_code": "ko",
    "voice_settings": { "speed": 1.0 }
  }' \\
  -o out.mp3`,
            },
            {
              lang: "JavaScript",
              code: `const res = await fetch("${base}/v1/text-to-speech/" + voiceId, {
  method: "POST",
  headers: { "Content-Type": "application/json", "xi-api-key": "${key}" },
  body: JSON.stringify({
    text: "일레븐랩스 호환 API 테스트입니다.",
    model_id: "eleven_multilingual_v2",
    language_code: "ko"
  }),
});
const audio = await res.blob();`,
            },
            {
              lang: "Python",
              code: `import httpx
r = httpx.post(
    "${base}/v1/text-to-speech/SPEAKER_ID",
    headers={"xi-api-key": "${key}"},
    json={"text": "일레븐랩스 호환 API 테스트입니다.", "language_code": "ko"},
    timeout=900,
)
r.raise_for_status()
open("out.mp3", "wb").write(r.content)`,
            },
          ],
        },
        {
          method: "POST",
          path: "/v1/text-to-speech/{voice_id}/stream",
          title: "ElevenLabs 스타일 스트림 경로",
          description:
            "경로 호환을 위해 제공합니다. 현재 엔진은 batch 합성 후 오디오 바이트를 반환하므로 true chunk streaming은 아닙니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST "${base}/v1/text-to-speech/SPEAKER_ID/stream" \\
  -H "xi-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{ "text": "stream 경로 호환 테스트입니다.", "language_code": "ko" }' \\
  -o out.mp3`,
            },
            {
              lang: "JavaScript",
              code: `const res = await fetch("${base}/v1/text-to-speech/" + voiceId + "/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json", "xi-api-key": "${key}" },
  body: JSON.stringify({ text: "stream 경로 호환 테스트입니다.", language_code: "ko" }),
});`,
            },
            {
              lang: "Python",
              code: `import httpx
with httpx.stream(
    "POST",
    "${base}/v1/text-to-speech/SPEAKER_ID/stream",
    headers={"xi-api-key": "${key}"},
    json={"text": "stream 경로 호환 테스트입니다.", "language_code": "ko"},
    timeout=900,
) as r:
    r.raise_for_status()
    open("out.mp3", "wb").write(r.read())`,
            },
          ],
        },
        {
          method: "POST",
          path: "/v1/text-to-dialogue",
          title: "ElevenLabs 스타일 Dialogue",
          description:
            "inputs[].voice_id/text 배열을 받아 다중 화자 오디오를 생성합니다. /stream 경로도 같은 방식으로 지원합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST "${base}/v1/text-to-dialogue?output_format=mp3_44100_128" \\
  -H "xi-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model_id": "eleven_v3",
    "language_code": "ko",
    "inputs": [
      { "voice_id": "HOST_SPEAKER_ID",  "text": "안녕하세요. 저는 진행자입니다." },
      { "voice_id": "GUEST_SPEAKER_ID", "text": "반갑습니다. 저는 게스트입니다." }
    ]
  }' \\
  -o dialogue.mp3`,
            },
            {
              lang: "JavaScript",
              code: `const res = await fetch("${base}/v1/text-to-dialogue", {
  method: "POST",
  headers: { "Content-Type": "application/json", "xi-api-key": "${key}" },
  body: JSON.stringify({
    model_id: "eleven_v3",
    language_code: "ko",
    inputs: [
      { voice_id: hostId, text: "안녕하세요. 저는 진행자입니다." },
      { voice_id: guestId, text: "반갑습니다. 저는 게스트입니다." }
    ]
  }),
});`,
            },
            {
              lang: "Python",
              code: `import httpx
r = httpx.post(
    "${base}/v1/text-to-dialogue",
    headers={"xi-api-key": "${key}"},
    json={
        "model_id": "eleven_v3",
        "language_code": "ko",
        "inputs": [
            {"voice_id": "HOST_SPEAKER_ID", "text": "안녕하세요. 저는 진행자입니다."},
            {"voice_id": "GUEST_SPEAKER_ID", "text": "반갑습니다. 저는 게스트입니다."},
        ],
    },
    timeout=900,
)
open("dialogue.mp3", "wb").write(r.content)`,
            },
          ],
        },
      ],
    },
    {
      title: "OpenAI TTS 호환",
      subtitle: "OpenAI Audio Speech 스타일",
      endpoints: [
        {
          method: "POST",
          path: "/v1/audio/speech",
          title: "OpenAI 스타일 음성 생성",
          description:
            "OpenAI Audio Speech와 같은 경로/필드로 요청을 받고 오디오 바이트를 직접 반환합니다. voice는 speaker id 또는 이름으로 매핑됩니다.",
          requestNotes:
            "response_format은 현재 mp3, wav를 지원합니다. input에 <speak><voice name=\"...\">...</voice></speak>를 넣으면 SSML-lite 다중 화자로 처리합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST ${base}/v1/audio/speech \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "tts-1",
    "voice": "Starhunter",
    "input": "OpenAI 호환 음성 생성 테스트입니다.",
    "response_format": "mp3",
    "speed": 1.0
  }' \\
  -o speech.mp3`,
            },
            {
              lang: "JavaScript",
              code: `const res = await fetch("${base}/v1/audio/speech", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: "Bearer ${key}" },
  body: JSON.stringify({
    model: "tts-1",
    voice: "Starhunter",
    input: "OpenAI 호환 음성 생성 테스트입니다.",
    response_format: "mp3",
    speed: 1.0
  }),
});
const audio = await res.blob();`,
            },
            {
              lang: "Python",
              code: `import httpx
r = httpx.post(
    "${base}/v1/audio/speech",
    headers={"Authorization": "Bearer ${key}"},
    json={
        "model": "tts-1",
        "voice": "Starhunter",
        "input": "OpenAI 호환 음성 생성 테스트입니다.",
        "response_format": "mp3",
    },
    timeout=900,
)
open("speech.mp3", "wb").write(r.content)`,
            },
          ],
        },
      ],
    },
    {
      title: "Gemini TTS 호환",
      subtitle: "Gemini generateContent 스타일",
      endpoints: [
        {
          method: "POST",
          path: "/v1beta/models/{model}:generateContent",
          title: "Gemini 스타일 다중 화자 TTS",
          description:
            "Gemini TTS의 generateContent 요청 형태를 받아 speakerVoiceConfigs와 프롬프트 라벨을 내부 podcast segments로 변환합니다.",
          requestNotes:
            "응답은 Gemini처럼 candidates[0].content.parts[0].inlineData.data에 base64 WAV를 넣어 반환합니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST "${base}/v1beta/models/gemini-2.5-flash-preview-tts:generateContent" \\
  -H "x-goog-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "contents": "Joe: 안녕하세요.\\nJane: 네, 반갑습니다.",
    "config": {
      "responseModalities": ["AUDIO"],
      "speechConfig": {
        "multiSpeakerVoiceConfig": {
          "speakerVoiceConfigs": [
            { "speaker": "Joe",  "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "Starhunter" } } },
            { "speaker": "Jane", "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "OmniVoice Korean Demo KR" } } }
          ]
        }
      }
    }
  }'`,
            },
            {
              lang: "JavaScript",
              code: `const res = await fetch("${base}/v1beta/models/gemini-2.5-flash-preview-tts:generateContent", {
  method: "POST",
  headers: { "Content-Type": "application/json", "x-goog-api-key": "${key}" },
  body: JSON.stringify({
    contents: "Joe: 안녕하세요.\\nJane: 네, 반갑습니다.",
    config: {
      responseModalities: ["AUDIO"],
      speechConfig: {
        multiSpeakerVoiceConfig: {
          speakerVoiceConfigs: [
            { speaker: "Joe", voiceConfig: { prebuiltVoiceConfig: { voiceName: "Starhunter" } } },
            { speaker: "Jane", voiceConfig: { prebuiltVoiceConfig: { voiceName: "OmniVoice Korean Demo KR" } } },
          ],
        },
      },
    },
  }),
});
const payload = await res.json();`,
            },
            {
              lang: "Python",
              code: `import base64, httpx
payload = httpx.post(
    "${base}/v1beta/models/gemini-2.5-flash-preview-tts:generateContent",
    headers={"x-goog-api-key": "${key}"},
    json={
        "contents": "Joe: 안녕하세요.\\nJane: 네, 반갑습니다.",
        "config": {"responseModalities": ["AUDIO"]},
    },
    timeout=900,
).json()
raw = base64.b64decode(payload["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
open("gemini.wav", "wb").write(raw)`,
            },
          ],
        },
      ],
    },
    {
      title: "화자",
      subtitle: "참조 오디오 업로드 · CRUD",
      endpoints: [
        {
          method: "GET",
          path: "/v1/speakers",
          title: "화자 목록",
          description: "즐겨찾기 우선 정렬. include_deleted=true로 소프트 삭제된 항목 포함 가능.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/speakers ${authH}` },
            {
              lang: "JavaScript",
              code: `const speakers = await fetch("${base}/v1/speakers", {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
speakers = httpx.get("${base}/v1/speakers", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `[
  {
    "id":   "a7b2c8...",
    "name": "내 기본 한국어",
    "tags": ["ko", "남성", "차분"],
    "is_favorite": true,
    "usage_count": 12,
    "last_used_at": "2026-04-16T09:30:00Z",
    "created_at":   "2026-04-10T10:00:00Z"
  }
]`,
          },
        },
        {
          method: "POST",
          path: "/v1/speakers",
          title: "화자 등록 (multipart)",
          description:
            "참조 오디오 파일과 메타를 multipart/form-data로 전송. 지원 포맷: wav/mp3/flac/ogg/m4a, 최대 50MB.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X POST ${base}/v1/speakers \\
  -H "Authorization: Bearer ${key}" \\
  -F "name=내 기본 한국어" \\
  -F "tags=ko,남성,차분" \\
  -F "language_hint=ko" \\
  -F "ref_transcript=안녕하세요 저는 스타헌터입니다." \\
  -F "note=스튜디오 녹음, 6초" \\
  -F "audio=@./sample.wav;type=audio/wav"`,
            },
            {
              lang: "JavaScript",
              code: `const fd = new FormData();
fd.append("name", "내 기본 한국어");
fd.append("tags", "ko,남성,차분");
fd.append("language_hint", "ko");
fd.append("ref_transcript", "안녕하세요 저는 스타헌터입니다.");
fd.append("audio", fileInput.files[0]);

const spk = await fetch("${base}/v1/speakers", {
  method: "POST",
  headers: { Authorization: "Bearer ${key}" }, // Content-Type은 자동
  body: fd,
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx

with open("sample.wav", "rb") as f:
    r = httpx.post(
        "${base}/v1/speakers",
        headers={"Authorization": "Bearer ${key}"},
        data={
            "name": "내 기본 한국어",
            "tags": "ko,남성,차분",
            "language_hint": "ko",
            "ref_transcript": "안녕하세요 저는 스타헌터입니다.",
        },
        files={"audio": ("sample.wav", f, "audio/wav")},
    )
r.raise_for_status()
print(r.json())`,
            },
          ],
          response: {
            status: 201,
            body: `{
  "id": "a7b2c8...",
  "name": "내 기본 한국어",
  "tags": ["ko", "남성", "차분"],
  "source_audio_path": "speakers/a7b2c8.../ref.wav",
  "is_favorite": false,
  "usage_count": 0,
  "created_at": "2026-04-16T10:00:00Z"
}`,
          },
        },
        {
          method: "PATCH",
          path: "/v1/speakers/{id}",
          title: "화자 수정",
          description: "이름·태그·노트·즐겨찾기 토글. 변경 필드만 보내면 됩니다.",
          samples: [
            {
              lang: "cURL",
              code: `curl -X PATCH ${base}/v1/speakers/SPEAKER_ID \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{ "is_favorite": true, "tags": ["ko", "중성", "나레이션"] }'`,
            },
            {
              lang: "JavaScript",
              code: `await fetch("${base}/v1/speakers/" + id, {
  method: "PATCH",
  headers: { "Content-Type": "application/json", Authorization: "Bearer ${key}" },
  body: JSON.stringify({ is_favorite: true }),
});`,
            },
            {
              lang: "Python",
              code: `import httpx
httpx.patch(
    f"${base}/v1/speakers/{speaker_id}",
    headers={"Authorization": "Bearer ${key}"},
    json={"is_favorite": True},
)`,
            },
          ],
        },
        {
          method: "DELETE",
          path: "/v1/speakers/{id}",
          title: "소프트 삭제",
          description: "deleted_at을 세팅. 30일 후 하드 삭제 예정(Phase 2).",
          samples: [
            { lang: "cURL", code: `curl -X DELETE ${base}/v1/speakers/SPEAKER_ID ${authH}` },
            {
              lang: "JavaScript",
              code: `await fetch("${base}/v1/speakers/" + id, {
  method: "DELETE",
  headers: { Authorization: "Bearer ${key}" },
});`,
            },
            {
              lang: "Python",
              code: `import httpx
httpx.delete(
    f"${base}/v1/speakers/{speaker_id}",
    headers={"Authorization": "Bearer ${key}"},
)`,
            },
          ],
        },
      ],
    },
    {
      title: "히스토리",
      subtitle: "과거 생성 조회",
      endpoints: [
        {
          method: "GET",
          path: "/v1/generations",
          title: "생성 목록 검색",
          description:
            "쿼리: q(텍스트 부분검색), status(succeeded/failed/...), speaker_id, limit, offset.",
          samples: [
            {
              lang: "cURL",
              code: `curl "${base}/v1/generations?q=안녕&limit=20" ${authH}`,
            },
            {
              lang: "JavaScript",
              code: `const qs = new URLSearchParams({ q: "안녕", limit: "20" });
const rows = await fetch("${base}/v1/generations?" + qs, {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
rows = httpx.get(
    "${base}/v1/generations",
    params={"q": "안녕", "limit": 20},
    headers={"Authorization": "Bearer ${key}"},
).json()`,
            },
          ],
        },
        {
          method: "GET",
          path: "/v1/generations/stats",
          title: "통계 요약",
          description: "총 생성 수, 성공/실패, 누적 오디오 시간.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/generations/stats ${authH}` },
            {
              lang: "JavaScript",
              code: `const stats = await fetch("${base}/v1/generations/stats", {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
stats = httpx.get("${base}/v1/generations/stats", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
          response: {
            status: 200,
            body: `{ "total": 42, "succeeded": 40, "failed": 2, "total_audio_sec": 356.8 }`,
          },
        },
        {
          method: "GET",
          path: "/v1/generations/{id}",
          title: "생성 상세",
          description: "파라미터·입력·결과 전체. 히스토리의 재현 기능도 이 응답을 기반으로 만듭니다.",
          samples: [
            { lang: "cURL", code: `curl ${base}/v1/generations/GEN_ID ${authH}` },
            {
              lang: "JavaScript",
              code: `const g = await fetch("${base}/v1/generations/" + id, {
  headers: { Authorization: "Bearer ${key}" }
}).then(r => r.json());`,
            },
            {
              lang: "Python",
              code: `import httpx
g = httpx.get(f"${base}/v1/generations/{gen_id}", headers={"Authorization": "Bearer ${key}"}).json()`,
            },
          ],
        },
      ],
    },
    {
      title: "오디오 자산",
      subtitle: "생성 결과·화자 원본 다운로드",
      endpoints: [
        {
          method: "GET",
          path: "/v1/assets/{generation_id}.{wav|mp3}",
          title: "생성 오디오 다운로드",
          description: "FileResponse로 스트리밍. 브라우저에서 <audio src>로 직접 사용 가능.",
          auth: false,
          samples: [
            {
              lang: "cURL",
              code: `curl -o out.wav ${base}/v1/assets/GEN_ID.wav`,
            },
            {
              lang: "JavaScript",
              code: `const audio = new Audio("${base}/v1/assets/" + id + ".wav");
audio.play();`,
            },
            {
              lang: "Python",
              code: `import httpx
with httpx.stream("GET", f"${base}/v1/assets/{gen_id}.wav") as r:
    r.raise_for_status()
    with open("out.wav", "wb") as f:
        for chunk in r.iter_bytes():
            f.write(chunk)`,
            },
          ],
        },
        {
          method: "GET",
          path: "/v1/assets/speaker/{id}/ref",
          title: "화자 참조 오디오",
          description: "화자 등록 시 업로드한 원본 오디오를 그대로 반환.",
          auth: false,
          samples: [
            {
              lang: "cURL",
              code: `curl -o ref.wav ${base}/v1/assets/speaker/SPEAKER_ID/ref`,
            },
            {
              lang: "JavaScript",
              code: `const el = document.querySelector("audio");
el.src = "${base}/v1/assets/speaker/" + speakerId + "/ref";`,
            },
            {
              lang: "Python",
              code: `import httpx
with httpx.stream("GET", f"${base}/v1/assets/speaker/{speaker_id}/ref") as r:
    r.raise_for_status()
    with open("ref.wav", "wb") as f:
        for chunk in r.iter_bytes():
            f.write(chunk)`,
            },
          ],
        },
      ],
    },
  ];
}
