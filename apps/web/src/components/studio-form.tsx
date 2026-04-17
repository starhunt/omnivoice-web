"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Play, RotateCcw, Trash2 } from "lucide-react";
import { api, audioUrlFor } from "@/lib/api";
import {
  DEFAULT_TTS_PARAMS,
  type EnginesResponse,
  type Job,
  type LanguageEntry,
  type PodcastSegment,
  type Speaker,
  type TTSParams,
  type TTSResponse,
  type VoiceAttributeOptions,
  type VoiceDesign,
} from "@/lib/types";

type Mode = "tts" | "design" | "auto";
type StudioKind = "single" | "podcast";
type EngineChoice = "auto" | "omnivoice" | "qwen3-tts";

const EMPTY_SEGMENT = { speaker_id: "", voice_id: "", label: "", text: "" };
const SAMPLE_PODCAST_SCRIPT = [
  "HOST: 오늘은 장문 대화형 팟캐스트 생성 흐름을 점검해 보겠습니다.",
  "",
  "GUEST: 네. 이렇게 라벨과 콜론으로 화자를 구분해서 전체 대본을 한 번에 붙여넣으면 됩니다.",
  "",
  "HOST: 같은 화자가 이어서 말하는 여러 줄은 다음 화자 라벨이 나오기 전까지 하나의 발화로 합쳐집니다.",
].join("\n");
const PODCAST_SCRIPT_LABEL_RE = /^\s*([A-Za-z0-9가-힣 _-]{1,32})\s*[:：]\s*(.*)$/;

function firstSpeakerId(speakers: Speaker[], preferredName?: string): string {
  if (!speakers.length) return "";
  if (preferredName) {
    const found = speakers.find((s) => s.name.toLowerCase().includes(preferredName.toLowerCase()));
    if (found) return found.id;
  }
  return speakers[0].id;
}

function secondSpeakerId(speakers: Speaker[], firstId: string): string {
  return speakers.find((s) => s.id !== firstId)?.id ?? firstId;
}

function defaultPodcastSegments(speakers: Speaker[]): PodcastSegment[] {
  const hostId = firstSpeakerId(speakers, "Starhunter");
  const guestId = secondSpeakerId(speakers, hostId);
  return [
    { ...EMPTY_SEGMENT, label: "HOST", speaker_id: hostId },
    { ...EMPTY_SEGMENT, label: "GUEST", speaker_id: guestId },
  ];
}

function parsePodcastScript(
  script: string,
  voiceForLabel: (label: string) => Pick<PodcastSegment, "speaker_id" | "voice_id">,
): PodcastSegment[] {
  const parsed: PodcastSegment[] = [];
  let current: { label: string; lines: string[] } | null = null;

  const flush = () => {
    if (!current) return;
    const text = current.lines.join("\n").trim();
    if (text) {
      parsed.push({
        label: current.label,
        ...voiceForLabel(current.label),
        text,
      });
    }
  };

  for (const rawLine of script.split(/\r?\n/)) {
    const match = rawLine.match(PODCAST_SCRIPT_LABEL_RE);
    if (match) {
      flush();
      current = { label: match[1].trim().toUpperCase(), lines: [match[2] ?? ""] };
      continue;
    }
    if (current) {
      current.lines.push(rawLine);
    } else if (rawLine.trim()) {
      current = { label: "HOST", lines: [rawLine] };
    }
  }
  flush();
  return parsed;
}

