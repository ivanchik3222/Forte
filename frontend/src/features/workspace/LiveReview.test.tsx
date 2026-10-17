import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MonitoringPage } from "../../pages/MonitoringPage";
import { ShiftPage } from "../../pages/ShiftPage";
import { localDay } from "../notifications/types";
import { useNotificationStore } from "../../store/useNotificationStore";
import { parseMonitoring, parseShift } from "../../api/review";
import { createDemoAlerts, demoCameras } from "../../data/demoNotifications";
import { createDemoHealth } from "../../data/demoMonitoring";

const originalFetch = global.fetch;
const response = (data: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => data }) as Response;
const cameras = [
  {
    id: "real-camera",
    name: "Серверная камера",
    location: "Астана",
    status: "offline",
    is_active: true,
  },
];
const summary = {
  problems: 1,
  unknown: 0,
  unavailable_minutes: 14,
  unknown_minutes: 2,
  degraded_minutes: 3,
};
const incident = {
  id: "interval",
  cameraId: "real-camera",
  mode: "api",
  kind: "offline",
  startedAt: "2026-10-17T07:10:00Z",
  endedAt: "2026-10-17T07:24:00Z",
};
const monitoring = () => ({
  cameras,
  summary,
  ttl_seconds: 90,
  as_of: new Date().toISOString(),
  signals: {
    "real-camera": {
      cameraId: "real-camera",
      mode: "api",
      status: "offline",
      checkedAt: new Date().toISOString(),
    },
  },
  incidents: { items: [incident], page: 1, per_page: 50, total: 51 },
});
const alert = (i = 0) => ({
  id: `event-${i}`,
  camera_id: "real-camera",
  camera_name: "Серверная камера",
  location: "Астана",
  detected_at: new Date(Date.now() - (10 - i) * 60000).toISOString(),
  source: "manual",
  read_at: null,
  recording: { media_id: "record", duration_sec: 100 },
  event: {
    type: `Эпизод с сервера ${i}`,
    description: "Описание специалиста",
    timecode_sec: 20 + i,
    evidence_frames: [],
    rule: null,
  },
});
const shift = () => ({
  as_of: new Date().toISOString(),
  cameras,
  episodes: [alert(), alert(1)],
  total: 20,
  incidents: [incident],
  monitoring_summary: summary,
});
const mount = (component: React.ReactNode) =>
  render(
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      {component}
    </MemoryRouter>,
  );

beforeEach(() => {
  jest.useFakeTimers().setSystemTime(new Date("2026-10-17T09:00:00Z"));
  useNotificationStore.setState({
    alerts: createDemoAlerts(),
    cameras: demoCameras,
    connection: "demo",
    ...createDemoHealth(),
  });
  jest.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  window.scrollTo = jest.fn();
  global.fetch = jest.fn(async (input) => {
    const url = String(input);
    if (url.includes("/monitoring?")) return response(monitoring());
    if (url.includes("/shift?")) return response(shift());
    if (url.endsWith("/playback-url"))
      return response({
        url: "/api/v1/media/record/content?token=first",
        expires_in: 900,
      });
    if (url.endsWith("/notifications/read"))
      return response({
        items: [{ id: "event-0", read_at: new Date().toISOString() }],
      });
    throw new Error(`Unexpected URL: ${url}`);
  });
});
afterEach(() => {
  global.fetch = originalFetch;
  jest.restoreAllMocks();
  jest.useRealTimers();
});

test("monitoring uses server history, totals and pagination without demo controls", async () => {
  mount(<MonitoringPage live />);
  await screen.findByText("Наблюдение было недоступно");
  expect(screen.queryByText("Проверить сценарий сбоя")).not.toBeInTheDocument();
  expect(screen.getByText("Интервалов: 51 · Страница 1")).toBeInTheDocument();
  expect(
    screen.getByText("14", {
      exact: false,
      selector: ".health-metrics strong",
    }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Далее" }));
  await waitFor(() =>
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("page=2"),
      expect.anything(),
    ),
  );
  await act(async () => {
    fireEvent.change(screen.getByLabelText("Камера контроля"), {
      target: { value: "real-camera" },
    });
  });
  await waitFor(() =>
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("page=1&camera_id=real-camera"),
      expect.anything(),
    ),
  );
});

test("API failure shows unknown connection and does not fabricate an empty healthy day", async () => {
  global.fetch = jest.fn().mockRejectedValue(new TypeError("Нет соединения"));
  mount(<MonitoringPage live />);
  await screen.findByRole("alert");
  expect(
    screen.queryByText("В журнале нет сбоев за этот день"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText("Демонстрационное состояние"),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/Связь с сервисом потеряна/)).toBeInTheDocument();
});

