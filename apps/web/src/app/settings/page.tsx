"use client";

import { useEffect, useMemo, useState } from "react";
import { CircleCheck, CircleX, Loader2, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type {
  Health,
  ProviderEngineId,
  TTSProvider,
  TTSProviderInput,
  TTSProviderTestResult,
} from "@/lib/types";

type ProviderForm = TTSProviderInput & { id?: string };

const QWEN_DEFAULT_CONFIG = {
  base_url: "",
  api_key: "",
  clone_base_url: "",
  clone_api_key: "",
  model: "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  clone_model: "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
  design_model: "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
  default_speaker: "sohee",
  python: "/opt/engines/qwen3-tts/.venv/bin/python",
  device: "cuda:0",
  dtype: "bfloat16",
  attn_implementation: "flash_attention_2",
};

const OMNI_DEFAULT_CONFIG = {
  engine_path: "/Users/starhunter/StudyProj/voiceproj/OmniVoice",
  engine_python: "/Users/starhunter/StudyProj/voiceproj/OmniVoice/.venv/bin/python",
  device: "mps",
};

export default function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [providers, setProviders] = useState<TTSProvider[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [form, setForm] = useState<ProviderForm | null>(null);
  const [testResult, setTestResult] = useState<TTSProviderTestResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const selected = useMemo(
    () => providers.find((provider) => provider.id === selectedId) ?? null,
    [providers, selectedId],
  );

  const load = async () => {
    setErr(null);
    const [h, p] = await Promise.all([api.health(), api.listProviders()]);
    setHealth(h);
    setProviders(p);
    setSelectedId((prev) => prev || p[0]?.id || "");
    if (!form && p[0]) setForm(providerToForm(p[0]));
  };

  useEffect(() => {
    load().catch((e: Error) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selected) {
      setForm(providerToForm(selected));
      setTestResult(null);
    }
  }, [selected]);

  const updateConfig = (key: string, value: string) => {
    setForm((prev) => (prev ? { ...prev, config: { ...prev.config, [key]: value } } : prev));
  };

  const save = async () => {
    if (!form) return;
    setSaving(true);
    setErr(null);
    try {
      const payload = normalizeForm(form);
      const saved = form.id ? await api.patchProvider(form.id, payload) : await api.createProvider(payload);
      const next = await api.listProviders();
      setProviders(next);
      setSelectedId(saved.id);
      setForm(providerToForm(saved));
      setHealth(await api.health());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!form?.id) return;
    setSaving(true);
    setErr(null);
    try {
      await api.deleteProvider(form.id);
      const next = await api.listProviders();
      setProviders(next);
      setSelectedId(next[0]?.id || "");
      setForm(next[0] ? providerToForm(next[0]) : null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    if (!form?.id) {
      setErr("저장 후 테스트할 수 있습니다.");
      return;
    }
    setTesting(true);
    setErr(null);
    try {
      setTestResult(await api.testProvider(form.id));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setTesting(false);
    }
  };

  const startNew = (engine: ProviderEngineId) => {
    setSelectedId("");
    setTestResult(null);
    setForm({
      name: engine === "qwen3-tts" ? "Qwen3-TTS Provider" : "OmniVoice Provider",
      engine,
      enabled: true,
      is_default: true,
      config: engine === "qwen3-tts" ? { ...QWEN_DEFAULT_CONFIG } : { ...OMNI_DEFAULT_CONFIG },
    });
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">설정</h1>
        <p className="text-sm text-muted-foreground">Provider 등록, 엔진 상태, 외부 서버 연결 정보</p>
      </header>

      {err && <div className="card border-destructive/40 text-sm text-destructive">{err}</div>}

      <section className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Provider</h2>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => startNew("qwen3-tts")} className="btn-outline px-3 py-1.5 text-xs">
              <Plus className="h-3 w-3" />
              Qwen 추가
            </button>
            <button type="button" onClick={() => startNew("omnivoice")} className="btn-outline px-3 py-1.5 text-xs">
              <Plus className="h-3 w-3" />
              OmniVoice 추가
            </button>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <div className="space-y-2">
            {providers.map((provider) => (
              <button
                key={provider.id}
                type="button"
                onClick={() => setSelectedId(provider.id)}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                  selectedId === provider.id ? "border-primary bg-primary/10" : "border-border bg-background hover:bg-muted"
                }`}
              >
                <span className="block font-medium">{provider.name}</span>
                <span className="text-xs text-muted-foreground">
                  {provider.engine} · {provider.enabled ? "enabled" : "disabled"}
                  {provider.is_default ? " · default" : ""}
                </span>
              </button>
            ))}
            {!providers.length && <p className="text-sm text-muted-foreground">등록된 Provider가 없습니다.</p>}
          </div>

          {form ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="이름">
                  <input className="input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </Field>
                <Field label="엔진">
                  <select
                    className="input mt-1"
                    value={form.engine}
                    onChange={(e) => {
                      const engine = e.target.value as ProviderEngineId;
                      setForm({
                        ...form,
                        engine,
                        config: engine === "qwen3-tts" ? { ...QWEN_DEFAULT_CONFIG } : { ...OMNI_DEFAULT_CONFIG },
                      });
                    }}
                  >
                    <option value="qwen3-tts">Qwen3-TTS</option>
                    <option value="omnivoice">OmniVoice</option>
                  </select>
                </Field>
              </div>

              <div className="flex flex-wrap gap-4 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                  />
                  사용
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_default}
                    onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                  />
                  이 엔진의 기본 Provider
                </label>
              </div>

              {form.engine === "qwen3-tts" ? (
                <QwenFields config={form.config} update={updateConfig} />
              ) : (
                <OmniFields config={form.config} update={updateConfig} />
              )}

              <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={save} disabled={saving} className="btn-primary">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  저장
                </button>
                <button type="button" onClick={test} disabled={testing || !form.id} className="btn-outline">
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  연결 테스트
                </button>
                {form.id && (
                  <button type="button" onClick={remove} disabled={saving} className="btn-ghost text-destructive">
                    <Trash2 className="h-4 w-4" />
                    삭제
                  </button>
                )}
              </div>

              {testResult && (
                <p className={`rounded-md border p-3 text-sm ${testResult.ok ? "border-emerald-500/30 text-emerald-300" : "border-destructive/40 text-destructive"}`}>
                  {testResult.ok ? "연결 성공" : "연결 실패"} · mode={testResult.mode ?? "-"}
                  {testResult.reason ? ` · ${testResult.reason}` : ""}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Provider를 선택하거나 새로 추가하세요.</p>
          )}
        </div>
      </section>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold">엔진 상태</h2>
        {!health ? (
          <p className="text-sm text-muted-foreground">로딩 중...</p>
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
            <Row label="엔진 경로" value={<Check ok={health.engine.engine_path_exists} />} />
            <Row label="엔진 Python" value={<Check ok={health.engine.engine_python_exists} />} />
            <Row label="브리지 스크립트" value={<Check ok={health.engine.bridge_script_exists} />} />
          </dl>
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

function providerToForm(provider: TTSProvider): ProviderForm {
  return {
    id: provider.id,
    name: provider.name,
    engine: provider.engine,
    enabled: provider.enabled,
    is_default: provider.is_default,
    config: provider.config,
  };
}

function normalizeForm(form: ProviderForm): TTSProviderInput {
  const config = Object.fromEntries(
    Object.entries(form.config).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value]),
  );
  return {
    name: form.name.trim(),
    engine: form.engine,
    enabled: form.enabled,
    is_default: form.is_default,
    config,
  };
}

function configString(config: Record<string, unknown>, key: string): string {
  const value = config[key];
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function QwenFields({
  config,
  update,
}: {
  config: Record<string, unknown>;
  update: (key: string, value: string) => void;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ConfigInput label="CustomVoice URL" k="base_url" config={config} update={update} placeholder="http://A100:8001" />
      <ConfigInput label="CustomVoice API Key" k="api_key" config={config} update={update} type="password" />
      <ConfigInput label="Clone Base URL" k="clone_base_url" config={config} update={update} placeholder="http://A100:8002" />
      <ConfigInput label="Clone API Key" k="clone_api_key" config={config} update={update} type="password" />
      <ConfigInput label="CustomVoice 모델" k="model" config={config} update={update} />
      <ConfigInput label="Clone 모델" k="clone_model" config={config} update={update} />
      <ConfigInput label="기본 voice" k="default_speaker" config={config} update={update} />
      <ConfigInput label="Python" k="python" config={config} update={update} />
      <ConfigInput label="디바이스" k="device" config={config} update={update} />
      <ConfigInput label="dtype" k="dtype" config={config} update={update} />
    </div>
  );
}

function OmniFields({
  config,
  update,
}: {
  config: Record<string, unknown>;
  update: (key: string, value: string) => void;
}) {
  return (
    <div className="grid gap-3">
      <ConfigInput label="엔진 경로" k="engine_path" config={config} update={update} />
      <ConfigInput label="엔진 Python" k="engine_python" config={config} update={update} />
      <ConfigInput label="디바이스" k="device" config={config} update={update} placeholder="mps | cuda | cpu" />
    </div>
  );
}

function ConfigInput({
  label,
  k,
  config,
  update,
  placeholder,
  type = "text",
}: {
  label: string;
  k: string;
  config: Record<string, unknown>;
  update: (key: string, value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <Field label={label}>
      <input
        className="input mt-1 font-mono text-xs"
        type={type}
        value={configString(config, k)}
        placeholder={placeholder}
        onChange={(e) => update(k, e.target.value)}
      />
    </Field>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
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
