import { mediaUrl } from "./client";
import {
  Alert,
  Camera,
  Page,
  parseAlert,
  parseCamera,
  parsePage,
} from "./workspace";
import { CameraAlert, MonitoredCamera } from "../features/notifications/types";
import {
  HealthIncident,
  HealthSignal,
  healthLabels,
} from "../features/monitoring/health";

interface HealthSummary {
  problems: number;
  unknown: number;
  unavailable_minutes: number;
  unknown_minutes: number;
  degraded_minutes: number;
}
export interface Monitoring {
  cameras: Camera[];
  signals: Record<string, HealthSignal>;
  incidents: Page<HealthIncident>;
  summary: HealthSummary;
  as_of: string;
}
export interface Shift {
  cameras: Camera[];
  episodes: Alert[];
  incidents: HealthIncident[];
  total: number;
  monitoring_summary: HealthSummary;
  as_of: string;
}
function object(v: unknown): asserts v is Record<string, any> {
  if (!v || typeof v !== "object" || Array.isArray(v))
    throw new Error("Некорректный ответ сервера.");
}
function valid(ok: unknown): asserts ok {
  if (!ok) throw new Error("Некорректный ответ сервера.");
}
const date = (v: unknown) =>
  typeof v === "string" &&
  /(Z|[+-]\d{2}:\d{2})$/.test(v) &&
  Number.isFinite(Date.parse(v));
function summary(v: unknown): HealthSummary {
  object(v);
  valid(
    [
      "problems",
      "unknown",
      "unavailable_minutes",
      "unknown_minutes",
      "degraded_minutes",
    ].every(
      (k) => typeof v[k] === "number" && Number.isFinite(v[k]) && v[k] >= 0,
    ),
  );
  return v as unknown as HealthSummary;
}
function incident(v: unknown): HealthIncident {
  object(v);
  valid(
    typeof v.id === "string" &&
      typeof v.cameraId === "string" &&
      v.mode === "api" &&
      ["offline", "occluded", "frozen", "poor_visibility", "unknown"].includes(
        v.kind,
      ) &&
      date(v.startedAt) &&
      (v.endedAt == null ||
        (date(v.endedAt) && Date.parse(v.endedAt) >= Date.parse(v.startedAt))),
  );
  return { ...v, endedAt: v.endedAt ?? undefined } as HealthIncident;
}
export function parseMonitoring(v: unknown): Monitoring {
  object(v);
  object(v.signals);
  valid(Array.isArray(v.cameras) && date(v.as_of) && v.ttl_seconds === 90);
  for (const [id, signal] of Object.entries(v.signals)) {
    object(signal);
    valid(
      signal.cameraId === id &&
        signal.mode === "api" &&
        Object.hasOwn(healthLabels, signal.status) &&
        date(signal.checkedAt),
    );
  }
  return {
    cameras: v.cameras.map(parseCamera),
    signals: v.signals as Record<string, HealthSignal>,
    incidents: parsePage(v.incidents, incident),
    summary: summary(v.summary),
    as_of: v.as_of,
  };
}
export function parseShift(v: unknown): Shift {
  object(v);
  valid(
    date(v.as_of) &&
      Array.isArray(v.cameras) &&
      Array.isArray(v.episodes) &&
      v.episodes.length <= 6 &&
      Number.isInteger(v.total) &&
      v.total >= v.episodes.length &&
      Array.isArray(v.incidents),
  );
  return {
    cameras: v.cameras.map(parseCamera),
    episodes: v.episodes.map(parseAlert),
    total: v.total,
    incidents: v.incidents.map(incident),
    monitoring_summary: summary(v.monitoring_summary),
    as_of: v.as_of,
  };
}
export const reviewCameras = (cameras: Camera[]): MonitoredCamera[] =>
  cameras.map((c) => ({ ...c, mode: "api" }));
export const reviewAlert = (a: Alert): CameraAlert => ({
  id: a.id,
  cameraId: a.camera_id,
  cameraName: a.camera_name,
  location: a.location,
  detectedAt: a.detected_at,
  source: a.source,
  mode: "api",
  readAt: a.read_at ?? undefined,
  event: {
    ...a.event,
    rule: a.event.rule ?? undefined,
    evidence_frames: a.event.evidence_frames.map((f) => ({
      timestamp_sec: f.timestamp_sec,
      image_base64: "",
      image_url: mediaUrl(f.image_url),
    })),
  },
  recording: a.recording
    ? {
        mediaId: a.recording.media_id,
        durationSec: a.recording.duration_sec,
        url: "",
      }
    : undefined,
});
