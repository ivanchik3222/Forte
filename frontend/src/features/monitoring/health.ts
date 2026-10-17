import { useEffect, useState } from "react";
import { AnalysisMode } from "../analysis/types";
import { MonitoredCamera } from "../notifications/types";

export type HealthIssue = "offline" | "occluded" | "frozen" | "poor_visibility";
export type HealthStatus = HealthIssue | "observing" | "unknown";
export interface HealthSignal {
  cameraId: string;
  mode: AnalysisMode;
  status: Exclude<HealthStatus, "unknown">;
  checkedAt: string;
}
export interface HealthIncident {
  id: string;
  cameraId: string;
  mode: AnalysisMode;
  kind: HealthIssue;
  startedAt: string;
  endedAt?: string;
}

export const healthLabels: Record<HealthStatus, string> = {
  observing: "Наблюдение доступно",
  offline: "Нет связи",
  occluded: "Объектив закрыт",
  frozen: "Кадр завис",
  poor_visibility: "Плохой обзор",
  unknown: "Нет свежих данных",
};
export const healthDescriptions: Record<HealthStatus, string> = {
  observing:
    "Сервис подтверждает получение изображения и видимость рабочей зоны.",
  offline:
    "Поток недоступен. События в этот период могли остаться незамеченными.",
  occluded: "Рабочая зона перекрыта. Проверьте, не закрыт ли объектив камеры.",
  frozen: "Изображение не обновляется. Проверьте поток и подключение камеры.",
  poor_visibility:
    "Рабочая зона видна не полностью. Проверьте ракурс и освещение.",
  unknown: "Доступность наблюдения не подтверждена свежей проверкой сервиса.",
};
export const issueKinds: HealthIssue[] = [
  "offline",
  "occluded",
  "frozen",
  "poor_visibility",
];
export const HEALTH_TTL_MS = 90_000;

export function cameraHealth(
  camera: MonitoredCamera,
  signal: HealthSignal | undefined,
  connection: "demo" | "connected" | "disconnected",
  now = Date.now(),
): HealthStatus {
  if (
    !signal ||
    signal.mode !== camera.mode ||
    signal.cameraId !== camera.id ||
    connection === "disconnected" ||
    (connection === "demo") !== (camera.mode === "demo")
  )
    return "unknown";
  const age = now - Date.parse(signal.checkedAt);
  if (
    !Number.isFinite(age) ||
    age < 0 ||
    (signal.mode === "api" && age > HEALTH_TTL_MS)
  )
    return "unknown";
  return signal.status;
}

export function dayBounds(day: string) {
  const start = Date.parse(`${day}T00:00:00+05:00`);
  return { start, end: start + 86_400_000 };
}

export function incidentWindow(
  incident: HealthIncident,
  day: string,
  now = Date.now(),
) {
  const bounds = dayBounds(day);
  const start = Math.max(Date.parse(incident.startedAt), bounds.start);
  const end = Math.min(
    incident.endedAt ? Date.parse(incident.endedAt) : now,
    bounds.end,
    now,
  );
  return Number.isFinite(start) && Number.isFinite(end) && end >= start
    ? { start, end }
    : undefined;
}

// Union intervals per camera: simultaneous outages on different cameras are camera-minutes.
export function unavailableMinutes(
  incidents: HealthIncident[],
  day: string,
  now = Date.now(),
) {
  const byCamera = new Map<string, { start: number; end: number }[]>();
  incidents
    .filter((i) => i.kind !== "poor_visibility")
    .forEach((i) => {
      const window = incidentWindow(i, day, now);
      if (window)
        byCamera.set(i.cameraId, [...(byCamera.get(i.cameraId) || []), window]);
    });
  let ms = 0;
  byCamera.forEach((windows) => {
    let end = 0;
    windows
      .sort((a, b) => a.start - b.start)
      .forEach((w) => {
        ms += Math.max(0, w.end - Math.max(w.start, end));
        end = Math.max(end, w.end);
      });
  });
  return ms / 60_000;
}

export function useMonitoringNow() {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return Math.max(now, Date.now());
}
