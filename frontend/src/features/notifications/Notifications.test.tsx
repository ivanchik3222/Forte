import { useAnalysisStore } from "../../store/useAnalysisStore";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import App from "../../App";
import { createDemoAlerts, demoCameras } from "../../data/demoNotifications";
import { useNotificationStore } from "../../store/useNotificationStore";
import { localDay } from "./types";

beforeEach(() => {
  useAnalysisStore.setState({settings:{mode:"demo",apiKey:""}});
  jest.useFakeTimers().setSystemTime(new Date("2026-10-17T09:00:00Z"));
  window.history.replaceState(null, "", "/notifications");
  window.scrollTo = jest.fn();
  useNotificationStore.setState({
    alerts: createDemoAlerts(),
    cameras: demoCameras,
    connection: "demo",
  });
});

afterEach(() => jest.useRealTimers());

const shownEvents = () =>
  within(screen.getByRole("list", { name: "События с камер" })).getAllByRole(
    "button",
  );

test("camera and day filters work together, and bulk read affects only shown events", () => {
  render(<App />);
  expect(shownEvents()).toHaveLength(4);
  fireEvent.change(screen.getByLabelText("Камера оповещений"), {
    target: { value: "camera-01" },
  });
  expect(shownEvents()).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Прочитать показанные" }));
  expect(
    useNotificationStore
      .getState()
      .alerts.filter((item) => !item.readAt)
      .map((item) => item.id),
  ).toEqual(["camera-demo-2", "camera-demo-3"]);
  fireEvent.change(screen.getByLabelText("Камера оповещений"), {
    target: { value: "all" },
  });
  fireEvent.change(screen.getByLabelText("День оповещений"), {
    target: { value: "2026-10-16" },
  });
  expect(shownEvents()).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Сегодня" }));
  expect(shownEvents()).toHaveLength(4);
});

test("opening an unread event marks it read while keeping its detail sheet open", () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /Новые 3/ }));
  fireEvent.click(shownEvents()[0]);
  const dialog = screen.getByRole("dialog", { name: "Событие с камеры" });
  expect(
    within(dialog).getByRole("heading", {
      name: "Наличные оставлены без наблюдения",
    }),
  ).toBeInTheDocument();
  expect(useNotificationStore.getState().alerts[0].readAt).toBeDefined();
  expect(
    within(dialog).getByText(/Демонстрационное событие/),
  ).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Закрыть окно" }));
  act(() => {
    jest.advanceTimersByTime(230);
  });
  expect(shownEvents()).toHaveLength(2);
});

test("incoming demo event resets old filters, appears first, and updates the unread badge", () => {
  render(<App />);
  fireEvent.change(screen.getByLabelText("День оповещений"), {
    target: { value: "2026-10-16" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Показать новое событие" }),
  );
  expect(screen.getByLabelText("День оповещений")).toHaveValue("2026-10-17");
  expect(shownEvents()).toHaveLength(5);
  expect(shownEvents()[0]).toHaveAccessibleName(/14:00, новое/);
  expect(screen.getByLabelText("Новых оповещений: 4")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Новое демо-событие добавлено",
  );
});

test("repeated delivery of an event preserves read state and does not duplicate it", () => {
  const store = useNotificationStore.getState();
  const original = store.alerts[0];
  store.markRead([original.id]);
  store.receiveAlert({
    ...original,
    event: { ...original.event, description: "Уточнённое описание" },
  });
  const alerts = useNotificationStore.getState().alerts;
  expect(alerts).toHaveLength(5);
  expect(
    alerts.find((alert) => alert.id === original.id)?.readAt,
  ).toBeDefined();
  expect(alerts[0].event.description).toBe("Уточнённое описание");
});

test("an actual received event uses its own evidence state and never a demo image", () => {
  const original = useNotificationStore.getState().alerts[0];
  useNotificationStore.setState({
    alerts: [
      {
        ...original,
        id: "real-1",
        mode: "api",
        event: { ...original.event, evidence_frames: [] },
      },
    ],
    connection: "connected",
  });
  render(<App />);
  fireEvent.click(shownEvents()[0]);
  const dialog = screen.getByRole("dialog", { name: "Событие с камеры" });
  expect(
    within(dialog).getByText("Кадры события пока не переданы"),
  ).toBeInTheDocument();
  expect(within(dialog).queryByRole("img")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Показать новое событие" }),
  ).not.toBeInTheDocument();
});

test("the notification day uses Astana time across the UTC day boundary", () => {
  expect(localDay("2026-10-17T20:15:00Z")).toBe("2026-10-18");
});

test("connecting a real feed removes fixtures and disconnection retains received events", () => {
  const store = useNotificationStore.getState();
  const real = { ...store.alerts[0], id: "real-2", mode: "api" as const };
  store.setConnection("connected");
  expect(useNotificationStore.getState().alerts).toEqual([]);
  expect(useNotificationStore.getState().cameras).toEqual([]);
  store.receiveAlert(real);
  store.setConnection("disconnected");
  expect(useNotificationStore.getState().alerts).toEqual([real]);
});
