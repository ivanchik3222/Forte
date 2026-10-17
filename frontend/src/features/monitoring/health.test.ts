import { createDemoHealth } from "../../data/demoMonitoring";
import { demoCameras } from "../../data/demoNotifications";
import { useNotificationStore } from "../../store/useNotificationStore";
import {
  cameraHealth,
  HealthIncident,
  HealthSignal,
  incidentWindow,
  unavailableMinutes,
} from "./health";

const now = Date.parse("2026-10-17T10:00:00+05:00");
const iso = (time: string) => `2026-10-17T${time}:00+05:00`;
const incident = (
  id: string,
  start: string,
  end: string,
  cameraId = "camera-01",
): HealthIncident => ({
  id,
  cameraId,
  kind: "offline",
  mode: "api",
  startedAt: iso(start),
  endedAt: iso(end),
});
beforeEach(() => {
  jest.useFakeTimers().setSystemTime(now);
  useNotificationStore.setState({
    connection: "demo",
    cameras: demoCameras,
    ...createDemoHealth(),
  });
});
afterEach(() => jest.useRealTimers());

test("unavailable time unions overlaps per camera and excludes degraded visibility", () => {
  const intervals = [
    incident("1", "08:00", "08:20"),
    incident("2", "08:10", "08:30"),
    incident("3", "08:00", "08:10", "camera-02"),
    { ...incident("4", "09:00", "09:30"), kind: "poor_visibility" as const },
  ];
  expect(unavailableMinutes(intervals, "2026-10-17", now)).toBe(40);
});

test("intervals are clipped to the selected day and now, including ongoing incidents", () => {
  const interval: HealthIncident = {
    ...incident("1", "00:00", "00:10"),
    startedAt: "2026-10-16T23:50:00+05:00",
  };
  expect(unavailableMinutes([interval], "2026-10-17", now)).toBe(10);
  expect(
    unavailableMinutes(
      [{ ...interval, startedAt: iso("09:50"), endedAt: undefined }],
      "2026-10-17",
      now,
    ),
  ).toBe(10);
  expect(
    incidentWindow(
      { ...interval, startedAt: iso("11:00"), endedAt: undefined },
      "2026-10-17",
      now,
    ),
  ).toBeUndefined();
});

test("API health requires fresh telemetry, not only an online camera flag", () => {
  const camera = { ...demoCameras[0], mode: "api" as const };
  const signal: HealthSignal = {
    cameraId: camera.id,
    mode: "api",
    status: "observing",
    checkedAt: new Date(now).toISOString(),
  };
  expect(cameraHealth(camera, undefined, "connected", now)).toBe("unknown");
  expect(cameraHealth(camera, signal, "connected", now)).toBe("observing");
  expect(cameraHealth(camera, signal, "connected", now + 90_001)).toBe(
    "unknown",
  );
  expect(cameraHealth(camera, signal, "disconnected", now)).toBe("unknown");
  expect(
    cameraHealth(
      camera,
      { ...signal, checkedAt: new Date(now + 1000).toISOString() },
      "connected",
      now,
    ),
  ).toBe("unknown");
  expect(
    cameraHealth(camera, { ...signal, mode: "demo" }, "connected", now),
  ).toBe("unknown");
});

test("older health signals cannot overwrite newer ones; resolved incidents do not reopen", () => {
  const feed = useNotificationStore.getState();
  feed.receiveHealthSignal({
    cameraId: "api-1",
    mode: "api",
    status: "observing",
    checkedAt: iso("09:59"),
  });
  feed.receiveHealthSignal({
    cameraId: "api-1",
    mode: "api",
    status: "offline",
    checkedAt: iso("09:58"),
  });
  expect(useNotificationStore.getState().healthSignals["api-1"].status).toBe(
    "observing",
  );
  feed.receiveHealthIncident(incident("real-1", "08:00", "08:20"));
  feed.receiveHealthIncident({
    ...incident("real-1", "08:00", "08:20"),
    endedAt: undefined,
  });
  expect(
    useNotificationStore
      .getState()
      .healthIncidents.filter((i) => i.id === "real-1"),
  ).toHaveLength(1);
  expect(
    useNotificationStore
      .getState()
      .healthIncidents.find((i) => i.id === "real-1")?.endedAt,
  ).toBe(iso("08:20"));
  const length = useNotificationStore.getState().healthIncidents.length;
  feed.receiveHealthIncident(incident("bad", "09:00", "08:00"));
  expect(useNotificationStore.getState().healthIncidents).toHaveLength(length);
});

test("demo failure and recovery update status and close the interval", () => {
  useNotificationStore.getState().simulateCameraIssue("camera-01", "occluded");
  let state = useNotificationStore.getState();
  expect(state.healthSignals["camera-01"].status).toBe("occluded");
  expect(
    state.healthIncidents.filter(
      (i) => i.cameraId === "camera-01" && !i.endedAt,
    ),
  ).toHaveLength(1);
  jest.advanceTimersByTime(120_000);
  state.restoreDemoCamera("camera-01");
  state = useNotificationStore.getState();
  expect(state.healthSignals["camera-01"].status).toBe("observing");
  expect(
    state.healthIncidents.filter(
      (i) => i.cameraId === "camera-01" && !i.endedAt,
    ),
  ).toHaveLength(0);
  expect(state.healthIncidents[0].endedAt).toBe(
    new Date(now + 120_000).toISOString(),
  );
});

test("live connection removes demo health and disables demo mutations", () => {
  useNotificationStore.getState().setConnection("connected");
  useNotificationStore.getState().simulateCameraIssue("camera-01", "offline");
  useNotificationStore.getState().restoreDemoCamera("camera-01");
  expect(useNotificationStore.getState().healthIncidents).toEqual([]);
  expect(useNotificationStore.getState().healthSignals).toEqual({});
});
