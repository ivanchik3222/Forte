import { AnalysisRecord, Violation } from "../features/analysis/types";

export const regulatorySource = {
  title:
    "Правила осуществления кассовых операций и операций по инкассации банкнот, монет и ценностей",
  shortTitle: "Кассовые операции и инкассация",
  number: "Постановление Правления НБРК № 231",
  date: "29 ноября 2019 года",
  url: "https://adilet.zan.kz/rus/docs/V1900019680",
};

// These are UI fixtures, not model predictions or confirmed legal classifications.
export const demoViolations: Violation[] = [
  {
    type: "Наличные оставлены без наблюдения",
    timecode_sec: 18,
    description:
      "Пример для демонстрации: сотрудник отходит от рабочего места, на столе остаются предметы, похожие на банкноты. Проверяющему необходимо изучить фрагмент и условия доступа к кассе.",
    evidence_frames: [],
    rule: {
      title: regulatorySource.title,
      url: regulatorySource.url,
      explanation:
        "Источник для исследования. Применимый пункт и связь с событием требуют проверки; это не подтверждённая квалификация нарушения.",
    },
  },
  {
    type: "Передача наличных вне рабочей зоны",
    timecode_sec: 44,
    description:
      "Пример для демонстрации: предметы, похожие на банкноты, передаются за пределами выделенной зоны стола. По одному кадру нельзя установить назначение передачи или наличие разрешения.",
    evidence_frames: [],
  },
];

export function createDemoRecords(): AnalysisRecord[] {
  const now = Date.now();
  return [
    {
      id: "demo-001",
      fileName: "cash_desk_01.mov",
      fileSize: 29.4 * 1024 * 1024,
      createdAt: new Date(now - 25 * 60000).toISOString(),
      duration: 82,
      mode: "demo",
      status: "done",
      verdict: "violation",
      violations: demoViolations,
    },
    {
      id: "demo-002",
      fileName: "cash_desk_02.mov",
      fileSize: 24.8 * 1024 * 1024,
      createdAt: new Date(now - 56 * 60000).toISOString(),
      duration: 64,
      mode: "demo",
      status: "done",
      verdict: "no_violation",
      violations: [],
    },
    {
      id: "demo-003",
      fileName: "cash_desk_03.mov",
      fileSize: 31.2 * 1024 * 1024,
      createdAt: new Date(now - 92 * 60000).toISOString(),
      duration: 108,
      mode: "demo",
      status: "done",
      verdict: "violation",
      violations: [demoViolations[0]],
    },
  ];
}
