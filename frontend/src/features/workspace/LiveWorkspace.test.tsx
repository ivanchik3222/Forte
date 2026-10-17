import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "../../App";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { useAuthStore } from "../../store/useAuthStore";
import { apiRequest, authApi } from "../../api/client";
import { parseMedia } from "../../api/workspace";

const user = {
  id: 1,
  email: "tester@example.com",
  nickname: null,
  full_name: "Проверяющий",
  user_type: "user",
};
const record = {
  id: "saved-id",
  file_name: "camera.mp4",
  file_size: 100,
  created_at: "2026-10-17T10:00:00Z",
  duration_sec: 2,
  status: "stored",
  analysis_status: "not_requested",
  verdict: null,
  violations: [],
};
const overview = {
  date: "2026-10-17",
  today_total: 0,
  today_read: 0,
  today_unread: 0,
  unread_total: 0,
  camera_total: 0,
  media_total: 1,
  recent_alerts: [],
  recent_media: [record],
};
const response = (payload: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => payload }) as Response;
const originalFetch = global.fetch;
beforeEach(() => {
  window.scrollTo = jest.fn();
  Object.defineProperty(global, "crypto", {
    configurable: true,
    value: { randomUUID: () => "upload-key" },
  });
  useAnalysisStore.setState({ settings: { mode: "api", apiKey: "" } });
  useAuthStore.setState({
    initialized: true,
    status: "authenticated",
    user,
    error: null,
  });
  window.history.replaceState(null, "", "/workspace");
  global.fetch = jest.fn(async (input) => {
    const url = String(input);
    if (
      url.endsWith(
        "/overview?date=" +
          new Intl.DateTimeFormat("en-CA", {
            timeZone: "Asia/Almaty",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
          }).format(new Date()),
      )
    )
      return response(overview);
    if (url.includes("/cameras"))
      return response({ items: [], total: 0, page: 1, per_page: 20 });
    if (url.endsWith("/playback-url"))
      return response({
        url: "/api/v1/media/saved-id/content?token=signed",
        expires_in: 900,
      });
    if (url.endsWith("/media/saved-id")) return response(record);
    if (url.endsWith("/media")) return response(record, 201);
    return response(
      { error: { code: "not_found", message: "Not found" } },
      404,
    );
  });
});
afterEach(() => {
  global.fetch = originalFetch;
});

