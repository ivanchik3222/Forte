import { useRef, useState } from "react";
import { PlaybackRange, SeekToEvidence } from "./playback";

export function useEvidencePlayback() {
  const video = useRef<HTMLVideoElement>(null);
  const panel = useRef<HTMLElement>(null);
  const resumeAt = useRef(0);
  const pendingPlay = useRef(false);
  const currentRange = useRef<PlaybackRange | null>(null);
  const [range, setRange] = useState<PlaybackRange | null>(null);
  const [playBlocked, setPlayBlocked] = useState(false);
  const updateRange = (next: PlaybackRange | null) => { currentRange.current = next; setRange(next); };
  const play = () => {
    const player = video.current;
    if (!player) return;
    try { player.play()?.catch(() => setPlayBlocked(true)); }
    catch { setPlayBlocked(true); }
  };
  const seek: SeekToEvidence = (seconds, selection) => {
    if (!Number.isFinite(seconds)) return;
    resumeAt.current = Math.max(0, seconds);
    const duration = video.current?.duration;
    if (duration && Number.isFinite(duration)) resumeAt.current = Math.min(resumeAt.current, duration);
    const end = selection && Number.isFinite(selection.end)
      ? duration && Number.isFinite(duration) ? Math.min(selection.end, duration) : selection.end
      : 0;
    updateRange(selection && end > resumeAt.current ? { ...selection, start: resumeAt.current, end } : null);
    pendingPlay.current = true;
    setPlayBlocked(false);
    panel.current?.scrollIntoView?.({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    panel.current?.focus({ preventScroll: true });
    if (video.current && video.current.readyState >= 1) {
      video.current.currentTime = resumeAt.current;
      pendingPlay.current = false;
      play();
    }
  };
  const onLoadedMetadata = () => {
    if (!video.current) return;
    const duration = video.current.duration;
    video.current.currentTime = Number.isFinite(duration) ? Math.min(resumeAt.current, duration) : resumeAt.current;
    const selected = currentRange.current;
    if (selected && Number.isFinite(duration)) {
      const end = Math.min(selected.end, duration);
      updateRange(end > video.current.currentTime ? { ...selected, start: video.current.currentTime, end } : null);
    }
    if (pendingPlay.current) { pendingPlay.current = false; play(); }
  };
  const onTimeUpdate = () => {
    const player = video.current, selected = currentRange.current;
    if (player && selected && player.currentTime >= selected.end && !player.paused) {
      player.pause();
      player.currentTime = selected.end;
    }
  };
  const onSeeking = () => {
    const selected = currentRange.current, position = video.current?.currentTime;
    if (selected && position !== undefined && (position < selected.start - .1 || position > selected.end + .1)) updateRange(null);
  };
  const onPlay = () => {
    setPlayBlocked(false);
    const selected = currentRange.current;
    if (video.current && selected && video.current.currentTime >= selected.end) video.current.currentTime = selected.start;
  };
  return { video, panel, resumeAt, range, playBlocked, seek, clearRange: () => updateRange(null),
    onLoadedMetadata, onTimeUpdate, onSeeking, onPlay };
}
