import { useCallback, useEffect, useRef, useState } from "react";
import { load } from "../../api/workspace";

export function useResource<T>(
  path: string,
  parse: (v: unknown) => T,
  poll = false,
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const parser = useRef(parse);
  parser.current = parse;
  const previousPath = useRef("");
  const refresh = useCallback(() => setRevision((x) => x + 1), []);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    let failures = 0;
    if (previousPath.current !== path) {
      setData(undefined);
      previousPath.current = path;
    }
    setError("");
    setLoading(true);
    const run = async () => {
      if (controller || stopped) return;
      controller = new AbortController();
      try {
        const result = await load(path, parser.current, controller.signal);
        if (!stopped) {
          setData(result);
          setError("");
          failures = 0;
        }
      } catch (e) {
        if (
          !stopped &&
          !(e instanceof DOMException && e.name === "AbortError")
        ) {
          setError(e instanceof Error ? e.message : "Нет связи с сервером.");
          failures++;
        }
      } finally {
        controller = undefined;
        if (!stopped) {
          setLoading(false);
          if (poll)
            timer = setTimeout(
              () => {
                if (!document.hidden) void run();
              },
              Math.min(60000, 15000 * 2 ** failures),
            );
        }
      }
    };
    const visible = () => {
      if (!document.hidden) {
        clearTimeout(timer);
        void run();
      }
    };
    void run();
    if (poll) document.addEventListener("visibilitychange", visible);
    return () => {
      stopped = true;
      controller?.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [path, revision, poll]);
  return { data, error, loading, refresh };
}
