export interface User {
  id: number;
  email: string | null;
  nickname: string | null;
  full_name: string | null;
  user_type: string;
}

interface AuthResponse {
  user: User;
  access_token: string;
  csrf_token?: string;
}
export interface UploadProgress {
  loaded: number;
  total?: number;
  transferred: boolean;
}
interface ApiRequestOptions extends RequestInit {
  onUploadProgress?: (progress: UploadProgress) => void;
}
export const apiBaseUrl = (
  process.env.REACT_APP_API_URL ?? "http://localhost:6767"
).replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}
let token: string | null = null;
let csrf = "";
let generation = 0;
let refreshPromise: Promise<AuthResponse> | null = null;
const requests = new Set<AbortController>();
let onSession: (session: AuthResponse | null) => void = () => {};
export function observeSession(callback: typeof onSession) {
  onSession = callback;
}
function applySession(session: AuthResponse | null) {
  if (
    session &&
    (!session.user ||
      !Number.isInteger(session.user.id) ||
      typeof session.access_token !== "string" ||
      !session.access_token)
  )
    throw new Error("Некорректный ответ сервера авторизации.");
  token = session?.access_token || null;
  if (session?.csrf_token) csrf = session.csrf_token;
  onSession(session);
}
function clearSession() {
  generation++;
  requests.forEach((c) => c.abort());
  requests.clear();
  csrf = "";
  token = null;
  refreshPromise = null;
  applySession(null);
  window.dispatchEvent(new Event("forte-session-cleared"));
}
async function raw<T>(
  path: string,
  options: ApiRequestOptions = {},
  access?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (access) headers.set("Authorization", `Bearer ${access}`);
  if (options.onUploadProgress && options.body instanceof FormData)
    return upload<T>(path, options, headers);
  const { onUploadProgress, ...requestOptions } = options;
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...requestOptions,
    headers,
    credentials: "include",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      payload?.error?.message ||
        payload?.message ||
        (typeof payload?.error === "string"
          ? payload.error
          : "Не удалось выполнить запрос."),
      response.status,
      payload?.error?.code,
    );
  return payload as T;
}

// Fetch cannot report upload progress. Keep the same session, retry and abort
// handling above this transport, and let the browser set the multipart boundary.
function upload<T>(
  path: string,
  options: ApiRequestOptions,
  headers: Headers,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const signal = options.signal;
    const aborted = () => new DOMException("Upload aborted", "AbortError");
    if (signal?.aborted) {
      reject(aborted());
      return;
    }
    const abort = () => xhr.abort();
    const cleanup = () => {
      signal?.removeEventListener("abort", abort);
      xhr.upload.onprogress = null;
      xhr.upload.onload = null;
    };
    xhr.upload.onprogress = (event) =>
      options.onUploadProgress?.({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : undefined,
        transferred: false,
      });
    xhr.upload.onload = (event) =>
      options.onUploadProgress?.({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : undefined,
        transferred: true,
      });
    xhr.onload = () => {
      cleanup();
      const payload = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload as T);
      else
        reject(
          new ApiError(
            payload?.error?.message ||
              payload?.message ||
              (typeof payload?.error === "string"
                ? payload.error
                : xhr.status === 413
                  ? "Сервер не принял файл такого размера. Попробуйте файл меньше или повторите позже."
                  : "Не удалось загрузить видео. Попробуйте ещё раз."),
            xhr.status,
            payload?.error?.code,
          ),
        );
    };
    xhr.onerror = () => {
      cleanup();
      reject(new TypeError("Нет связи с сервером."));
    };
    xhr.onabort = () => {
      cleanup();
      reject(aborted());
    };
    xhr.open(options.method || "POST", `${apiBaseUrl}${path}`);
    xhr.withCredentials = true;
    xhr.responseType = "json";
    headers.forEach((value, key) => xhr.setRequestHeader(key, value));
    signal?.addEventListener("abort", abort, { once: true });
    options.onUploadProgress?.({ loaded: 0, transferred: false });
    try {
      xhr.send(options.body as FormData);
    } catch (error) {
      cleanup();
      reject(error);
    }
  });
}
async function refresh(): Promise<AuthResponse> {
  if (!refreshPromise) {
    const epoch = generation;
    const rotate = async () => {
      csrf = (await raw<{ csrf_token: string }>("/api/auth/session-csrf"))
          .csrf_token;
      const session = await raw<AuthResponse>("/api/auth/refresh", {
        method: "POST",
        headers: { "X-CSRF-TOKEN": csrf },
      });
      if (epoch !== generation)
        throw new DOMException("Session changed", "AbortError");
      applySession(session);
      return session;
    };
    refreshPromise = (navigator.locks
      ? navigator.locks.request("forte-refresh", rotate)
      : rotate()).finally(() => {
      if (epoch === generation) refreshPromise = null;
    });
  }
  return refreshPromise;
}
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
  accessToken?: string,
): Promise<T> {
  const epoch = generation;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  requests.add(controller);
  try {
    let result: T;
    try {
      result = await raw<T>(
        path,
        { ...options, signal: controller.signal },
        accessToken || token || undefined,
      );
    } catch (error) {
      if (
        !(error instanceof ApiError) ||
        error.status !== 401 ||
        epoch !== generation ||
        controller.signal.aborted
      )
        throw error;
      try {
        await refresh();
      } catch (refreshError) {
        if (
          refreshError instanceof ApiError &&
          refreshError.status === 401 &&
          epoch === generation
        )
          clearSession();
        throw refreshError;
      }
      result = await raw<T>(
        path,
        { ...options, signal: controller.signal },
        token || undefined,
      );
    }
    if (epoch !== generation)
      throw new DOMException("Session changed", "AbortError");
    return result;
  } finally {
    requests.delete(controller);
    options.signal?.removeEventListener("abort", abort);
  }
}
export const authApi = {
  login: async (identifier: string, password: string, otp?: string) => {
    clearSession();
    const epoch = generation;
    const session = await raw<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password, ...(otp ? { otp } : {}) }),
    });
    if (epoch !== generation)
      throw new DOMException("Session changed", "AbortError");
    applySession(session);
    return session;
  },
  restore: refresh,
  logout: async () => {
    const revoke = async () => {
      csrf = (await raw<{ csrf_token: string }>("/api/auth/session-csrf"))
        .csrf_token;
      await raw("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-TOKEN": csrf },
      });
    };
    await (navigator.locks ? navigator.locks.request("forte-refresh", revoke) : revoke());
    clearSession();
  },
};
export function mediaUrl(path: string): string {
  if (!path.startsWith("/api/v1/"))
    throw new Error("Некорректная ссылка на файл.");
  return `${apiBaseUrl}${path}`;
}
