import { t, useLocale } from "../../i18n";
export function DemoScene({ event = 0 }: { event?: number }) {
  useLocale();
  return (
    <div className="demo-scene">
      <img
        src="/images/demo-cash-desk.jpg"
        width="1672"
        height="940"
        alt={t("Синтетическая иллюстрация кассового рабочего места. Не кадр из видео.")}
      />
      <span className="demo-scene-label">{t("Демо ")}{String(event + 1).padStart(2, "0")}{t(" · Синтетическая иллюстрация")}</span>
    </div>
  );
}
