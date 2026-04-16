"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, RotateCcw } from "lucide-react";
import { api, audioUrlFor } from "@/lib/api";
import {
  DEFAULT_TTS_PARAMS,
  type LanguageEntry,
  type Speaker,
  type TTSParams,
  type TTSResponse,
  type VoiceAttributeOptions,
  type VoiceDesign,
} from "@/lib/types";

type Mode = "tts" | "design" | "auto";

export function StudioForm() {
  const [mode, setMode] = useState<Mode>("auto");
  const [text, setText] = useState("안녕하세요, OmniVoice 음성 합성 테스트입니다.");
  const [language, setLanguage] = useState<string>("ko");
  const [speakerId, setSpeakerId] = useState<string | null>(null);
  const [format, setFormat] = useState<"wav" | "mp3">("wav");
  const [params, setParams] = useState<TTSParams>(DEFAULT_TTS_PARAMS);
  const [design, setDesign] = useState<VoiceDesign>({});
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [languages, setLanguages] = useState<LanguageEntry[]>([]);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [voiceAttrs, setVoiceAttrs] = useState<VoiceAttributeOptions | null>(null);
  const [nonverbal, setNonverbal] = useState<string[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<TTSResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.languages(),
      api.listSpeakers(),
      api.voiceAttributes(),
      api.nonverbalTags(),
    ])
      .then(([l, s, v, n]) => {
        setLanguages(l);
        setSpeakers(s);
        setVoiceAttrs(v);
        setNonverbal(n);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  const handleSubmit = async () => {
    setSubmitting(true);
    setErr(null);
    setResult(null);
    try {
      const payload = {
        text,
        speaker_id: mode === "tts" ? speakerId : null,
        language: language || null,
        design: mode === "design" ? design : null,
        params,
        format,
      };
      const res = await api.tts(payload);
      setResult(res);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const insertTag = (tag: string) => {
    setText((prev) => `${prev} ${tag}`.trim());
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      {/* 좌측 사이드: 모드 + 파라미터 */}
      <aside className="space-y-4">
        <div className="card space-y-3">
          <label className="label">모드</label>
          <div className="grid grid-cols-3 gap-1 rounded-md bg-muted p-1">
            {(["tts", "design", "auto"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`rounded px-2 py-1.5 text-xs font-medium transition ${
                  mode === m ? "bg-card shadow-sm text-foreground" : "text-muted-foreground"
                }`}
              >
                {m === "tts" ? "화자 복제" : m === "design" ? "보이스 디자인" : "오토"}
              </button>
            ))}
          </div>

          {mode === "tts" && (
            <div>
              <label className="label">화자</label>
              <select
                className="input mt-1"
                value={speakerId ?? ""}
                onChange={(e) => setSpeakerId(e.target.value || null)}
              >
                <option value="">— 선택 —</option>
                {speakers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} {s.is_favorite ? "★" : ""}
                  </option>
                ))}
              </select>
              {speakers.length === 0 && (
                <p className="mt-1 text-xs text-muted-foreground">
                  화자가 없습니다. 화자 라이브러리에서 먼저 등록하세요.
                </p>
              )}
            </div>
          )}

          <div>
            <label className="label">언어</label>
            <select
              className="input mt-1"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="">자동 감지</option>
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name} ({l.code})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">출력 포맷</label>
            <div className="mt-1 flex gap-1 rounded-md bg-muted p-1">
              {(["wav", "mp3"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFormat(f)}
                  className={`flex-1 rounded px-2 py-1.5 text-xs font-medium transition ${
                    format === f ? "bg-card shadow-sm" : "text-muted-foreground"
                  }`}
                >
                  {f.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="card space-y-3">
          <label className="label">파라미터</label>

          <SliderRow
            label="속도"
            min={0.5}
            max={1.5}
            step={0.05}
            value={params.speed ?? 1.0}
            onChange={(v) => setParams({ ...params, speed: v })}
            suffix="x"
          />
          <SliderRow
            label="CFG"
            min={0}
            max={4}
            step={0.1}
            value={params.guidance_scale}
            onChange={(v) => setParams({ ...params, guidance_scale: v })}
          />

          <div>
            <label className="label">품질 (num_step)</label>
            <div className="mt-1 grid grid-cols-3 gap-1 rounded-md bg-muted p-1">
              {[
                { v: 16, name: "Fast" },
                { v: 32, name: "Balanced" },
                { v: 64, name: "Quality" },
              ].map((p) => (
                <button
                  key={p.v}
                  type="button"
                  onClick={() => setParams({ ...params, num_step: p.v })}
                  className={`rounded px-1 py-1.5 text-xs font-medium ${
                    params.num_step === p.v ? "bg-card shadow-sm" : "text-muted-foreground"
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={params.denoise}
              onChange={(e) => setParams({ ...params, denoise: e.target.checked })}
            />
            Denoise
          </label>

          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-xs text-primary hover:underline"
          >
            {showAdvanced ? "고급 설정 닫기" : "고급 설정 열기"}
          </button>
          {showAdvanced && (
            <div className="space-y-3 border-t border-border pt-3">
              <SliderRow
                label="t_shift"
                min={0}
                max={1}
                step={0.05}
                value={params.t_shift}
                onChange={(v) => setParams({ ...params, t_shift: v })}
              />
              <SliderRow
                label="position_temp"
                min={0}
                max={10}
                step={0.5}
                value={params.position_temperature}
                onChange={(v) => setParams({ ...params, position_temperature: v })}
              />
              <SliderRow
                label="layer_penalty"
                min={0}
                max={10}
                step={0.5}
                value={params.layer_penalty_factor}
                onChange={(v) => setParams({ ...params, layer_penalty_factor: v })}
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={params.preprocess_prompt}
                  onChange={(e) => setParams({ ...params, preprocess_prompt: e.target.checked })}
                />
                preprocess_prompt
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={params.postprocess_output}
                  onChange={(e) => setParams({ ...params, postprocess_output: e.target.checked })}
                />
                postprocess_output
              </label>
            </div>
          )}

          <button
            type="button"
            onClick={() => setParams(DEFAULT_TTS_PARAMS)}
            className="btn-ghost w-full text-xs"
          >
            <RotateCcw className="h-3 w-3" />
            기본값 복원
          </button>
        </div>
      </aside>

      {/* 본문: 텍스트 + 디자인 + 결과 */}
      <section className="space-y-4">
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <label className="label">텍스트</label>
            <span className="text-xs text-muted-foreground">
              {text.length} / 10,000
            </span>
          </div>
          <textarea
            className="textarea"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={10000}
            placeholder="합성할 텍스트를 입력하세요. [laughter] 같은 비언어 태그를 삽입할 수 있습니다."
          />
          <div className="flex flex-wrap gap-2">
            {nonverbal.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => insertTag(tag)}
                className="rounded-md border border-border bg-muted px-2 py-1 text-xs hover:bg-primary/20"
              >
                {tag}
              </button>
            ))}
          </div>
        </div>

        {mode === "design" && voiceAttrs && (
          <div className="card space-y-3">
            <label className="label">보이스 디자인</label>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <DesignSelect
                label="gender"
                value={design.gender}
                options={voiceAttrs.gender}
                onChange={(v) => setDesign({ ...design, gender: v })}
              />
              <DesignSelect
                label="age"
                value={design.age}
                options={voiceAttrs.age}
                onChange={(v) => setDesign({ ...design, age: v })}
              />
              <DesignSelect
                label="pitch"
                value={design.pitch}
                options={voiceAttrs.pitch}
                onChange={(v) => setDesign({ ...design, pitch: v })}
              />
              <DesignSelect
                label="style"
                value={design.style}
                options={voiceAttrs.style}
                onChange={(v) => setDesign({ ...design, style: v })}
              />
              <DesignSelect
                label="english_accent"
                value={design.english_accent}
                options={voiceAttrs.english_accent}
                onChange={(v) => setDesign({ ...design, english_accent: v })}
              />
              <DesignSelect
                label="chinese_dialect"
                value={design.chinese_dialect}
                options={voiceAttrs.chinese_dialect}
                onChange={(v) => setDesign({ ...design, chinese_dialect: v })}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Accent는 영어 텍스트, Dialect는 중국어 텍스트에만 효과 있습니다. 빈 필드는 모델이 자율 결정합니다.
            </p>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || text.length === 0 || (mode === "tts" && !speakerId)}
            className="btn-primary"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {submitting ? "생성 중…" : "생성"}
          </button>
          {err && <span className="text-sm text-destructive">{err}</span>}
        </div>

        {result && result.audio_url && (
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <label className="label">결과</label>
              <span className="text-xs text-muted-foreground">
                ID: <code className="font-mono">{result.generation_id.slice(0, 12)}…</code>
              </span>
            </div>
            <audio controls src={audioUrlFor(result.generation_id, format)} className="w-full" />
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
              <span>길이: {result.duration_sec?.toFixed(2)}s</span>
              {result.rtf !== null && <span>RTF: {result.rtf.toFixed(3)}</span>}
              <span>상태: {result.status}</span>
            </div>
            <a href={audioUrlFor(result.generation_id, format)} download className="btn-outline w-fit">
              다운로드
            </a>
          </div>
        )}
      </section>
    </div>
  );
}

function SliderRow({
  label,
  min,
  max,
  step,
  value,
  onChange,
  suffix = "",
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <label className="label">{label}</label>
        <span className="text-xs font-mono text-foreground">
          {value.toFixed(2)}
          {suffix}
        </span>
      </div>
      <input
        type="range"
        className="mt-1 w-full accent-[rgb(var(--primary))]"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

function DesignSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | null | undefined;
  options: string[];
  onChange: (v: string | null) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <select
        className="input mt-1"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">—</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
