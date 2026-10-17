import { apiRequest, mediaUrl } from "./client";
import { AnalysisRecord } from "../features/analysis/types";

export interface Page<T> {
  items: T[];
  page: number;
  per_page: number;
  total: number;
}
export interface Media {
  id: string;
  file_name: string;
  file_size: number;
  created_at: string;
  duration_sec: number | null;
  status: "stored";
  analysis_status: "not_requested" | "queued" | "processing" | "done" | "failed";
  verdict: 'violation' | 'no_violation' | null;
  violations: {type: string; timecode_sec: number; description: string; classification_status?: 'grounded' | 'unclassified'; rule: {title: string; section?: string; url?: string} | null}[];
}
export interface Camera {
  id: string;
  name: string;
  location: string;
  status: "unknown" | "online" | "offline";
  is_active: boolean;
}
export interface Alert {
  id: string;
  camera_id: string;
  camera_name: string;
  location: string;
  detected_at: string;
  source: string;
  read_at: string | null;
  recording?: { media_id: string; duration_sec: number } | null;
  event: {
    type: string;
    description: string;
    timecode_sec: number;
    evidence_frames: { timestamp_sec: number; image_url: string }[];
    rule?: {
      title: string;
      section?: string;
      url?: string;
      explanation?: string;
    } | null;
  };
}
export interface Source {
  id: string;
  title: string;
  number: string | null;
  document_date: string | null;
  publisher: string | null;
  url: string;
}
export interface Overview {
  date: string;
  today_total: number;
  today_read: number;
  today_unread: number;
  unread_total: number;
  camera_total: number;
  media_total: number;
  recent_alerts: Alert[];
  recent_media: Media[];
  monitoring_summary?: {
    problems: number;
    unknown: number;
    unavailable_minutes: number;
    unknown_minutes: number;
    degraded_minutes: number;
  };
}
export interface Capabilities {
  uploads: boolean;
  analysis: boolean;
  camera_stream: boolean;
  formats: string[];
  max_file_size: number;
}
const object = (v: unknown): v is Record<string, any> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const date = (v: unknown) =>
  typeof v === "string" &&
  Number.isFinite(Date.parse(v)) &&
  /(Z|[+-]\d{2}:\d{2})$/.test(v);
const number = (v: unknown) =>
  typeof v === "number" && Number.isFinite(v) && v >= 0;
function requireValue(ok: unknown): asserts ok {
  if (!ok) throw new Error("Некорректный ответ сервера.");
}
export function parseMedia(v: unknown): Media {
  requireValue(
    object(v) &&
      typeof v.id === "string" &&
      typeof v.file_name === "string" &&
      number(v.file_size) &&
      date(v.created_at) &&
      (v.duration_sec === null || number(v.duration_sec)) &&
      v.status === "stored" &&
      ["not_requested", "queued", "processing", "done", "failed"].includes(v.analysis_status) &&
      (v.verdict === null || (v.analysis_status === 'done' && ['violation','no_violation'].includes(v.verdict))) &&
      Array.isArray(v.violations) &&
      ((v.verdict === 'violation') === (v.violations.length > 0)) &&
      v.violations.every((e: any)=>object(e) && typeof e.type==='string' && number(e.timecode_sec) &&
        typeof e.description==='string' && (e.classification_status==='unclassified' ? e.rule===null : object(e.rule) && typeof e.rule.title==='string')),
  );
  return v as unknown as Media;
}
export function parseAlert(v: unknown): Alert {
  requireValue(
    object(v) &&
      ["id", "camera_id", "camera_name", "location", "source"].every(
        (k) => typeof v[k] === "string",
      ) &&
      date(v.detected_at) &&
      (v.read_at === null || date(v.read_at)) &&
      object(v.event),
  );
  const e = v.event;
  requireValue(
    typeof e.type === "string" &&
      typeof e.description === "string" &&
      number(e.timecode_sec) &&
      Array.isArray(e.evidence_frames),
  );
  e.evidence_frames.forEach((f: unknown) => {
    requireValue(
      object(f) && number(f.timestamp_sec) && typeof f.image_url === "string",
    );
    mediaUrl(f.image_url);
  });
  if (e.rule != null)
    requireValue(
      object(e.rule) &&
        typeof e.rule.title === "string" &&
        ["section", "url", "explanation"].every(
          (k) => e.rule[k] == null || typeof e.rule[k] === "string",
        ),
    );
  if (v.recording != null)
    requireValue(
      object(v.recording) &&
        typeof v.recording.media_id === "string" &&
        number(v.recording.duration_sec) &&
        v.recording.duration_sec > e.timecode_sec,
    );
  return v as unknown as Alert;
}
export function parseCamera(v: unknown): Camera {
  requireValue(
    object(v) &&
      ["id", "name", "location"].every((k) => typeof v[k] === "string") &&
      ["unknown", "online", "offline"].includes(v.status) &&
      typeof v.is_active === "boolean",
  );
  return v as unknown as Camera;
}
export function parseSource(v: unknown): Source {
  requireValue(
    object(v) &&
      typeof v.id === "string" &&
      typeof v.title === "string" &&
      typeof v.url === "string" &&
      ["number", "document_date", "publisher"].every(
        (k) => v[k] === null || typeof v[k] === "string",
      ),
  );
  return v as unknown as Source;
}
export function parsePage<T>(v: unknown, parse: (item: unknown) => T): Page<T> {
  requireValue(
    object(v) &&
      Array.isArray(v.items) &&
      Number.isInteger(v.total) &&
      v.total >= 0 &&
      Number.isInteger(v.page) &&
      v.page >= 1 &&
      Number.isInteger(v.per_page) &&
      v.per_page >= 1,
  );
  return {
    items: v.items.map(parse),
    page: v.page,
    per_page: v.per_page,
    total: v.total,
  };
}
export function parseOverview(v: unknown): Overview {
  requireValue(
    object(v) &&
      typeof v.date === "string" &&
      [
        "today_total",
        "today_read",
        "today_unread",
        "unread_total",
        "camera_total",
        "media_total",
      ].every((k) => number(v[k])) &&
      Array.isArray(v.recent_alerts) &&
      Array.isArray(v.recent_media),
  );
  if (v.monitoring_summary != null) {
    requireValue(
      object(v.monitoring_summary) &&
        [
          "problems",
          "unknown",
          "unavailable_minutes",
          "unknown_minutes",
          "degraded_minutes",
        ].every((k) => number(v.monitoring_summary[k])),
    );
  }
  return {
    ...v,
    recent_alerts: v.recent_alerts.map(parseAlert),
    recent_media: v.recent_media.map(parseMedia),
  } as Overview;
}
export const asRecord = (m: Media): AnalysisRecord => ({
  id: m.id,
  fileName: m.file_name,
  fileSize: m.file_size,
  createdAt: m.created_at,
  duration: m.duration_sec ?? undefined,
  status: m.analysis_status === "not_requested" ? "stored" : m.analysis_status === "queued" ? "processing" : m.analysis_status,
  mode: "api",
  verdict: m.verdict ?? undefined,
  violations: m.violations.map(v=>({...v,rule:v.rule ?? undefined,evidence_frames:[]})),
});
export async function load<T>(
  path: string,
  parse: (v: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  return parse(await apiRequest<unknown>(`/api/v1${path}`, { signal }));
}
