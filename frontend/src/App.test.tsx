import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import { createDemoRecords } from "./data/demo";
import { useAuthStore } from "./store/useAuthStore";
import { useAnalysisStore } from "./store/useAnalysisStore";
import { useNotificationStore } from "./store/useNotificationStore";
import { createDemoAlerts, demoCameras } from "./data/demoNotifications";

const originalFetch = global.fetch;
const response = (payload: unknown) =>
  ({ ok: true, status: 200, json: async () => payload }) as Response;

beforeEach(() => {
  window.history.replaceState(null, "", "/workspace");
  window.scrollTo = jest.fn();
  useNotificationStore.setState({
    alerts: createDemoAlerts(),
    cameras: demoCameras,
    connection: "demo",
  });
  URL.createObjectURL = jest.fn(() => "blob:test");
  URL.revokeObjectURL = jest.fn();
  useAnalysisStore.setState({
    records: createDemoRecords(),
    settings: { mode: "demo", apiKey: "" },
  });
});

afterEach(() => {
  useAuthStore.getState().logout();
  global.fetch = originalFetch;
  jest.useRealTimers();
});

test("overview exposes a prominent new-check action and opens the upload sheet", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: "Контроль кассовых операций" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Демо-режим")).toBeInTheDocument();
  expect(screen.queryByLabelText("Выбрать видеофайл")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Новая проверка" }));
  expect(
    screen.getByRole("dialog", { name: "Новая проверка" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Запустить демо" })).toBeDisabled();
});

test("invalid files are rejected before analysis", () => {
  global.fetch = jest.fn();
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Новая проверка" }));
  fireEvent.change(screen.getByLabelText("Выбрать видеофайл"), {
    target: { files: [new File(["x"], "file.pdf")] },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("MOV, MP4 или WebM");
  expect(global.fetch).not.toHaveBeenCalled();
});

test("API upload completes the full UI flow and shows real no-violation result", async () => {
  useAnalysisStore.setState({ settings: { mode: "api", apiKey: "test-key" } });
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce(response({ job_id: "api-1" }))
    .mockResolvedValueOnce(
      response({
        job_id: "api-1",
        status: "done",
        verdict: "no_violation",
        violations: [],
      }),
    );
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Новая проверка" }));
  fireEvent.change(screen.getByLabelText("Выбрать видеофайл"), {
    target: { files: [new File(["video"], "camera.mov")] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Начать проверку" }));
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Нарушение не обнаружено" }),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByText("Демонстрационный результат."),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Скачать JSON" }),
  ).toBeInTheDocument();
});

test("API failure remains an error instead of falling back to demo", async () => {
  useAnalysisStore.setState({ settings: { mode: "api", apiKey: "key" } });
  global.fetch = jest.fn().mockRejectedValue(new TypeError("Network failure"));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Новая проверка" }));
  fireEvent.change(screen.getByLabelText("Выбрать видеофайл"), {
    target: { files: [new File(["video"], "camera.mov")] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Начать проверку" }));
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Проверка не завершена" }),
    ).toBeInTheDocument(),
  );
  expect(screen.getByText(/Нет связи с API/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Скачать JSON" }),
  ).not.toBeInTheDocument();
});

test("event selection updates the evidence and shows missing rules honestly", () => {
  window.history.replaceState(null, "", "/analysis/demo-001");
  render(<App />);
  expect(
    screen.getByRole("heading", {
      name: "Обнаружены признаки возможных нарушений",
    }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Перейти к событию 2/ }));
  expect(screen.getByText("Событие 2 · 00:44")).toBeInTheDocument();
  expect(
    screen.getByText(/Сервис не передал нормативный источник/),
  ).toBeInTheDocument();
});

test("history filtering has an empty state and can recover", () => {
  window.history.replaceState(null, "", "/history");
  render(<App />);
  fireEvent.change(
    screen.getByRole("textbox", { name: "Поиск по имени файла" }),
    { target: { value: "missing" } },
  );
  expect(
    screen.getByRole("heading", { name: "Проверки не найдены" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
  expect(screen.getByText("cash_desk_01.mov")).toBeInTheDocument();
});

test("API mode cannot be enabled without a key", () => {
  window.history.replaceState(null, "", "/settings");
  render(<App />);
  fireEvent.click(screen.getByRole("radio", { name: /Подключённый сервис/ }));
  fireEvent.click(screen.getByRole("button", { name: /Сохранить настройки/ }));
  expect(screen.getByRole("alert")).toHaveTextContent("Введите API-ключ");
  expect(useAnalysisStore.getState().settings.mode).toBe("demo");
  fireEvent.change(screen.getByLabelText("API-ключ *"), {
    target: { value: "session-key" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Сохранить настройки/ }));
  expect(screen.getByRole("status")).toHaveTextContent("Настройки сохранены");
  expect(useAnalysisStore.getState().settings.mode).toBe("api");
});

test("cancelling a mock job prevents late completion", async () => {
  jest.useFakeTimers();
  let id = "";
  act(() => {
    id = useAnalysisStore.getState().start();
  });
  act(() => {
    useAnalysisStore.getState().cancel(id);
  });
  await act(async () => {
    jest.advanceTimersByTime(10000);
  });
  expect(
    useAnalysisStore.getState().records.find((item) => item.id === id)?.status,
  ).toBe("cancelled");
});

test("existing backend sign-in remains accessible from profile", async () => {
  const fetchMock = jest.fn().mockResolvedValue(
    response({
      user: {
        id: 1,
        email: "demo@example.com",
        nickname: null,
        full_name: "Тестовый пользователь",
        user_type: "user",
      },
      access_token: "test-access",
      refresh_token: "test-refresh",
    }),
  );
  global.fetch = fetchMock;
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Войти в аккаунт" }));
  fireEvent.change(screen.getByLabelText("Email или никнейм"), {
    target: { value: "demo@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Пароль"), {
    target: { value: "secret123" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Войти" }));
  await waitFor(() =>
    expect(screen.getAllByText("Тестовый пользователь").length).toBeGreaterThan(
      0,
    ),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:6767/api/auth/login",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        identifier: "demo@example.com",
        password: "secret123",
      }),
    }),
  );
});

test("root is a project landing page and opens the workspace without reloading", () => {
  window.history.replaceState(null, "", "/");
  render(<App />);
  expect(
    screen.getByRole("heading", { level: 1, name: /Всё важное/ }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "Начать проверку" }));
  expect(window.location.pathname).toBe("/workspace");
  expect(
    screen.getByRole("button", { name: "Новая проверка" }),
  ).toBeInTheDocument();
});

test("the homepage demo link opens the complete report", () => {
  window.history.replaceState(null, "", "/");
  render(<App />);
  fireEvent.click(screen.getByRole("link", { name: "Посмотреть демо" }));
  expect(window.location.pathname).toBe("/analysis/demo-001");
  expect(
    screen.getByRole("heading", {
      name: "Обнаружены признаки возможных нарушений",
    }),
  ).toBeInTheDocument();
});
