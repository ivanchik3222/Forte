import { CameraAlert, localDay } from "../notifications/types";

export const EPISODE_SECONDS = 10;
export function shiftEpisodes(
  alerts: CameraAlert[],
  day: string,
  cameraId = "all",
  limit = 6,
) {
  return alerts
    .filter(
      (a) =>
        Number.isFinite(Date.parse(a.detectedAt)) &&
        localDay(a.detectedAt) === day &&
        (cameraId === "all" || a.cameraId === cameraId),
    )
    .sort(
      (a, b) =>
        Date.parse(a.detectedAt) - Date.parse(b.detectedAt) ||
        a.id.localeCompare(b.id),
    )
    .slice(-limit);
}
export function clipBounds(
  offset: number,
  duration: number,
  before = 3,
  after = 7,
) {
  if (
    !Number.isFinite(offset) ||
    !Number.isFinite(duration) ||
    offset < 0 ||
    duration <= 0 ||
    offset >= duration
  )
    return undefined;
  return {
    start: Math.max(0, offset - before),
    end: Math.min(duration, offset + after),
  };
}
export function safeMediaUrl(url?: string) {
  if (!url) return undefined;
  try {
    const parsed = new URL(url, "https://forte.invalid");
    const local =
      url.startsWith("/") && parsed.origin === "https://forte.invalid";
    return (local || /^https?:\/\//.test(url)) &&
      ["http:", "https:"].includes(parsed.protocol) &&
      !parsed.username &&
      !parsed.password
      ? url
      : undefined;
  } catch {
    return undefined;
  }
}
export function frameSource(base64?: string) {
  return base64 && /^[A-Za-z0-9+/=\s]+$/.test(base64)
    ? `data:image/jpeg;base64,${base64.replace(/\s/g, "")}`
    : undefined;
}
