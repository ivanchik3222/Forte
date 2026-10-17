import { apiRequest, authApi } from "./client";
import { mockUploads } from "../test-utils/upload";

const originalFetch = global.fetch;
let uploads: ReturnType<typeof mockUploads>;
const session = {
  user: { id: 1 },
  access_token: "current-token",
  csrf_token: "csrf",
};
beforeEach(() => {
  uploads = mockUploads();
  global.fetch = jest.fn(
    async () =>
      ({ ok: true, status: 200, json: async () => session }) as Response,
  );
});
afterEach(() => {
  uploads.restore();
  global.fetch = originalFetch;
});
const body = () => {
  const form = new FormData();
  form.append("file", new File(["video"], "camera.mp4"));
  return form;
};

test("multipart upload reports real progress and waits for the server response", async () => {
  await authApi.login("test", "test");
  const onUploadProgress = jest.fn();
  const pending = apiRequest("/api/v1/media", {
    method: "POST",
    body: body(),
    onUploadProgress,
  });
  const request = uploads.requests[0];
  expect(request.withCredentials).toBe(true);
  expect(request.setRequestHeader).toHaveBeenCalledWith(
    "authorization",
    "Bearer current-token",
  );
  request.progress(50, 100);
  expect(onUploadProgress).toHaveBeenLastCalledWith({
    loaded: 50,
    total: 100,
    transferred: false,
  });
  request.transferred(100);
  expect(onUploadProgress).toHaveBeenLastCalledWith({
    loaded: 100,
    total: 100,
    transferred: true,
  });
  const resolved = jest.fn();
  pending.then(resolved);
  await Promise.resolve();
  expect(resolved).not.toHaveBeenCalled();
  request.respond({ id: "stored" });
  await expect(pending).resolves.toEqual({ id: "stored" });
});

test("expired upload refreshes the session and retries with the same body and key", async () => {
  await authApi.login("test", "test");
  const form = body();
  const pending = apiRequest("/api/v1/media", {
    method: "POST",
    body: form,
    headers: { "Idempotency-Key": "same-upload" },
    onUploadProgress: jest.fn(),
  });
  const retried = new Promise<void>((resolve) => {
    global.fetch = jest.fn(async () => {
      // Allow the refresh and its continuation to finish before inspecting XHR.
      setTimeout(resolve, 0);
      return {
        ok: true,
        status: 200,
        json: async () => ({ ...session, access_token: "fresh-token" }),
      } as Response;
    });
  });
  uploads.requests[0].respond({ error: { message: "Expired" } }, 401);
  await retried;
  expect(uploads.requests).toHaveLength(2);
  expect(uploads.requests[1].send).toHaveBeenCalledWith(form);
  expect(uploads.requests[1].setRequestHeader).toHaveBeenCalledWith(
    "idempotency-key",
    "same-upload",
  );
  expect(uploads.requests[1].setRequestHeader).toHaveBeenCalledWith(
    "authorization",
    "Bearer fresh-token",
  );
  uploads.requests[1].respond({ id: "stored" });
  await expect(pending).resolves.toEqual({ id: "stored" });
});

test("abort and logout stop the actual network transfer", async () => {
  await authApi.login("test", "test");
  const controller = new AbortController();
  const pending = apiRequest("/api/v1/media", {
    method: "POST",
    body: body(),
    signal: controller.signal,
    onUploadProgress: jest.fn(),
  });
  const cancelled = expect(pending).rejects.toMatchObject({
    name: "AbortError",
  });
  controller.abort();
  await cancelled;
  expect(uploads.requests[0].abort).toHaveBeenCalledTimes(1);
  const next = apiRequest("/api/v1/media", {
    method: "POST",
    body: body(),
    onUploadProgress: jest.fn(),
  });
  const signedOut = expect(next).rejects.toMatchObject({ name: "AbortError" });
  await authApi.logout();
  await signedOut;
  expect(uploads.requests[1].abort).toHaveBeenCalledTimes(1);
});

test("unknown upload length stays unknown and network errors remain retryable", async () => {
  const onUploadProgress = jest.fn();
  const pending = apiRequest("/api/v1/media", {
    method: "POST",
    body: body(),
    onUploadProgress,
  });
  const failed = expect(pending).rejects.toBeInstanceOf(TypeError);
  uploads.requests[0].progress(50);
  expect(onUploadProgress).toHaveBeenLastCalledWith({
    loaded: 50,
    total: undefined,
    transferred: false,
  });
  uploads.requests[0].onerror?.(new ProgressEvent("error"));
  await failed;
});
