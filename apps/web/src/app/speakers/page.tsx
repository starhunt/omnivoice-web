"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Star, Trash2, Upload } from "lucide-react";
import { api, speakerRefUrl } from "@/lib/api";
import type { Speaker } from "@/lib/types";

export default function SpeakersPage() {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [form, setForm] = useState({ name: "", tags: "", note: "", language_hint: "", ref_transcript: "" });
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = async () => {
    setLoading(true);
    try {
      setSpeakers(await api.listSpeakers());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setErr("오디오 파일을 선택하세요.");
      return;
    }
    setErr(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("name", form.name);
      fd.append("tags", form.tags);
      if (form.note) fd.append("note", form.note);
      if (form.language_hint) fd.append("language_hint", form.language_hint);
      if (form.ref_transcript) fd.append("ref_transcript", form.ref_transcript);
      fd.append("audio", file);
      await api.createSpeaker(fd);
      setForm({ name: "", tags: "", note: "", language_hint: "", ref_transcript: "" });
      if (fileRef.current) fileRef.current.value = "";
      await reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const toggleFavorite = async (s: Speaker) => {
    await api.patchSpeaker(s.id, { is_favorite: !s.is_favorite });
    await reload();
  };

  const remove = async (s: Speaker) => {
    if (!confirm(`'${s.name}' 화자를 삭제하시겠습니까? (소프트 삭제, 30일 후 영구)`)) return;
    await api.deleteSpeaker(s.id);
    await reload();
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">화자 라이브러리</h1>
        <p className="text-sm text-muted-foreground">
          참조 오디오를 업로드하여 화자를 등록하고 재사용합니다.
        </p>
      </header>

      {err && <div className="card border-destructive/40 text-sm text-destructive">{err}</div>}

      <section className="card">
        <h2 className="mb-3 text-sm font-semibold">신규 등록</h2>
        <form onSubmit={handleCreate} className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="label">이름 *</label>
            <input
              className="input mt-1"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="예: 내 기본 한국어"
            />
          </div>
          <div>
            <label className="label">태그 (쉼표 구분)</label>
            <input
              className="input mt-1"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="예: ko,남성,차분"
            />
          </div>
          <div>
            <label className="label">언어 힌트</label>
            <input
              className="input mt-1"
              value={form.language_hint}
              onChange={(e) => setForm({ ...form, language_hint: e.target.value })}
              placeholder="ko, en, zh, …"
            />
          </div>
          <div>
            <label className="label">참조 오디오 *</label>
            <input
              ref={fileRef}
              type="file"
              accept="audio/wav,audio/mpeg,audio/flac,audio/ogg,audio/mp4,.wav,.mp3,.flac,.ogg,.m4a"
              className="input mt-1"
              required
            />
            <p className="mt-1 text-xs text-muted-foreground">3–10초 권장, 24kHz 자동 리샘플</p>
          </div>
          <div className="md:col-span-2">
            <label className="label">전사 텍스트 (선택, 정확도 향상)</label>
            <textarea
              className="textarea mt-1"
              rows={2}
              value={form.ref_transcript}
              onChange={(e) => setForm({ ...form, ref_transcript: e.target.value })}
              placeholder="참조 오디오에서 말한 내용"
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">노트</label>
            <textarea
              className="textarea mt-1"
              rows={2}
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder="자유 메모"
            />
          </div>
          <div className="md:col-span-2">
            <button type="submit" disabled={uploading} className="btn-primary">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {uploading ? "업로드 중…" : "등록"}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h2 className="mb-3 text-sm font-semibold">등록된 화자 ({speakers.length})</h2>
        {loading ? (
          <p className="text-sm text-muted-foreground">로딩 중…</p>
        ) : speakers.length === 0 ? (
          <p className="text-sm text-muted-foreground">아직 화자가 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="pb-2 pr-2">★</th>
                  <th className="pb-2 pr-2">이름</th>
                  <th className="pb-2 pr-2">태그</th>
                  <th className="pb-2 pr-2">언어</th>
                  <th className="pb-2 pr-2">샘플</th>
                  <th className="pb-2 pr-2">사용 횟수</th>
                  <th className="pb-2 pr-2">생성일</th>
                  <th className="pb-2 pr-2"></th>
                </tr>
              </thead>
              <tbody>
                {speakers.map((s) => (
                  <tr key={s.id} className="border-b border-border last:border-0">
                    <td className="py-3 pr-2">
                      <button
                        type="button"
                        onClick={() => toggleFavorite(s)}
                        aria-label="즐겨찾기 토글"
                      >
                        <Star
                          className={`h-4 w-4 ${
                            s.is_favorite ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"
                          }`}
                        />
                      </button>
                    </td>
                    <td className="py-3 pr-2 font-medium">{s.name}</td>
                    <td className="py-3 pr-2 text-muted-foreground">{s.tags.join(", ") || "—"}</td>
                    <td className="py-3 pr-2 text-muted-foreground">{s.language_hint || "—"}</td>
                    <td className="py-3 pr-2">
                      {s.source_audio_path ? (
                        <audio src={speakerRefUrl(s.id)} controls preload="none" className="h-8 w-40" />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3 pr-2 text-muted-foreground">{s.usage_count}</td>
                    <td className="py-3 pr-2 text-muted-foreground">
                      {new Date(s.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 pr-2 text-right">
                      <button
                        type="button"
                        onClick={() => remove(s)}
                        className="text-muted-foreground hover:text-destructive"
                        aria-label="삭제"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
