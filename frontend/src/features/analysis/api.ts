import { t } from "../../i18n";
import { API_BASE_URL, JobResponse, Violation } from "./types";

const POLL_INTERVAL = 1800;
const JOB_TIMEOUT = 5 * 60 * 1000;

export function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isViolation(value: unknown): value is Violation {
  if (
    !isObject(value) ||
    typeof value.type !== "string" ||
    typeof value.description !== "string" ||
    typeof value.timecode_sec !== "number" ||
    !Number.isFinite(value.timecode_sec) ||
    value.timecode_sec < 0 ||
    !Array.isArray(value.evidence_frames)
  )
    return false;
  if (
    !value.evidence_frames.every(
      (frame) =>
        isObject(frame) &&
        typeof frame.timestamp_sec === "number" &&
        Number.isFinite(frame.timestamp_sec) &&
        frame.timestamp_sec >= 0 &&
        typeof frame.image_base64 === "string",
    )
  )
    return false;
  if (
    value.rule !== undefined &&
    (!isObject(value.rule) ||
      typeof value.rule.title !== "string" ||
      ["section", "url", "explanation"].some(
        (key) =>
          value.rule &&
          isObject(value.rule) &&
          value.rule[key] !== undefined &&
          typeof value.rule[key] !== "string",
      ))
  )
    return false;
  return true;
}

export function parseJobResponse(value: unknown): JobResponse {
  if (!isObject(value) || typeof value.job_id !== "string")
    throw new Error("Сервер вернул ответ без job_id. Проверьте контракт API.");
  if (value.status === "processing")
    return {
      job_id: value.job_id,
      status: "processing",
      progress:
        typeof value.progress === "number" && Number.isFinite(value.progress)
          ? Math.min(99, Math.max(0, value.progress))
          : undefined,
      stage: typeof value.stage === "string" ? value.stage : undefined,
    };
  if (value.status === "failed")
    return {
      job_id: value.job_id,
      status: "failed",
      error: typeof value.error === "string" ? value.error : undefined,
    };
  if (
    value.status !== "done" ||
    !["violation", "no_violation"].includes(String(value.verdict)) ||
    !Array.isArray(value.violations) ||
    !value.violations.every(isViolation)
  ) {
    throw new Error(
      "Формат результата не соответствует API из ТЗ. Проверьте verdict, violations и evidence_frames.",
    );
  }
  if (
    (value.verdict === "no_violation" && value.violations.length) ||
    (value.verdict === "violation" && !value.violations.length)
  ) {
    throw new Error("В ответе сервера вердикт противоречит списку событий.");
  }
  return value as unknown as JobResponse;
}

async function readResponse(response: Response): Promise<unknown> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 || response.status === 403)
      throw new Error(
        "Доступ к API отклонён. Проверьте API-ключ в настройках.",
      );
    if (response.status === 413)
      throw new Error(
        "Сервер отклонил размер файла. Выберите более короткий фрагмент.",
      );
    if (response.status === 415)
      throw new Error("Сервер не поддерживает этот формат. Попробуйте MOV.");
    throw new Error(
      isObject(payload) && typeof payload.error === "string"
        ? payload.error
        : t("Ошибка сервера ({0}). Повторите проверку позже.", [response.status]),
    );
  }
  return payload;
}

export async function analyzeVideo(
  file: File,
  apiKey: string,
  signal: AbortSignal,
  onUpdate: (job: JobResponse) => void,
): Promise<JobResponse> {
  const requestController = new AbortController();
  const abort = () => requestController.abort();
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) requestController.abort();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    requestController.abort();
  }, JOB_TIMEOUT);
  const headers = { "X-API-Key": apiKey, Accept: "application/json" };
  try {
    const form = new FormData();
    form.append("file", file);
    const submitted = await readResponse(
      await fetch(`${API_BASE_URL}/api/v1/analyze`, {
        method: "POST",
        headers,
        body: form,
        signal: requestController.signal,
      }),
    );
    if (
      !isObject(submitted) ||
      typeof submitted.job_id !== "string" ||
      !submitted.job_id
    )
      throw new Error("Сервер не вернул идентификатор проверки.");
    onUpdate({ job_id: submitted.job_id, status: "processing" });
    while (true) {
      const job = parseJobResponse(
        await readResponse(
          await fetch(
            `${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(submitted.job_id)}`,
            { headers, signal: requestController.signal },
          ),
        ),
      );
      if (job.job_id !== submitted.job_id)
        throw new Error("Сервер вернул результат другой проверки.");
      onUpdate(job);
      if (job.status !== "processing") return job;
      await abortableDelay(POLL_INTERVAL, requestController.signal);
    }
  } catch (error) {
    if (timedOut)
      throw new Error(
        "Сервер не вернул результат за 5 минут. Проверьте доступность сервиса и повторите попытку.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "Нет связи с API. Проверьте адрес сервера, сеть и настройки CORS.",
      );
    throw error;
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener("abort", abort);
  }
}
