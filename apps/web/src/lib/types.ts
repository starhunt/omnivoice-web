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
