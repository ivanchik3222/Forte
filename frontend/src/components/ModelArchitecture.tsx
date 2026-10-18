import { useState } from "react";
import { Link } from "react-router-dom";
import { t, useLocale } from "../i18n";
import { Icon, IconName } from "./Icon";

const patterns: { icon: IconName; title: string; text: string }[] = [
  { icon: "scan", title: "Руки и предметы", text: "Перемещение и передача предметов, появление и исчезновение объектов в рабочей зоне." },
  { icon: "grid", title: "Рабочая поверхность", text: "Последовательность действий в кассовой зоне и её связь с происходящим в полном кадре." },
  { icon: "video", title: "Изменения во времени", text: "Модель рассматривает короткие последовательности кадров, а не только отдельные фотографии." },
  { icon: "eye", title: "Контекст и видимость", text: "Уход из рабочей зоны, действия с дверцами и сумками, перекрытия обзора и неоднозначные предметы." },
];

function StepLabel({ number, title }: { number: string; title: string }) {
  return <div className="pipeline-step-label"><span>{number}</span><strong>{t(title)}</strong></div>;
}

export function ModelArchitecture() {
  useLocale();
  const [detail, setDetail] = useState<"pipeline" | "patterns" | "api">("pipeline");
  return <section className="landing-section landing-container model-section" id="model" aria-labelledby="model-title">
    <div className="landing-section-intro">
      <div><p className="landing-eyebrow">{t("03 / ВНУТРИ ТЕХНОЛОГИИ")}</p><h2 id="model-title">{t("От пикселей")}<br /><span>{t("к проверяемому выводу.")}</span></h2></div>
      <p>{t("Обученный классификатор находит подозрительные эпизоды. Визуально-языковая модель уточняет контекст. Исходные кадры позволяют проверить каждый результат.")}</p>
    </div>
    <div className="model-explorer">
      <div className="model-explorer-toolbar">
        <div className="model-explorer-caption"><Icon name="scan" size={18} /><span>FORTE / MODEL MAP</span></div>
        <div className="model-view-switch" role="group" aria-label={t("Раздел схемы модели")}>
          {([['pipeline', 'Путь видео'], ['patterns', 'Что ищем'], ['api', 'Ответ API']] as const).map(([id, label]) =>
            <button key={id} aria-pressed={detail === id} aria-controls="model-explorer-content" onClick={() => setDetail(id)}>{t(label)}</button>)}
        </div>
      </div>
      <div className="model-explorer-content" id="model-explorer-content" key={detail}>
        {detail === "pipeline" && <>
          <div className="pipeline-intake">
            <div className="pipeline-input-icon"><Icon name="video" size={27} /></div>
            <div><StepLabel number="01" title="Видео становится последовательностью" />
              <p>{t("Проверяем файл и длительность, декодируем кадры и сохраняем их реальные временные метки. Анализируем только изображение, без звука.")}</p>
            </div><span className="pipeline-format">MOV<span>PTS / TIMECODE</span></span>
          </div>
          <div className="pipeline-connector" aria-hidden="true"><Icon name="down" size={19} /></div>
          <div className="pipeline-branches">
            <article className="pipeline-model pipeline-temporal">
              <StepLabel number="02A" title="Находим эпизоды" />
              <h3>R3D-18 <span>+ bank classifier</span></h3>
              <div className="model-views" aria-label={t("Два представления: кассовая зона и полный кадр")}>
                <div className="model-frame"><span className="model-person" /><span className="model-desk" /><span className="model-roi" /><small>{t("Кассовая зона")}</small></div>
                <span className="model-views-plus" aria-hidden="true">+</span>
                <div className="model-frame model-frame-context"><span className="model-person" /><span className="model-desk" /><small>{t("Полный кадр")}</small></div>
              </div>
              <p>{t("Два взгляда на одну сцену: движения в рабочей зоне и общий контекст. Их признаки объединяет классификатор, обученный на банковских видео.")}</p>
              <dl className="model-specs"><div><dt>{t("Короткий клип")}</dt><dd>{t("16 кадров · 4 кадра/с")}</dd></div><div><dt>{t("Шаг анализа")}</dt><dd>{t("1 секунда")}</dd></div><div><dt>{t("Объединение признаков")}</dt><dd>512 + 512 → 1024</dd></div></dl>
              <span className="model-stage-result"><Icon name="clock" size={16} />{t("Интервалы и моменты максимальной оценки")}</span>
            </article>
            <article className="pipeline-model pipeline-context">
              <StepLabel number="02B" title="Проверяем контекст" />
              <h3>Qwen3-VL <span>4B / local VLM</span></h3>
              <div className="model-filmstrip" aria-hidden="true">{Array.from({ length: 8 }, (_, i) => <span key={i}><i /><small>{String(i + 1).padStart(2, "0")}</small></span>)}</div>
              <p>{t("Модель читает последовательность полных кадров, описывает видимые действия и сопоставляет возможные нарушения с условиями и исключениями правил.")}</p>
              <dl className="model-specs"><div><dt>{t("Окно наблюдения")}</dt><dd>{t("12 секунд")}</dd></div><div><dt>{t("Выборка")}</dt><dd>{t("8 кадров на окно")}</dd></div><div><dt>{t("Основание")}</dt><dd>{t("Видимые факты + правила РК")}</dd></div></dl>
              <span className="model-stage-result"><Icon name="book" size={16} />{t("Описание, тип и основание — когда подтверждены")}</span>
            </article>
          </div>
          <div className="pipeline-connector pipeline-connector-merge" aria-hidden="true"><Icon name="down" size={19} /></div>
          <div className="pipeline-result">
            <div><StepLabel number="03" title="Собираем доказательства" /><h3>{t("Сигнал → контекст → исходный кадр")}</h3><p>{t("Объединяем результаты, выбираем 1–3 JPEG-кадра на событие и сверяем таймкоды. Неопределённый тип отмечаем явно; сбой анализа не превращаем в отсутствие нарушений.")}</p></div>
            <div className="pipeline-result-tags"><span><Icon name="checkCircle" size={16} />{t("Вердикт")}</span><span><Icon name="clock" size={16} />{t("Таймкод")}</span><span><Icon name="image" size={16} />{t("Кадры")}</span><span><Icon name="file" size={16} />JSON</span></div>
          </div>
          <details className="model-technical-details"><summary>{t("Технические детали и границы модели")}<Icon name="plus" size={17} /></summary>
            <div><p>{t("R3D-18 извлекает признаки движения. Обученная бинарная голова оценивает эпизоды с фиксированным порогом 0,5. Это оценка модели, а не вероятность доказанного нарушения.")}</p>
              <p>{t("Текущий банковский классификатор рассчитан на исходный ракурс 464 × 848. Для другого ракурса его вывод не используется; полнокадровый VLM-анализ требует отдельной проверки качества.")}</p>
              <p>{t("Обе ветки выполняются последовательно для экономии памяти. Правило принимается только при подтверждении всех видимых условий и проверке исключений. Быстрые действия между выбранными кадрами могут быть пропущены.")}</p></div>
          </details>
        </>}
        {detail === "patterns" && <div className="model-patterns-view">
          <p className="model-detail-lead">{t("Смотрим на действия и их последовательность.")}</p>
          <div className="model-patterns-grid">{patterns.map(p => <article key={p.title}><Icon name={p.icon} size={25} /><h3>{t(p.title)}</h3><p>{t(p.text)}</p></article>)}</div>
          <div className="model-pattern-note"><Icon name="info" size={20} /><p>{t("Эти паттерны помогают описать сцену, но сами по себе не доказывают нарушение. Открытая дверца, передача предмета или уход из кадра требуют контекста и применимого правила.")}</p></div>
        </div>}
        {detail === "api" && <div className="model-api-view">
          <div><p className="landing-eyebrow">{t("ОДИН КОНТРАКТ ДЛЯ ИНТЕГРАЦИИ")}</p><h3>{t("Видео на входе. Структурированный результат на выходе.")}</h3>
            <ol className="model-api-steps"><li><span>01</span><div><code>POST /api/v1/analyze</code><p>{t("Передайте файл и X-API-Key. В ответ получите job_id.")}</p></div></li><li><span>02</span><div><code>GET /api/v1/jobs/&#123;job_id&#125;</code><p>{t("Запрашивайте статус: processing, done или failed.")}</p></div></li><li><span>03</span><div><strong>{t("Проверьте результат")}</strong><p>{t("Вердикт, тип, описание, таймкод и 1–3 исходных кадра в JPEG/base64 для каждого события.")}</p></div></li></ol>
            <Link to="/api-access" className="button button-outline">{t("Открыть документацию API")}<Icon name="arrow" size={17} /></Link>
          </div>
          <div className="model-response-card"><div><Icon name="file" size={18} /><strong>{t("Поля результата")}</strong><span>JSON</span></div>
            <dl>{[['job_id', 'Идентификатор проверки'], ['status', 'Статус обработки'], ['verdict', 'violation / no_violation'], ['violations[]', 'Список событий'], ['type · description', 'Тип и объяснение'], ['timecode_sec', 'Момент в секундах'], ['evidence_frames[]', 'Кадры с временными метками']].map(([field, label]) => <div key={field}><dt><code>{field}</code></dt><dd>{t(label)}</dd></div>)}</dl>
            <p>{t("При отсутствии нарушений список событий пуст. Если анализ завершился с ошибкой, API сообщает о сбое и не выдаёт отсутствие нарушений.")}</p>
          </div>
        </div>}
      </div>
      <p className="model-deployment-note"><Icon name="info" size={16} />{t("Показана полная локальная связка. Её перенос на публичный сервер ещё не завершён; доступные этапы зависят от развёртывания.")}</p>
    </div>
  </section>;
}

