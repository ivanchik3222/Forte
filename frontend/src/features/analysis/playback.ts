import { timecode } from "./types";

export interface PlaybackRange { start: number; end: number; label: string }
export type SeekToEvidence = (seconds: number, range?: PlaybackRange) => void;

/** Preserve subsecond intervals instead of displaying a misleading 00:07–00:07. */
export function evidenceTime(seconds: number) {
  const milliseconds = Math.round(Math.max(0, seconds) * 1000);
  const fraction = milliseconds % 1000;
  return timecode(milliseconds / 1000) + (fraction ? `.${String(fraction).padStart(3, "0").replace(/0+$/, "")}` : "");
}
export function intervalTime(start: number, end: number) {
  return start === end ? evidenceTime(start) : `${evidenceTime(start)}–${evidenceTime(end)}`;
}