test("upload uses multipart JWT API and shows stored without a verdict", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Загрузить видео" }));
  fireEvent.change(screen.getByLabelText("Выбрать видеофайл"), {
    target: { files: [new File(["video"], "camera.mp4")] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить видео" }));
  await screen.findByRole("heading", { name: "camera.mp4" });
  expect(window.location.pathname).toBe("/analysis/saved-id");
  expect(
    screen.getByText(/Видео сохранено. Запустите поиск объектов/),
  ).toBeInTheDocument();
  expect(screen.queryByText("Нарушение не обнаружено")).not.toBeInTheDocument();
  const call = (global.fetch as jest.Mock).mock.calls.find((c) =>
    String(c[0]).endsWith("/media"),
  );
  expect(call[1].body).toBeInstanceOf(FormData);
  expect(call[1].headers.get("Content-Type")).toBeNull();
  expect(call[1].headers.get("Idempotency-Key")).toBe("upload-key");
});

test("direct link restores record from server without an in-memory File", async () => {
  window.history.replaceState(null, "", "/analysis/saved-id");
  useAnalysisStore.setState({ records: [] });
  render(<App />);
  await screen.findByRole("heading", { name: "camera.mp4" });
  await screen.findByRole("link", { name: "Скачать оригинал" });
  expect(
    screen.getByRole("button", { name: "Скачать JSON" }),
  ).toBeInTheDocument();
});

test("server outage remains an error and does not insert demo data", async () => {
  global.fetch = jest.fn().mockRejectedValue(new TypeError("Network failure"));
  window.history.replaceState(null, "", "/history");
  render(<App />);
  await waitFor(() =>
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0),
  );
  expect(screen.queryByText("cash_desk_01.mov")).not.toBeInTheDocument();
  expect(screen.getByText("Рабочий режим")).toBeInTheDocument();
});

test("invalid stored response cannot pretend analysis succeeded", () => {
  expect(() => parseMedia({ ...record, verdict: "no_violation" })).toThrow();
  expect(() => parseMedia({ ...record, status: "done" })).toThrow();
});

test("new review routes are available inside the authenticated workspace", async () => {
  const previous = global.fetch;
  const summary = {
    problems: 0,
    unknown: 0,
    unavailable_minutes: 0,
    unknown_minutes: 0,
    degraded_minutes: 0,
  };
  global.fetch = jest.fn(async (input, options) => {
    if (String(input).includes("/monitoring?"))
      return response({
        as_of: new Date().toISOString(),
        ttl_seconds: 90,
        cameras: [],
        signals: {},
        summary,
        incidents: { items: [], total: 0, page: 1, per_page: 50 },
      });
    if (String(input).includes("/shift?"))
      return response({
        as_of: new Date().toISOString(),
        cameras: [],
        episodes: [],
        total: 0,
        incidents: [],
        monitoring_summary: summary,
      });
    return previous(input, options);
  });
  window.history.replaceState(null, "", "/monitoring");
  render(<App />);
  await screen.findByText("В журнале нет сбоев за этот день");
  expect(
    screen.getByRole("heading", { name: "Всё ли в поле зрения?" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("link", { name: "Смена за минуту" })[0]);
  await screen.findByRole("heading", { name: "За этот день событий нет" });
  expect(
    screen.getByRole("heading", { name: "Смена за минуту" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Страница не найдена")).not.toBeInTheDocument();
});

test("startup restores the session from cookie before loading the workspace", async () => {
  useAuthStore.setState({ initialized: false, user: null, status: "idle" });
  const previousFetch = global.fetch;
  global.fetch = jest.fn(async (input, options) => {
    if (String(input).endsWith("/session-csrf"))
      return response({ csrf_token: "csrf-restored" });
    if (String(input).endsWith("/refresh"))
      return response({ user, access_token: "restored" });
    return previousFetch(input, options);
  });
  render(<App />);
  await screen.findByRole("heading", { name: "Контроль кассовых операций" });
  expect(useAuthStore.getState().accessToken).toBe("restored");
});

test.each([true, false])(
  "event details keep the server-confirmed read state (success=%s)",
  async (success) => {
    window.history.replaceState(null, "", "/notifications");
    const event = {
      id: "e1",
      camera_id: "c1",
      camera_name: "Тестовая камера",
      location: "Тест",
      detected_at: "2026-10-17T10:00:00Z",
      source: "test",
      read_at: null,
      event: {
        type: "Проверка доставки",
        description: "Тестовый сигнал",
        timecode_sec: 0,
        evidence_frames: [],
        rule: null,
      },
    };
    const previousFetch = global.fetch;
    global.fetch = jest.fn(async (input, options) => {
      const path = String(input);
      if (path.includes("/notifications?"))
        return response({ items: [event], total: 1, page: 1, per_page: 20 });
      if (path.endsWith("/notifications/e1")) return response(event);
      if (path.endsWith("/notifications/read"))
        return success
          ? response({ items: [{ id: "e1", read_at: "2026-10-17T11:00:00Z" }] })
          : response(
              { error: { message: "Не удалось сохранить просмотр" } },
              500,
            );
      return previousFetch(input, options);
    });
    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Тестовая камера/ }),
    );
    await screen.findByRole("dialog", { name: "Событие с камеры" });
    await screen.findByText(
      success ? /Просмотр сохранён/ : /Отметка просмотра не сохранена/,
    );
    if (!success) await screen.findAllByText("Не удалось сохранить просмотр");
    expect(
      screen.getByRole("dialog", { name: "Событие с камеры" }),
    ).toBeInTheDocument();
    expect(screen.queryByAltText(/Синтетическая/)).not.toBeInTheDocument();
  },
);

test("parallel expired requests share one refresh and logout clears session", async () => {
  let expired = true;
  global.fetch = jest.fn(async (input, init) => {
    const path = String(input);
    if (path.endsWith("/login"))
      return response({ user, access_token: "old", csrf_token: "csrf" });
    if (path.endsWith("/session-csrf")) return response({ csrf_token: expired ? "csrf" : "rotated-csrf" });
    if (path.endsWith("/refresh")) {
      expired = false;
      return response({ user, access_token: "new", csrf_token: "rotated-csrf" });
    }
    if (path.endsWith("/logout")) return response({ message: "Logged out" });
    return expired
      ? response({ error: { message: "Expired" } }, 401)
      : response({ ok: true });
  });
  await act(async () => {
    await authApi.login("tester", "password");
    await Promise.all([
      apiRequest("/api/v1/media"),
      apiRequest("/api/v1/cameras"),
    ]);
  });
  expect(
    (global.fetch as jest.Mock).mock.calls.filter((c) =>
      String(c[0]).endsWith("/refresh"),
    ),
  ).toHaveLength(1);
  expect(useAuthStore.getState().accessToken).toBe("new");
  await act(async () => {
    await authApi.logout();
  });
  expect(useAuthStore.getState().user).toBeNull();
});
