export type Speaker = {
  id: string;
  name: string;
  tags: string[];
  note: string | null;
  language_hint: string | null;
  ref_transcript: string | null;
  source_audio_path: string | null;
  prompt_blob_path: string | null;
  is_favorite: boolean;
  usage_count: number;
  last_used_at: string | null;
  created_at: string;
};

export type TTSParams = {
  num_step: number;
  guidance_scale: number;
  denoise: boolean;
  speed: number | null;
  duration: number | null;
  t_shift: number;
  position_temperature: number;
  class_temperature: number;
  layer_penalty_factor: number;
  preprocess_prompt: boolean;
  postprocess_output: boolean;
  audio_chunk_duration: number;
  audio_chunk_threshold: number;
};

export type VoiceDesign = {
  gender?: string | null;
  age?: string | null;
  pitch?: string | null;
  style?: string | null;
  english_accent?: string | null;
  chinese_dialect?: string | null;
};

export type TTSRequest = {
  text: string;
  speaker_id?: string | null;
  language?: string | null;
  instruct?: string | null;
  design?: VoiceDesign | null;
  params: TTSParams;
  format: "wav" | "mp3";
  project_id?: string | null;
  engine?: "auto" | "omnivoice" | "qwen3-tts";
};

export type TTSResponse = {
  generation_id: string;
  audio_url: string | null;
  duration_sec: number | null;
  rtf: number | null;
  status: string;
  created_at: string;
};

export type Generation = {
  id: string;
  project_id: string | null;
  mode: string;
  text: string;
  language: string | null;
  speaker_id: string | null;
  instruct: string | null;
  params_json: Record<string, unknown>;
  audio_path: string | null;
  audio_format: string;
  duration_sec: number | null;
  rtf: number | null;
  status: string;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

export type Job = {
  id: string;
  type: "tts" | "podcast" | string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled" | string;
  generation_id: string | null;
  request_json: Record<string, unknown>;
  progress_current: number;
  progress_total: number;
  progress_message: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: {
    current: number;
    total: number;
    message: string | null;
  };
  audio_url: string | null;
};

export type JobCreateResponse = {
  job_id: string;
  generation_id: string;
  status: string;
};

export type PodcastSegment = {
  speaker_id: string;
  text: string;
  label?: string | null;
  language?: string | null;
};

export type PodcastJobRequest = {
  title?: string | null;
  segments: PodcastSegment[];
  language?: string | null;
  params: TTSParams;
  format: "wav" | "mp3";
  pause_ms: number;
  project_id?: string | null;
  engine?: "auto" | "omnivoice" | "qwen3-tts";
};

export type EngineInfo = {
  id: string;
  name: string;
  available: boolean;
  mode: string;
  reason: string | null;
  python: string | null;
  path: string | null;
  model: string | null;
  capabilities: {
    supports_voice_clone: boolean;
    supports_voice_design: boolean;
    supports_custom_voices: boolean;
    supports_native_dialogue: boolean;
    supports_streaming: boolean;
    max_speakers: number;
    languages: string[];
  };
};

export type EnginesResponse = {
  default_engine: string;
  selected_engine: string | null;
  engines: EngineInfo[];
};

export type LanguageEntry = {
  code: string;
  name: string;
  english_name: string | null;
};

export type VoiceAttributeOptions = {
  gender: string[];
  age: string[];
  pitch: string[];
  style: string[];
  english_accent: string[];
  chinese_dialect: string[];
};

export type Health = {
  status: string;
  version: string;
  engine: {
    engine_path_exists: boolean;
    engine_python_exists: boolean;
    bridge_script_exists: boolean;
    mode: "live" | "stub";
  };
  device: string;
};

export const DEFAULT_TTS_PARAMS: TTSParams = {
  num_step: 32,
  guidance_scale: 2.0,
  denoise: true,
  speed: null,
  duration: null,
  t_shift: 0.1,
  position_temperature: 5.0,
  class_temperature: 0.0,
  layer_penalty_factor: 5.0,
  preprocess_prompt: true,
  postprocess_output: true,
  audio_chunk_duration: 15.0,
  audio_chunk_threshold: 30.0,
};