test("disconnected monitoring keeps the journal at its last confirmed snapshot", async () => {
  const data = monitoring();
  data.incidents.items = [{ ...incident, endedAt: null as unknown as string }];
  data.incidents.total = 1;
  let available = true;
  global.fetch = jest.fn(async () => {
    if (!available) throw new TypeError("Нет соединения");
    return response(data);
  });
  mount(<MonitoringPage live />);
  await screen.findByText(
    "Проблема ещё не устранена · События могли остаться незамеченными",
  );
  available = false;
  await act(async () => {
    jest.advanceTimersByTime(180000);
  });
  await screen.findByRole("alert");
  expect(
    screen.queryByText("сейчас", { selector: ".health-incident-time span" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("14:00", { selector: ".health-incident-time span" }),
  ).toBeInTheDocument();
});

test("shift opens signed recording, seeks, and opens full context with a new URL", async () => {
  mount(<ShiftPage live />);
  const video = (await screen.findByLabelText(
    "Фрагмент записи события",
  )) as HTMLVideoElement;
  expect(video.src).toContain("/api/v1/media/record/content?token=first");
  expect(
    screen.getByText("Отметка специалиста", { exact: false }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Демо-событие", { exact: false }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/Последние 6 из 20 событий/)).toBeInTheDocument();
  Object.defineProperty(video, "duration", { configurable: true, value: 100 });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(17);
  fireEvent.click(screen.getByRole("button", { name: "Смотреть подборку" }));
  fireEvent.click(screen.getByRole("button", { name: "Что было до и после" }));
  const context = (await screen.findByLabelText(
    "Полная запись с контекстом",
  )) as HTMLVideoElement;
  Object.defineProperty(context, "duration", {
    configurable: true,
    value: 100,
  });
  fireEvent.loadedMetadata(context);
  expect(context.currentTime).toBe(5);
  expect(
    (global.fetch as jest.Mock).mock.calls.filter(([url]) =>
      String(url).endsWith("/playback-url"),
    ),
  ).toHaveLength(2);
});

test("read failure remains retryable; success is persisted through the API without mutating demo data", async () => {
  let fail = true;
  const fetchBefore = global.fetch;
  global.fetch = jest.fn(async (input, init) =>
    String(input).endsWith("/notifications/read") && fail
      ? response(
          {
            error: {
              code: "write_failed",
              message: "Не удалось сохранить просмотр",
            },
          },
          500,
        )
      : fetchBefore(input, init),
  );
  const unchanged = useNotificationStore.getState().alerts;
  const changed = jest.fn();
  mount(<ShiftPage live onChanged={changed} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Отметить просмотренным" }),
  );
  await screen.findByText("Не удалось сохранить просмотр");
  expect(
    screen.getByRole("button", { name: "Отметить просмотренным" }),
  ).toBeEnabled();
  fail = false;
  fireEvent.click(
    screen.getByRole("button", { name: "Отметить просмотренным" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Отмечено как просмотренное" }),
    ).toBeDisabled(),
  );
  expect(changed).toHaveBeenCalledTimes(1);
  expect(useNotificationStore.getState().alerts).toBe(unchanged);
});

test("expired or failed video link can be renewed without rebuilding the playlist", async () => {
  let version = 0;
  const previous = global.fetch;
  global.fetch = jest.fn(async (input, init) =>
    String(input).endsWith("/playback-url")
      ? response({
          url: `/api/v1/media/record/content?token=${++version}`,
          expires_in: 900,
        })
      : previous(input, init),
  );
  mount(<ShiftPage live />);
  fireEvent.error(await screen.findByLabelText("Фрагмент записи события"));
  await screen.findByText(/Видео недоступно или таймкод/);
  fireEvent.click(
    screen.getByRole("button", { name: "Обновить ссылку на видео" }),
  );
  const video = (await screen.findByLabelText(
    "Фрагмент записи события",
  )) as HTMLVideoElement;
  expect(video.src).toContain("token=2");
  expect(
    screen.getByRole("button", { name: "Смотреть подборку" }),
  ).toBeInTheDocument();
});

test("polling the playlist does not rewind the selected episode", async () => {
  mount(<ShiftPage live />);
  await screen.findByLabelText("Фрагмент записи события");
  fireEvent.click(screen.getByRole("button", { name: "Следующий эпизод" }));
  await screen.findByLabelText("Фрагмент записи события");
  await act(async () => {
    jest.advanceTimersByTime(15000);
  });
  expect(
    screen.getByRole("heading", { name: "Эпизод с сервера 1" }),
  ).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining(`/shift?date=${localDay()}`),
    expect.anything(),
  );
});

test("new response validators reject unknown statuses, reversed intervals and external media paths", () => {
  expect(() =>
    parseMonitoring({
      ...monitoring(),
      signals: { broken: { status: "healthy" } },
    }),
  ).toThrow();
  expect(() =>
    parseShift({
      ...shift(),
      incidents: [{ ...incident, endedAt: "2026-10-16T00:00:00Z" }],
    }),
  ).toThrow();
  expect(() =>
    parseShift({
      ...shift(),
      episodes: [
        {
          ...alert(),
          event: {
            ...alert().event,
            evidence_frames: [
              {
                timestamp_sec: 10,
                image_url: "https://external.invalid/private.jpg",
              },
            ],
          },
        },
      ],
    }),
  ).toThrow();
});
