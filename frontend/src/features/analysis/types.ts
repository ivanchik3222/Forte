import { localeCode, t } from "../../i18n";
export type AnalysisMode = "demo" | "api";
export type Verdict = "violation" | "no_violation";

export interface RuleReference {
  title: string;
  section?: string;
  url?: string;
  explanation?: string;
}

export interface EvidenceFrame {
  timestamp_sec: number;
  image_base64: string;
}

export interface Violation {
  type: string;
  timecode_sec: number;
  description: string;
  evidence_frames: EvidenceFrame[];
  // Optional extension of the jury API: absence is visible in the interface.
  rule?: RuleReference;
}

export type JobResponse =
  | { job_id: string; status: "processing"; progress?: number; stage?: string }
  | { job_id: string; status: "failed"; error?: string }
  | {
      job_id: string;
      status: "done";
      verdict: Verdict;
      violations: Violation[];
    };

export interface AnalysisRecord {
  id: string;
  jobId?: string;
  fileName: string;
  fileSize: number;
  createdAt: string;
  duration?: number;
  mode: AnalysisMode;
  status:
    | "stored"
    | "uploading"
    | "processing"
    | "done"
    | "failed"
    | "cancelled";
  progress?: number;
  stage?: string;
  verdict?: Verdict;
  violations: Violation[];
  error?: string;
  file?: File;
  videoUrl?: string;
}

export interface ConnectionSettings {
  mode: AnalysisMode;
  apiKey: string;
}

export const MAX_FILE_SIZE = 1024 * 1024 * 1024;
export const MAX_FILE_SIZE_LABEL = "1 ГБ";
export const API_BASE_URL = (
  process.env.REACT_APP_API_URL ?? "http://localhost:6767"
).replace(/\/$/, "");

export function validateVideo(file: File): string | null {
  if (!/\.(mov|mp4|webm)$/i.test(file.name))
    return "Выберите видео в формате MOV, MP4 или WebM.";
  if (!file.size) return "Файл пустой. Выберите другую запись.";
  if (file.size > MAX_FILE_SIZE)
    return t("Файл больше {0}. Загрузите более короткий фрагмент.", [MAX_FILE_SIZE_LABEL]);
  return null;
}

export function timecode(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  return `${hours ? `${hours.toString().padStart(2, "0")}:` : ""}${Math.floor(
    (safe % 3600) / 60,
  )
    .toString()
    .padStart(2, "0")}:${(safe % 60).toString().padStart(2, "0")}`;
}

export function fileSize(bytes: number): string {
  if (bytes >= 1024 ** 3)
    return t("{0} ГБ", [(bytes / 1024 ** 3).toLocaleString(localeCode(), { maximumFractionDigits: 2 })]);
  return t("{0} МБ", [(bytes / 1024 / 1024).toLocaleString(localeCode(), { maximumFractionDigits: 1 })]);
}

export function safeSourceUrl(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}
