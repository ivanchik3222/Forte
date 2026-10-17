import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { createDemoAlerts, demoCameras } from "../../data/demoNotifications";
import { createDemoHealth } from "../../data/demoMonitoring";
import { useNotificationStore } from "../../store/useNotificationStore";
import { ShiftPage } from "../../pages/ShiftPage";
import { EpisodePlayer } from "./EpisodePlayer";
import { clipBounds, safeMediaUrl, shiftEpisodes } from "./model";

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
});
afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
});
const renderShift = () =>
  render(
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ShiftPage />
    </MemoryRouter>,
  );
const currentEpisode = () =>
  within(screen.getByRole("region", { name: "Эпизоды смены" }))
    .getAllByRole("button")
    .find((button) => button.getAttribute("aria-current") === "step");

test("playlist takes six latest matching events and plays them chronologically", () => {
  const alert = createDemoAlerts()[0];
  const alerts = Array.from({ length: 9 }, (_, i) => ({
    ...alert,
    id: String(i),
    detectedAt: `2026-10-17T10:0${i}:00+05:00`,
  }));
  expect(
    shiftEpisodes(alerts.reverse(), "2026-10-17").map((a) => a.id),
  ).toEqual(["3", "4", "5", "6", "7", "8"]);
  expect(shiftEpisodes(alerts, "2026-10-16")).toEqual([]);
  expect(shiftEpisodes(alerts, "2026-10-17", "missing-camera")).toEqual([]);
});

test("clips clamp to source bounds; unsafe media URLs and invalid offsets are rejected", () => {
  expect(clipBounds(1, 8)).toEqual({ start: 0, end: 8 });
  expect(clipBounds(98, 100)).toEqual({ start: 95, end: 100 });
  expect(clipBounds(100, 100)).toBeUndefined();
  expect(clipBounds(-1, 100)).toBeUndefined();
  expect(clipBounds(NaN, 100)).toBeUndefined();
  expect(safeMediaUrl("javascript:alert(1)")).toBeUndefined();
  expect(safeMediaUrl("//external.test/a.mp4")).toBeUndefined();
  expect(
    safeMediaUrl("https://user:secret@external.test/a.mp4"),
  ).toBeUndefined();
  expect(safeMediaUrl("/recordings/a.mp4")).toBe("/recordings/a.mp4");
});

test("demo playlist advances, pauses, finishes, and restarts without changing read state", () => {
  renderShift();
  const readBefore = useNotificationStore
    .getState()
    .alerts.map((a) => a.readAt);
  fireEvent.click(screen.getByRole("button", { name: "Смотреть подборку" }));
  act(() => jest.advanceTimersByTime(10_000));
  expect(currentEpisode()).toHaveTextContent("02");
  fireEvent.click(screen.getByRole("button", { name: "Пауза" }));
  act(() => jest.advanceTimersByTime(20_000));
  expect(currentEpisode()).toHaveTextContent("02");
  fireEvent.click(screen.getByRole("button", { name: "Смотреть подборку" }));
  for (let i = 0; i < 3; i++) act(() => jest.advanceTimersByTime(10_000));
  expect(screen.getByText("Все эпизоды показаны")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Смотреть ещё раз" }));
  expect(currentEpisode()).toHaveTextContent("01");
  expect(useNotificationStore.getState().alerts.map((a) => a.readAt)).toEqual(
    readBefore,
  );
});

test("opening context pauses review and changing filters resets the playlist", () => {
  renderShift();
  fireEvent.click(screen.getByRole("button", { name: "Смотреть подборку" }));
  fireEvent.click(screen.getByRole("button", { name: "Что было до и после" }));
  expect(
    screen.getByRole("dialog", { name: "До и после события" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Видеоконтекст не передан/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Закрыть окно" }));
  act(() => jest.advanceTimersByTime(250));
  act(() => jest.advanceTimersByTime(10_000));
  expect(currentEpisode()).toHaveTextContent("01");
  fireEvent.click(screen.getByRole("button", { name: "Смотреть подборку" }));
  fireEvent.change(screen.getByLabelText("Камера обзора смены"), {
    target: { value: "camera-03" },
  });
  expect(
    screen.getByRole("button", { name: "Смотреть подборку" }),
  ).toBeInTheDocument();
  act(() => jest.advanceTimersByTime(20_000));
  expect(currentEpisode()).toHaveTextContent("Касса 03");
});

test("timeline picks nearest event and still allows incremental keyboard values", () => {
  renderShift();
  const slider = screen.getByRole("slider", {
    name: "Выбрать время на шкале смены",
  });
  fireEvent.change(slider, { target: { value: "0" } });
  expect(currentEpisode()).toHaveTextContent("01");
  fireEvent.change(slider, { target: { value: "1" } });
  expect(slider).toHaveValue("1");
  fireEvent.change(slider, { target: { value: "1439" } });
  expect(currentEpisode()).toHaveTextContent("04");
});

test("real event without video or frames never shows a synthetic image", () => {
  const alert = { ...createDemoAlerts()[0], mode: "api" as const };
  render(
    <EpisodePlayer
      alert={alert}
      playing={false}
      onPause={jest.fn()}
      onFinish={jest.fn()}
    />,
  );
  expect(screen.getByText("Кадры не переданы")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText(/Видео не передано/)).toBeInTheDocument();
});

test("real playback seeks to context start and advances once at clip end", () => {
  const alert = {
    ...createDemoAlerts()[0],
    mode: "api" as const,
    recording: { url: "/camera.mp4", durationSec: 100 },
  };
  const finish = jest.fn();
  render(
    <EpisodePlayer
      alert={alert}
      playing
      onPause={jest.fn()}
      onFinish={finish}
    />,
  );
  const video = screen.getByLabelText(
    "Фрагмент записи события",
  ) as HTMLVideoElement;
  Object.defineProperty(video, "duration", { configurable: true, value: 100 });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(15);
  expect(video.play).toHaveBeenCalled();
  video.currentTime = 25;
  fireEvent.timeUpdate(video);
  fireEvent.ended(video);
  expect(finish).toHaveBeenCalledTimes(1);
});

test("video metadata with an invalid event offset falls back to explicit missing media state", () => {
  const alert = {
    ...createDemoAlerts()[0],
    mode: "api" as const,
    recording: { url: "/camera.mp4", durationSec: 100 },
  };
  render(
    <EpisodePlayer
      alert={alert}
      playing={false}
      onPause={jest.fn()}
      onFinish={jest.fn()}
    />,
  );
  const video = screen.getByLabelText("Фрагмент записи события");
  Object.defineProperty(video, "duration", { configurable: true, value: 5 });
  fireEvent.loadedMetadata(video);
  expect(screen.getByText(/таймкод вне записи/)).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
