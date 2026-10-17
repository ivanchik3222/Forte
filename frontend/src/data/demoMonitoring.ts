import {
  HealthIncident,
  HealthSignal,
  dayBounds,
} from "../features/monitoring/health";
import { localDay } from "../features/notifications/types";
import { demoCameras } from "./demoNotifications";

export function createDemoHealth(now = Date.now()) {
  const elapsed = now - dayBounds(localDay(now)).start;
  const ago = (minutes: number) =>
    new Date(
      now - Math.min(minutes * 60_000, (elapsed * minutes) / 180),
    ).toISOString();
  const healthIncidents: HealthIncident[] = [
    {
      id: "health-demo-1",
      cameraId: "camera-01",
      mode: "demo",
      kind: "offline",
      startedAt: ago(120),
      endedAt: ago(106),
    },
    {
      id: "health-demo-2",
      cameraId: "camera-02",
      mode: "demo",
      kind: "occluded",
      startedAt: ago(80),
      endedAt: ago(73),
    },
    {
      id: "health-demo-3",
      cameraId: "camera-01",
      mode: "demo",
      kind: "frozen",
      startedAt: ago(45),
      endedAt: ago(41),
    },
    {
      id: "health-demo-4",
      cameraId: "camera-03",
      mode: "demo",
      kind: "poor_visibility",
      startedAt: ago(12),
    },
  ];
  const healthSignals: Record<string, HealthSignal> = Object.fromEntries(
    demoCameras.map((camera) => [
      camera.id,
      {
        cameraId: camera.id,
        mode: "demo",
        checkedAt: new Date(now).toISOString(),
        status: camera.id === "camera-03" ? "poor_visibility" : "observing",
      },
    ]),
  );
  return { healthSignals, healthIncidents };
}
