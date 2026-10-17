/** Synthetic artwork for the UI demo. Never exported as model evidence. */
export function DemoScene({ event = 0 }: { event?: number }) {
  return (
    <div className="demo-scene">
      <img
        src="/images/demo-cash-desk.jpg"
        width="1672"
        height="940"
        alt="Синтетическая иллюстрация кассового рабочего места. Не кадр из видео."
      />
      <span className="demo-scene-label">
        Демо {String(event + 1).padStart(2, "0")} · Синтетическая иллюстрация
      </span>
    </div>
  );
}