const features: { icon: IconName; title: string; text: string }[] = [
  { icon: "history", title: "Записи не теряются", text: "Загруженные видео и история проверок собраны в аккаунте. К результату можно вернуться позже." },
  { icon: "play", title: "Смена за минуту", text: "Выделенные эпизоды помогают просмотреть события смены и перейти к нужному моменту записи." },
  { icon: "eye", title: "Видно, где не видно", text: "Статусы камер и интервалы доступности отделяют отсутствие событий от отсутствия наблюдения." },
  { icon: "bell", title: "Важное — в событиях", text: "Единая лента оповещений, фильтры и отметки просмотра помогают распределить внимание." },
  { icon: "server", title: "Готовый API-контракт", text: "Загрузка видео по ключу, статус задачи и JSON-результат с кадрами для внешней проверки и интеграций." },
  { icon: "user", title: "Понятно на трёх языках", text: "Русский, қазақша и English. Интерфейс переключается без потери открытого раздела и выбранного файла." },
];

export function WorkspaceFeatures() {
  useLocale();
  return <section className="landing-section landing-container workspace-features" id="workspace-features" aria-labelledby="features-title">
    <div className="landing-section-intro"><div><p className="landing-eyebrow">{t("04 / БОЛЬШЕ, ЧЕМ АНАЛИЗ")}</p><h2 id="features-title">{t("Вся проверка.")}<br /><span>{t("В одном пространстве.")}</span></h2></div><p>{t("От первой загрузки до повторного просмотра — инструменты, которые помогают работать с результатом каждый день.")}</p></div>
    <div className="workspace-feature-grid">{features.map((f, i) => <article key={f.title}><div className="workspace-feature-top"><span><Icon name={f.icon} size={23} /></span><small>0{i + 1}</small></div><h3>{t(f.title)}</h3><p>{t(f.text)}</p></article>)}</div>
  </section>;
}