export function StudioForm() {
  const [kind, setKind] = useState<StudioKind>("single");
  const [mode, setMode] = useState<Mode>("auto");
  const [text, setText] = useState("안녕하세요, OmniVoice 음성 합성 테스트입니다.");
  const [language, setLanguage] = useState<string>("ko");
  const [speakerId, setSpeakerId] = useState<string | null>(null);
  const [qwenVoiceId, setQwenVoiceId] = useState<string>("");
  const [format, setFormat] = useState<"wav" | "mp3">("wav");
  const [engine, setEngine] = useState<EngineChoice>("auto");
  const [params, setParams] = useState<TTSParams>(DEFAULT_TTS_PARAMS);
  const [design, setDesign] = useState<VoiceDesign>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [useAsync, setUseAsync] = useState(true);

  const [podcastTitle, setPodcastTitle] = useState("대화형 팟캐스트");
  const [podcastScript, setPodcastScript] = useState(SAMPLE_PODCAST_SCRIPT);
  const [pauseMs, setPauseMs] = useState(350);
  const [segments, setSegments] = useState<PodcastSegment[]>([
    { ...EMPTY_SEGMENT, label: "HOST" },
    { ...EMPTY_SEGMENT, label: "GUEST" },
  ]);
  const [showSegmentEditor, setShowSegmentEditor] = useState(false);

  const [languages, setLanguages] = useState<LanguageEntry[]>([]);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [voiceAttrs, setVoiceAttrs] = useState<VoiceAttributeOptions | null>(null);
  const [nonverbal, setNonverbal] = useState<string[]>([]);
  const [engines, setEngines] = useState<EnginesResponse | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<TTSResponse | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const jobRunning = job?.status === "queued" || job?.status === "running";
  const progressTotal = job?.progress.total || job?.progress_total || 0;
  const progressCurrent = job?.progress.current || job?.progress_current || 0;
  const progressPct = progressTotal > 0 ? Math.round((progressCurrent / progressTotal) * 100) : 0;
  const podcastChars = segments.reduce((sum, seg) => sum + seg.text.trim().length, 0);
  const activeEngineId = engine === "auto" ? engines?.selected_engine ?? "auto" : engine;
  const activeEngine = engines?.engines.find((item) => item.id === activeEngineId) ?? null;
  const qwenActive = activeEngineId === "qwen3-tts";
  const qwenVoiceOptions = useMemo(
    () =>
      (activeEngine?.voices ?? []).map((voice) => ({
        id: voice.id,
        name: `${voice.name}${voice.source === "uploaded" ? " (uploaded)" : ""}`,
      })),
    [activeEngine],
  );
  const hostSpeakerId = segments.find((seg) => (seg.label || "").toUpperCase() === "HOST")?.speaker_id ?? "";
  const guestSpeakerId = segments.find((seg) => (seg.label || "").toUpperCase() === "GUEST")?.speaker_id ?? "";
  const hostVoiceId = segments.find((seg) => (seg.label || "").toUpperCase() === "HOST")?.voice_id ?? "";
  const guestVoiceId = segments.find((seg) => (seg.label || "").toUpperCase() === "GUEST")?.voice_id ?? "";

  const canSubmitSingle =
    text.trim().length > 0 && (qwenActive ? Boolean(qwenVoiceId) : mode !== "tts" || Boolean(speakerId));
  const canSubmitPodcast = showSegmentEditor
    ? segments.length > 0 && segments.every((seg) => (qwenActive ? seg.voice_id : seg.speaker_id) && seg.text.trim().length > 0)
    : podcastScript.trim().length > 0 && Boolean(qwenActive ? hostVoiceId || qwenVoiceOptions[0] : hostSpeakerId || speakers[0]);

  const speakerOptions = useMemo(
    () => speakers.map((s) => ({ id: s.id, name: `${s.name}${s.is_favorite ? " ★" : ""}` })),
    [speakers],
  );

  useEffect(() => {
    Promise.all([
      api.languages(),
      api.listSpeakers(),
      api.voiceAttributes(),
      api.nonverbalTags(),
      api.engines(),
    ])
      .then(([l, s, v, n, e]) => {
        setLanguages(l);
        setSpeakers(s);
        setVoiceAttrs(v);
        setNonverbal(n);
        setEngines(e);
        const qwen = e.engines.find((item) => item.id === "qwen3-tts");
        const firstQwenVoice = qwen?.voices[0]?.id;
        if (firstQwenVoice) setQwenVoiceId((prev) => prev || firstQwenVoice);
        if (!speakerId && s[0]) setSpeakerId(s[0].id);
        if (s[0]) {
          const defaults = defaultPodcastSegments(s);
          setSegments((prev) =>
            prev.map((seg, idx) => ({
              ...seg,
              speaker_id: seg.speaker_id || defaults[idx]?.speaker_id || s[0].id,
            })),
          );
        }
      })
      .catch((e: Error) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!qwenActive) return;
    const first = qwenVoiceOptions[0]?.id;
    if (first && !qwenVoiceId) setQwenVoiceId(first);
    if (first) {
      setSegments((prev) =>
        prev.map((seg, idx) => ({
          ...seg,
          voice_id: seg.voice_id || qwenVoiceOptions[idx % qwenVoiceOptions.length]?.id || first,
        })),
      );
    }
  }, [qwenActive, qwenVoiceId, qwenVoiceOptions]);

  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;

    const poll = async () => {
      try {
        const next = await api.getJob(activeJobId);
        if (stopped) return;
        setJob(next);
        if (!["queued", "running"].includes(next.status)) {
          setActiveJobId(null);
        }
      } catch (e) {
        if (!stopped) {
          setErr((e as Error).message);
          setActiveJobId(null);
        }
      }
    };

    poll();
    const timer = window.setInterval(poll, 2500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [activeJobId]);

  const singlePayload = () => ({
    text,
    speaker_id: qwenActive ? null : mode === "tts" ? speakerId : null,
    voice_id: qwenActive ? qwenVoiceId : null,
    language: language || null,
    design: !qwenActive && mode === "design" ? design : null,
    params,
    format,
    engine,
  });

  const handleSubmitSingle = async () => {
    setSubmitting(true);
    setErr(null);
    setResult(null);
    setJob(null);
    setActiveJobId(null);
    try {
      if (useAsync) {
        const created = await api.createTtsJob(singlePayload());
        const next = await api.getJob(created.job_id);
        setJob(next);
        setActiveJobId(created.job_id);
      } else {
        const res = await api.tts(singlePayload());
        setResult(res);
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitPodcast = async () => {
    setSubmitting(true);
    setErr(null);
    setResult(null);
    setJob(null);
    setActiveJobId(null);
    try {
      const podcastSegments = showSegmentEditor
        ? segments
        : parsePodcastScript(podcastScript, voiceForPodcastLabel).slice(0, 200);
      if (!podcastSegments.length) {
        throw new Error("HOST: 내용 또는 GUEST: 내용 형식의 대본을 입력하세요.");
      }
      if (podcastSegments.some((seg) => !(qwenActive ? seg.voice_id : seg.speaker_id) || !seg.text.trim())) {
        throw new Error("모든 발화에 화자와 텍스트가 필요합니다.");
      }
      setSegments(podcastSegments);
      const created = await api.createPodcastJob({
        title: podcastTitle || null,
        segments: podcastSegments.map((seg) => ({
          speaker_id: qwenActive ? null : seg.speaker_id,
          voice_id: qwenActive ? seg.voice_id : null,
          label: seg.label || null,
          text: seg.text.trim(),
          language: seg.language || null,
        })),
        language: language || null,
        params,
        format,
        pause_ms: pauseMs,
        engine,
      });
      const next = await api.getJob(created.job_id);
      setJob(next);
      setActiveJobId(created.job_id);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const insertTag = (tag: string) => {
    setText((prev) => `${prev} ${tag}`.trim());
  };

  const updateSegment = (idx: number, patch: Partial<PodcastSegment>) => {
    setSegments((prev) => prev.map((seg, i) => (i === idx ? { ...seg, ...patch } : seg)));
  };

  const voiceForPodcastLabel = (label: string): Pick<PodcastSegment, "speaker_id" | "voice_id"> => {
    const normalized = label.toUpperCase();
    const match = segments.find((seg) => (seg.label || "").toUpperCase() === normalized);
    if (qwenActive) {
      if (match?.voice_id) return { voice_id: match.voice_id, speaker_id: null };
      if (normalized === "HOST" && hostVoiceId) return { voice_id: hostVoiceId, speaker_id: null };
      if (normalized === "GUEST" && guestVoiceId) return { voice_id: guestVoiceId, speaker_id: null };
      return { voice_id: qwenVoiceOptions[0]?.id ?? "", speaker_id: null };
    }
    if (match?.speaker_id) return { speaker_id: match.speaker_id, voice_id: null };
    if (normalized === "HOST" && hostSpeakerId) return { speaker_id: hostSpeakerId, voice_id: null };
    if (normalized === "GUEST" && guestSpeakerId) return { speaker_id: guestSpeakerId, voice_id: null };
    return { speaker_id: speakers[0]?.id ?? "", voice_id: null };
  };

  const setSpeakerForLabel = (label: string, value: string) => {
    const normalized = label.toUpperCase();
    setSegments((prev) =>
      prev.map((seg) =>
        (seg.label || "").toUpperCase() === normalized
          ? qwenActive
            ? { ...seg, voice_id: value, speaker_id: null }
            : { ...seg, speaker_id: value, voice_id: null }
          : seg,
      ),
    );
  };

  const applyPodcastScript = () => {
    const parsed = parsePodcastScript(podcastScript, voiceForPodcastLabel).slice(0, 200);
    if (!parsed.length) {
      setErr("HOST: 내용 또는 GUEST: 내용 형식의 대본을 입력하세요.");
      return;
    }
    if (parsed.some((seg) => !(qwenActive ? seg.voice_id : seg.speaker_id))) {
      setErr("대본에 사용할 화자를 먼저 선택하세요.");
      return;
    }
    setSegments(parsed);
    setErr(null);
    setShowSegmentEditor(false);
  };

  const syncScriptFromSegments = () => {
    setPodcastScript(
      segments
        .map((seg) => `${(seg.label || "HOST").toUpperCase()}: ${seg.text.trim()}`)
        .join("\n\n"),
    );
  };

  const addSegment = () => {
    setSegments((prev) => [
      ...prev,
      {
        ...EMPTY_SEGMENT,
        label: prev.length % 2 === 0 ? "HOST" : "GUEST",
        speaker_id: qwenActive ? null : speakers[0]?.id ?? "",
        voice_id: qwenActive ? qwenVoiceOptions[prev.length % Math.max(qwenVoiceOptions.length, 1)]?.id ?? "" : null,
      },
    ]);
  };

  const removeSegment = (idx: number) => {
    setSegments((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <aside className="space-y-4">
        <div className="card space-y-3">
          <label className="label">작업</label>
          <div className="grid grid-cols-2 gap-1 rounded-md bg-muted p-1">
            {(["single", "podcast"] as StudioKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`rounded px-2 py-1.5 text-xs font-medium transition ${
                  kind === k ? "bg-card shadow-sm text-foreground" : "text-muted-foreground"
                }`}
              >
                {k === "single" ? "단일 음성" : "팟캐스트"}
              </button>
            ))}
          </div>

          <div>
            <label className="label">엔진</label>
            <select
              className="input mt-1"
              value={engine}
              onChange={(e) => setEngine(e.target.value as EngineChoice)}
            >
              <option value="auto">자동 ({engines?.selected_engine ?? "auto"})</option>
              {(engines?.engines ?? []).map((item) => (
                <option key={item.id} value={item.id} disabled={!item.available}>
                  {item.name} {item.available ? "" : `- ${item.reason ?? "사용 불가"}`}
                </option>
              ))}
            </select>
            {engines && (
              <p className="mt-1 text-xs text-muted-foreground">
                사용 가능: {engines.engines.filter((item) => item.available).map((item) => item.name).join(", ") || "없음"}
              </p>
            )}
            {qwenActive && (
              <p className="mt-1 text-xs text-muted-foreground">
                Qwen3-TTS는 엔진 내장 voice를 사용합니다. OmniVoice 화자 복제 목록과 별도로 선택됩니다.
              </p>
            )}
          </div>

          {kind === "single" && (
            <>
              {qwenActive ? (
                <SpeakerSelect
                  label="Qwen Voice"
                  value={qwenVoiceId}
                  speakers={qwenVoiceOptions}
                  onChange={(v) => setQwenVoiceId(v)}
                />
              ) : (
                <>
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
                    <SpeakerSelect
                      label="화자"
                      value={speakerId ?? ""}
                      speakers={speakerOptions}
                      onChange={(v) => setSpeakerId(v || null)}
                    />
                  )}
                </>
              )}

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={useAsync}
                  onChange={(e) => setUseAsync(e.target.checked)}
                />
                비동기 Job으로 생성
              </label>
            </>
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

          {kind === "podcast" && (
            <SliderRow
              label="발화 간격"
              min={0}
              max={1500}
              step={50}
              value={pauseMs}
              onChange={(v) => setPauseMs(v)}
              suffix="ms"
            />
          )}
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

      <section className="space-y-4">
        {kind === "single" ? (
          <>
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

            {!qwenActive && mode === "design" && voiceAttrs && (
              <VoiceDesignEditor
                voiceAttrs={voiceAttrs}
                design={design}
                setDesign={setDesign}
              />
            )}
          </>
        ) : (
          <div className="card space-y-4">
            <div>
              <label className="label">제목</label>
              <input
                className="input mt-1"
                value={podcastTitle}
                onChange={(e) => setPodcastTitle(e.target.value)}
                placeholder="팟캐스트 제목"
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <SpeakerSelect
                label={qwenActive ? "HOST Voice" : "HOST 화자"}
                value={qwenActive ? hostVoiceId : hostSpeakerId}
                speakers={qwenActive ? qwenVoiceOptions : speakerOptions}
                onChange={(v) => setSpeakerForLabel("HOST", v)}
              />
              <SpeakerSelect
                label={qwenActive ? "GUEST Voice" : "GUEST 화자"}
                value={qwenActive ? guestVoiceId : guestSpeakerId}
                speakers={qwenActive ? qwenVoiceOptions : speakerOptions}
                onChange={(v) => setSpeakerForLabel("GUEST", v)}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <label className="label">대본</label>
                <span className="text-xs text-muted-foreground">
                  {podcastScript.length.toLocaleString()}자
                </span>
              </div>
              <textarea
                className="textarea min-h-[320px] font-mono text-sm leading-6"
                value={podcastScript}
                onChange={(e) => setPodcastScript(e.target.value)}
                placeholder={"HOST: 진행자 발화\n\nGUEST: 게스트 발화\n\nHOST: 다음 질문"}
              />
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <button type="button" onClick={applyPodcastScript} className="btn-outline px-3 py-1.5 text-xs">
                  대본을 발화로 나누기
                </button>
                <button
                  type="button"
                  onClick={() => setShowSegmentEditor((v) => !v)}
                  className="btn-ghost px-3 py-1.5 text-xs"
                >
                  {showSegmentEditor ? "세부 편집 닫기" : "세부 편집 열기"}
                </button>
                {showSegmentEditor && (
                  <button type="button" onClick={syncScriptFromSegments} className="btn-ghost px-3 py-1.5 text-xs">
                    세부 편집을 대본에 반영
                  </button>
                )}
                <span>
                  현재 발화 {segments.length}개, {podcastChars.toLocaleString()}자
                </span>
              </div>
            </div>

            {showSegmentEditor && (
              <div className="space-y-3 border-t border-border pt-4">
                <div className="flex items-center justify-between">
                  <label className="label">발화 세부 편집</label>
                  <button type="button" onClick={addSegment} className="btn-outline px-3 py-1.5 text-xs">
                    <Plus className="h-3 w-3" />
                    발화 추가
                  </button>
                </div>

                {segments.map((seg, idx) => (
                  <div key={idx} className="space-y-2 rounded-md border border-border bg-background/30 p-3">
                    <div className="grid gap-2 md:grid-cols-[120px_1fr_40px]">
                      <input
                        className="input"
                        value={seg.label ?? ""}
                        onChange={(e) => updateSegment(idx, { label: e.target.value })}
                        placeholder="HOST"
                      />
                      <SpeakerSelect
                        label=""
                        value={qwenActive ? seg.voice_id ?? "" : seg.speaker_id ?? ""}
                        speakers={qwenActive ? qwenVoiceOptions : speakerOptions}
                        onChange={(v) =>
                          updateSegment(
                            idx,
                            qwenActive
                              ? { voice_id: v, speaker_id: null }
                              : { speaker_id: v, voice_id: null },
                          )
                        }
                      />
                      <button
                        type="button"
                        onClick={() => removeSegment(idx)}
                        disabled={segments.length <= 1}
                        className="rounded-md p-2 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        title="삭제"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    <textarea
                      className="textarea min-h-[96px]"
                      value={seg.text}
                      onChange={(e) => updateSegment(idx, { text: e.target.value })}
                      placeholder="이 화자가 말할 내용을 입력하세요."
                    />
                  </div>
                ))}
              </div>
            )}

            {!qwenActive && speakers.length < 2 && (
              <p className="text-xs text-muted-foreground">
                실제 2인 팟캐스트는 화자 라이브러리에 두 명 이상의 화자를 등록한 뒤 서로 다른 화자를 선택하세요.
              </p>
            )}
            {qwenActive && qwenVoiceOptions.length < 2 && (
              <p className="text-xs text-muted-foreground">
                Qwen voice가 두 개 이상 노출되면 HOST와 GUEST에 서로 다른 voice를 지정할 수 있습니다.
              </p>
            )}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={kind === "single" ? handleSubmitSingle : handleSubmitPodcast}
            disabled={
              submitting ||
              jobRunning ||
              (kind === "single" ? !canSubmitSingle : !canSubmitPodcast)
            }
            className="btn-primary"
          >
            {submitting || jobRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {submitting || jobRunning ? "생성 중..." : kind === "single" ? "생성" : "팟캐스트 생성"}
          </button>
          {err && <span className="text-sm text-destructive">{err}</span>}
        </div>

        {job && (
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <label className="label">Job</label>
              <span className="text-xs text-muted-foreground">
                ID: <code className="font-mono">{job.id.slice(0, 12)}...</code>
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-muted">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${Math.min(progressPct, 100)}%` }}
              />
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
              <span>상태: {job.status}</span>
              <span>진행: {progressCurrent} / {progressTotal || 1}</span>
              {job.progress.message && <span>{job.progress.message}</span>}
            </div>
            {job.error && <p className="text-xs text-destructive">{job.error}</p>}
            {job.status === "succeeded" && job.generation_id && (
              <>
                <audio controls src={audioUrlFor(job.generation_id, format)} className="w-full" />
                <a href={audioUrlFor(job.generation_id, format)} download className="btn-outline w-fit">
                  다운로드
                </a>
              </>
            )}
          </div>
        )}

        {result && result.audio_url && (
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <label className="label">결과</label>
              <span className="text-xs text-muted-foreground">
                ID: <code className="font-mono">{result.generation_id.slice(0, 12)}...</code>
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

function SpeakerSelect({
  label,
  value,
  speakers,
  onChange,
}: {
  label: string;
  value: string;
  speakers: { id: string; name: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div>
      {label && <label className="label">{label}</label>}
      <select
        className={label ? "input mt-1" : "input"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">화자 선택</option>
        {speakers.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function VoiceDesignEditor({
  voiceAttrs,
  design,
  setDesign,
}: {
  voiceAttrs: VoiceAttributeOptions;
  design: VoiceDesign;
  setDesign: (design: VoiceDesign) => void;
}) {
  return (
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
        <option value="">-</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
