import { useCallback, useEffect, useState } from "react";
import { apiRequest, mediaUrl } from "../../api/client";
import { CameraAlert } from "../notifications/types";
import { safeMediaUrl } from "./model";

// Fetch on selecting an episode or opening its context. A cached playlist never
// embeds expiring playback credentials, and retries obtain a fresh signed URL.
export function useEpisodeMedia(alert: CameraAlert) {
  const id = alert.mode === "api" ? alert.recording?.mediaId : undefined;
  const [url, setUrl] = useState<string>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(id));
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setUrl(undefined);
    setError("");
    setLoading(true);
    void apiRequest<{ url: string }>(
      `/api/v1/media/${encodeURIComponent(id)}/playback-url`,
      {
        method: "POST",
        signal: controller.signal,
      },
    )
      .then((result) => {
        if (!controller.signal.aborted) setUrl(mediaUrl(result.url));
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Видео недоступно.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [id, revision]);
  return {
    url: id ? url : safeMediaUrl(alert.recording?.url),
    loading: Boolean(id) && loading,
    error,
    refresh,
    canRefresh: Boolean(id),
  };
}
