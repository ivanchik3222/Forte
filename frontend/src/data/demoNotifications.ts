import {
  CameraAlert,
  localDay,
  MonitoredCamera,
} from "../features/notifications/types";
import { demoViolations } from "./demo";

export const demoCameras: MonitoredCamera[] = [
  {
    id: "camera-01",
    name: "Касса 01",
    location: "Астана · Центральное отделение",
    status: "online",
    mode: "demo",
  },
  {
    id: "camera-02",
    name: "Касса 02",
    location: "Астана · Центральное отделение",
    status: "online",
    mode: "demo",
  },
  {
    id: "camera-03",
    name: "Касса 03",
    location: "Алматы · Отделение Достык",
    status: "online",
    mode: "demo",
  },
];

export function createDemoAlerts(): CameraAlert[] {
  const now = Date.now();
  const start = Date.parse(`${localDay(now)}T00:00:00+05:00`);
  return [18, 47, 93, 160, 1440].map((minutes, index) => {
    const camera = demoCameras[index % demoCameras.length];
    // The first four examples always belong to today, including just after midnight.
    const ago =
      index === 4
        ? minutes * 60000
        : Math.min(minutes * 60000, (now - start) * ((index + 1) / 5));
    return {
      id: `camera-demo-${index + 1}`,
      cameraId: camera.id,
      cameraName: camera.name,
      location: camera.location,
      detectedAt: new Date(now - ago).toISOString(),
      mode: "demo",
      event: demoViolations[index % demoViolations.length],
      readAt: index >= 3 ? new Date(now).toISOString() : undefined,
    };
  });
}
