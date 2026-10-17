import { create } from "zustand";
import { createDemoRecords, demoViolations } from "../data/demo";
import { abortableDelay } from "../features/analysis/api";
import {
  AnalysisRecord,
  ConnectionSettings,
  validateVideo,
  Verdict,
} from "../features/analysis/types";

const controllers = new Map<string, AbortController>();
let sequence = 0;

interface AnalysisState {
  records: AnalysisRecord[];
  settings: ConnectionSettings;
  setSettings: (settings: ConnectionSettings) => void;
  start: (file?: File, demoVerdict?: Verdict) => string;
  cancel: (id: string) => void;
  retry: (id: string) => string;
  setDuration: (id: string, duration: number) => void;
}

export const useAnalysisStore = create<AnalysisState>((set, get) => {
  const update = (id: string, patch: Partial<AnalysisRecord>) =>
    set((state) => ({
      records: state.records.map((record) =>
        record.id === id ? { ...record, ...patch } : record,
      ),
    }));
  return {
    records: createDemoRecords(),
    settings: { mode: "api", apiKey: "" },
    setSettings: (settings) => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
      get().records.forEach((record) => {
        if (record.videoUrl?.startsWith("blob:"))
          URL.revokeObjectURL(record.videoUrl);
      });
      set({
        settings,
        records: settings.mode === "demo" ? createDemoRecords() : [],
      });
    },
    setDuration: (id, duration) => {
      if (Number.isFinite(duration) && duration > 0) update(id, { duration });
    },
    start: (file, demoVerdict = "violation") => {
      const { settings } = get();
      if (file) {
        const error = validateVideo(file);
        if (error) throw new Error(error);
      }
      if (settings.mode === "api")
        throw new Error("Загрузите файл через рабочий кабинет.");
      const mode = "demo" as const;
      const id = `check-${Date.now()}-${++sequence}`;
      const controller = new AbortController();
      controllers.set(id, controller);
      const record: AnalysisRecord = {
        id,
        fileName: file?.name || "demo_cash_desk.mov",
        fileSize: file?.size || 29.4 * 1024 * 1024,
        createdAt: new Date().toISOString(),
        mode,
        status: "processing",
        duration: file ? undefined : 82,
        violations: [],
        file,
        videoUrl: file ? URL.createObjectURL(file) : undefined,
      };
      set((state) => ({ records: [record, ...state.records] }));
      void (async () => {
        try {
          if (mode === "demo") {
            const stages = [
              "Подготовка демонстрации",
              "Пример поиска событий",
              "Пример сопоставления с правилами",
              "Подготовка результата",
            ];
            for (let i = 0; i < stages.length; i++) {
              update(id, { progress: 10 + i * 25, stage: stages[i] });
              await abortableDelay(850, controller.signal);
            }
            update(id, {
              status: "done",
              progress: 100,
              verdict: demoVerdict,
              violations: demoVerdict === "violation" ? demoViolations : [],
            });
          }
        } catch (error) {
          if (!controller.signal.aborted)
            update(id, {
              status: "failed",
              error:
                error instanceof Error
                  ? error.message
                  : "Не удалось выполнить проверку.",
            });
        } finally {
          controllers.delete(id);
        }
      })();
      return id;
    },
    cancel: (id) => {
      controllers.get(id)?.abort();
      update(id, { status: "cancelled", stage: undefined });
    },
    retry: (id) => {
      const record = get().records.find((item) => item.id === id);
      if (!record) throw new Error("Проверка не найдена.");
      return get().start(record.file, record.verdict);
    },
  };
});
