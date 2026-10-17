import { create } from "zustand";
import { createDemoAlerts, demoCameras } from "../data/demoNotifications";
import { demoViolations } from "../data/demo";
import { CameraAlert, MonitoredCamera } from "../features/notifications/types";
import { createDemoHealth } from "../data/demoMonitoring";
import {
  HealthIncident,
  HealthIssue,
  HealthSignal,
  issueKinds,
} from "../features/monitoring/health";

interface NotificationState {
  alerts: CameraAlert[];
  cameras: MonitoredCamera[];
  connection: "demo" | "connected" | "disconnected";
  healthSignals: Record<string, HealthSignal>;
  healthIncidents: HealthIncident[];
  receiveHealthSignal: (signal: HealthSignal) => void;
  receiveHealthIncident: (incident: HealthIncident) => void;
  simulateCameraIssue: (cameraId: string, kind: HealthIssue) => void;
  restoreDemoCamera: (cameraId: string) => void;
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
  ...createDemoHealth(),
  receiveHealthSignal: (signal) => {
    if (
      !signal.cameraId ||
      !["observing", ...issueKinds].includes(signal.status) ||
      !Number.isFinite(Date.parse(signal.checkedAt)) ||
      Date.parse(signal.checkedAt) > Date.now()
    )
      return;
    set((state) => {
      const previous = state.healthSignals[signal.cameraId];
      if (
        previous &&
        Date.parse(previous.checkedAt) > Date.parse(signal.checkedAt)
      )
        return state;
      return {
        healthSignals: { ...state.healthSignals, [signal.cameraId]: signal },
      };
    });
  },
  receiveHealthIncident: (incident) => {
    const start = Date.parse(incident.startedAt);
    const end = incident.endedAt ? Date.parse(incident.endedAt) : undefined;
    if (
      !incident.id ||
      !incident.cameraId ||
      !issueKinds.includes(incident.kind) ||
      !Number.isFinite(start) ||
      start > Date.now() ||
      (end !== undefined &&
        (!Number.isFinite(end) || end < start || end > Date.now()))
    )
      return;
    set((state) => {
      const previous = state.healthIncidents.find((i) => i.id === incident.id);
      // Late delivery of an open interval must not reopen an already resolved incident.
      const updated = {
        ...incident,
        endedAt: incident.endedAt || previous?.endedAt,
      };
      return {
        healthIncidents: [
          updated,
          ...state.healthIncidents.filter((i) => i.id !== incident.id),
        ],
      };
    });
  },
  simulateCameraIssue: (cameraId, kind) => {
    const state = get();
    if (
      state.connection !== "demo" ||
      !issueKinds.includes(kind) ||
      !state.cameras.some((c) => c.id === cameraId && c.mode === "demo")
    )
      return;
    state.restoreDemoCamera(cameraId);
    const startedAt = new Date().toISOString();
    get().receiveHealthIncident({
      id: `health-demo-${Date.now()}-${demoSequence++}`,
      cameraId,
      mode: "demo",
      kind,
      startedAt,
    });
    get().receiveHealthSignal({
      cameraId,
      mode: "demo",
      status: kind,
      checkedAt: startedAt,
    });
  },
  restoreDemoCamera: (cameraId) => {
    if (
      get().connection !== "demo" ||
      !get().cameras.some((c) => c.id === cameraId && c.mode === "demo")
    )
      return;
    const now = new Date().toISOString();
    set((state) => ({
      healthIncidents: state.healthIncidents.map((i) =>
        i.cameraId === cameraId && i.mode === "demo" && !i.endedAt
          ? { ...i, endedAt: now }
          : i,
      ),
      healthSignals: {
        ...state.healthSignals,
        [cameraId]: {
          cameraId,
          mode: "demo",
          status: "observing",
          checkedAt: now,
        },
      },
    }));
  },
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
            healthSignals: Object.fromEntries(
              Object.entries(state.healthSignals).filter(
                ([, signal]) => signal.mode !== "demo",
              ),
            ),
            healthIncidents: state.healthIncidents.filter(
              (incident) => incident.mode !== "demo",
            ),
          }
        : {}),
    })),
}));
