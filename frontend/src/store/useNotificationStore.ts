import { create } from "zustand";
import { createDemoAlerts, demoCameras } from "../data/demoNotifications";
import { demoViolations } from "../data/demo";
import { CameraAlert, MonitoredCamera } from "../features/notifications/types";

interface NotificationState {
  alerts: CameraAlert[];
  cameras: MonitoredCamera[];
  connection: "demo" | "connected" | "disconnected";
  receiveAlert: (alert: CameraAlert) => void;
  markRead: (ids: string[]) => void;
  addDemoAlert: () => void;
  setCameras: (cameras: MonitoredCamera[]) => void;
  setConnection: (connection: NotificationState["connection"]) => void;
}

let demoSequence = 0;

export const useNotificationStore = create<NotificationState>((set, get) => ({
  alerts: createDemoAlerts(),
  cameras: demoCameras,
  connection: "demo",
  receiveAlert: (incoming) => {
    if (
      !incoming.id ||
      !incoming.cameraId ||
      !Number.isFinite(Date.parse(incoming.detectedAt))
    )
      return;
    set((state) => {
      const existing = state.alerts.find((alert) => alert.id === incoming.id);
      const alert = {
        ...incoming,
        readAt: existing?.readAt || incoming.readAt,
      };
      return {
        alerts: [
          alert,
          ...state.alerts.filter((item) => item.id !== alert.id),
        ].sort((a, b) => Date.parse(b.detectedAt) - Date.parse(a.detectedAt)),
      };
    });
  },
  markRead: (ids) => {
    const selected = new Set(ids);
    const readAt = new Date().toISOString();
    set((state) => ({
      alerts: state.alerts.map((alert) =>
        selected.has(alert.id) && !alert.readAt ? { ...alert, readAt } : alert,
      ),
    }));
  },
  addDemoAlert: () => {
    const index = demoSequence++;
    const camera = demoCameras[index % demoCameras.length];
    get().receiveAlert({
      id: `camera-demo-incoming-${Date.now()}-${index}`,
      cameraId: camera.id,
      cameraName: camera.name,
      location: camera.location,
      detectedAt: new Date().toISOString(),
      mode: "demo",
      event: demoViolations[index % demoViolations.length],
    });
  },
  setCameras: (cameras) => set({ cameras }),
  setConnection: (connection) =>
    set((state) => ({
      connection,
      ...(state.connection === "demo" && connection !== "demo"
        ? {
            alerts: state.alerts.filter((alert) => alert.mode !== "demo"),
            cameras: state.cameras.filter((camera) => camera.mode !== "demo"),
          }
        : {}),
    })),
}));
