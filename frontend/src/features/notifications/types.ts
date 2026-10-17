import { useEffect, useState } from "react";
import { AnalysisMode, Violation } from "../analysis/types";

export interface MonitoredCamera {
  id: string;
  name: string;
  location: string;
  status: "online" | "offline" | "unknown";
  mode: AnalysisMode;
}

// A camera event is independent from a manually uploaded analysis job.
export interface CameraAlert {
  id: string;
  cameraId: string;
  cameraName: string;
  location: string;
  detectedAt: string;
  mode: AnalysisMode;
  source?: string;
  event: Omit<Violation, "evidence_frames"> & {
    evidence_frames: (Violation["evidence_frames"][number] & {
      image_url?: string;
    })[];
  };
  readAt?: string;
  // timecode_sec and evidence timestamps are offsets from the start of this recording.
  recording?: { url: string; durationSec: number; mediaId?: string };
}

const dayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Almaty",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function localDay(value: string | number | Date = new Date()): string {
  return dayFormatter.format(value instanceof Date ? value : new Date(value));
}

export function alertTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Almaty",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function useCurrentDay() {
  const [day, setDay] = useState(() => localDay());
  useEffect(() => {
    const timer = window.setInterval(() => setDay(localDay()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  return day;
}
