import { analyzeVideo, parseJobResponse } from "./api";
import { MAX_FILE_SIZE, safeSourceUrl, timecode, validateVideo } from "./types";

const originalFetch = global.fetch;
const response = (payload: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => payload }) as Response;

afterEach(() => {
  global.fetch = originalFetch;
  jest.useRealTimers();
});

test("validates actual upload constraints, including empty and oversized MOV", () => {
  expect(validateVideo(new File(["video"], "record.MOV"))).toBeNull();
  expect(validateVideo(new File(["text"], "report.pdf"))).toMatch(/MOV/);
  expect(validateVideo(new File([], "empty.mov"))).toMatch(/пустой/);
  const largeFile = new File(["v"], "large.mov");
  Object.defineProperty(largeFile, "size", { value: MAX_FILE_SIZE + 1 });
  expect(validateVideo(largeFile)).toMatch(/1 ГБ/);
});

test("accepts videos above the previous limit and exactly 1 GB", () => {
  for (const size of [300 * 1024 ** 2, 1024 ** 3]) {
    const file = new File(["v"], "shift.mp4");
    Object.defineProperty(file, "size", { value: size });
    expect(validateVideo(file)).toBeNull();
  }
});

test("rejects inconsistent verdicts and malformed evidence instead of inventing a result", () => {
  expect(() =>
    parseJobResponse({
      job_id: "1",
      status: "done",
      verdict: "violation",
      violations: [],
    }),
  ).toThrow(/противоречит/);
  expect(() =>
    parseJobResponse({
      job_id: "1",
      status: "done",
      verdict: "maybe",
      violations: [],
    }),
  ).toThrow(/Формат/);
  expect(() =>
    parseJobResponse({
      job_id: "1",
      status: "done",
      verdict: "violation",
      violations: [
        {
          type: "event",
          timecode_sec: -1,
          description: "description",
          evidence_frames: [],
        },
      ],
    }),
  ).toThrow(/Формат/);
  expect(
    parseJobResponse({
      job_id: "1",
      status: "done",
      verdict: "no_violation",
      violations: [],
    }).status,
  ).toBe("done");
});

test("uploads a MOV as multipart with API key and reads the jury result", async () => {
  const file = new File(["video"], "test.mov", { type: "video/quicktime" });
  const result = {
    job_id: "test-1",
    status: "done",
    verdict: "no_violation",
    violations: [],
  };
  const fetchMock = jest
    .fn()
    .mockResolvedValueOnce(response({ job_id: "test-1" }))
    .mockResolvedValueOnce(response(result));
  global.fetch = fetchMock;
  const update = jest.fn();
  expect(
    await analyzeVideo(
      file,
      "session-key",
      new AbortController().signal,
      update,
    ),
  ).toEqual(result);
  const upload = fetchMock.mock.calls[0];
  expect(upload[0]).toBe("http://localhost:6767/api/v1/analyze");
  expect(upload[1].body.get("file")).toBe(file);
  expect(upload[1].headers["X-API-Key"]).toBe("session-key");
  expect(upload[1].headers["Content-Type"]).toBeUndefined();
  expect(fetchMock.mock.calls[1][0]).toBe(
    "http://localhost:6767/api/v1/jobs/test-1",
  );
  expect(update).toHaveBeenLastCalledWith(result);
});

test("polls processing until done without fabricating progress", async () => {
  jest.useFakeTimers();
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce(response({ job_id: "p1" }))
    .mockResolvedValueOnce(response({ job_id: "p1", status: "processing" }))
    .mockResolvedValueOnce(
      response({
        job_id: "p1",
        status: "done",
        verdict: "no_violation",
        violations: [],
      }),
    );
  const update = jest.fn();
  const result = analyzeVideo(
    new File(["v"], "v.mov"),
    "key",
    new AbortController().signal,
    update,
  );
  for (let i = 0; i < 12; i++) await Promise.resolve();
  expect(update).toHaveBeenLastCalledWith(
    expect.objectContaining({ status: "processing", progress: undefined }),
  );
  jest.advanceTimersByTime(1800);
  expect((await result).status).toBe("done");
});

test("shows API authentication failures and rejects results from a different job", async () => {
  global.fetch = jest.fn().mockResolvedValue(response({}, 401));
  await expect(
    analyzeVideo(
      new File(["v"], "v.mov"),
      "bad",
      new AbortController().signal,
      jest.fn(),
    ),
  ).rejects.toThrow(/API-ключ/);
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce(response({ job_id: "expected" }))
    .mockResolvedValueOnce(
      response({
        job_id: "wrong",
        status: "done",
        verdict: "no_violation",
        violations: [],
      }),
    );
  await expect(
    analyzeVideo(
      new File(["v"], "v.mov"),
      "key",
      new AbortController().signal,
      jest.fn(),
    ),
  ).rejects.toThrow(/другой проверки/);
});

test("cancels in-flight network requests and enforces the five-minute timeout", async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn(
    (_url, options) =>
      new Promise((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
  ) as typeof fetch;
  const controller = new AbortController();
  const cancelled = analyzeVideo(
    new File(["v"], "v.mov"),
    "key",
    controller.signal,
    jest.fn(),
  );
  const cancelledAssertion = expect(cancelled).rejects.toHaveProperty(
    "name",
    "AbortError",
  );
  controller.abort();
  await cancelledAssertion;
  const timedOut = analyzeVideo(
    new File(["v"], "v.mov"),
    "key",
    new AbortController().signal,
    jest.fn(),
  );
  const timeoutAssertion = expect(timedOut).rejects.toThrow(/5 минут/);
  jest.advanceTimersByTime(300000);
  await timeoutAssertion;
});

test("formats long timecodes and only allows web links for regulatory sources", () => {
  expect(timecode(3661)).toBe("01:01:01");
  expect(safeSourceUrl("javascript:alert(1)")).toBeUndefined();
  expect(safeSourceUrl("https://adilet.zan.kz/rus/docs/V1900019680")).toMatch(
    /^https:/,
  );
});
