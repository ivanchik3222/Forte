import { LoadingMark } from "../components/LoadingState";
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiBaseUrl } from '../api/client';
import './ApiAccessPage.css';

export function ApiAccessPage() {
  const [key, setKey] = useState('');
  const [expires, setExpires] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function issue() {
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/api-keys`, { method: 'POST', credentials: 'omit' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Не удалось создать ключ.');
      setKey(data.api_key); setExpires(data.expires_at);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Сервис недоступен.'); }
    finally { setBusy(false); }
  }
  async function revoke() {
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/api-keys/current`, {
        method: 'DELETE', credentials: 'omit', headers: { 'X-API-Key': key },
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error?.message || 'Не удалось отозвать ключ.');
      }
      setKey(''); setExpires(''); setMessage('Ключ отозван. Доступ к его задачам закрыт.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Сервис недоступен.'); }
    finally { setBusy(false); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(key); setMessage('Ключ скопирован.'); }
    catch { setMessage('Выделите ключ и скопируйте вручную.'); }
  }
  return <main className="api-access-page">
    <Link to="/" className="api-back">← Forte Control</Link>
    <header><span className="eyebrow">ДЛЯ ИНТЕГРАЦИЙ</span>
      <h1>API без регистрации</h1>
      <p>Загрузите видео из своего приложения и получите результат по идентификатору задачи.</p>
    </header>
    <section className="api-access-card" aria-labelledby="key-heading">
      <h2 id="key-heading">Ваш API-ключ</h2>
      <p>Ключ действует 30 дней и открывает только ваши задачи. Сохраните его: после закрытия страницы восстановить ключ нельзя. Новый ключ не открывает прежние загрузки.</p>
      {!key ? <button className="button button-primary" onClick={issue} disabled={busy}>{busy && <LoadingMark small />}{busy ? 'Создаём…' : 'Создать API-ключ'}</button> : <>
        <label htmlFor="api-key-value">Сохраните ключ в безопасном месте</label>
        <input id="api-key-value" className="api-key-value" readOnly value={key} autoComplete="off" spellCheck={false} />
        <p>Действует до {new Date(expires).toLocaleString('ru-RU')}.</p>
        <div className="api-key-actions">
          <button className="button button-primary" onClick={copy}>Копировать ключ</button>
          <button className="button" onClick={revoke} disabled={busy}>{busy && <LoadingMark small />}Отозвать ключ</button>
        </div>
      </>}
      <p role="status" aria-live="polite">{message}</p>
    </section>
    <section className="api-access-card" aria-labelledby="usage-heading">
      <h2 id="usage-heading">Два шага для обработки видео</h2>
      <p>Передавайте ключ в заголовке <code>X-API-Key</code> при каждом запросе. В примерах замените <code>YOUR_API_KEY</code> на сохранённый ключ.</p>
      <h3>1. Загрузите видео</h3>
      <pre><code>{`curl -X POST "${apiBaseUrl}/api/v1/analyze" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  -F "file=@video.mov"`}</code></pre>
      <p>Ответ: <code>{'{"job_id":"…","status":"processing"}'}</code>. Поддерживаются MOV, MP4 и WebM до 1 ГиБ.</p>
      <h3>2. Получите результат</h3>
      <pre><code>{`curl "${apiBaseUrl}/api/v1/jobs/JOB_ID" \\\n  -H "X-API-Key: YOUR_API_KEY"`}</code></pre>
      <p>Проверяйте статус раз в 3–5 секунд до <code>done</code> или <code>failed</code>. Готовый ответ содержит вердикт, события и JPEG-кадры в base64.</p>
      <p>Одна активная задача на ключ. При ответе 429 повторите запрос позже; частота выдачи ключей и загрузок ограничена.</p>
      <p className="api-notice">Сейчас API использует R3D: при обнаружении признаков возможного нарушения возвращает <code>status=done</code>, <code>verdict=violation</code> и <code>classification_status=unclassified</code>. Qwen пока не подключён, поэтому проверка правил не выполняется: <code>rule_evaluation=not_performed</code>, <code>coverage_status=partial</code>, <code>rule=null</code>. Если положительного сигнала нет, анализ завершается <code>status=failed</code>; результат <code>no_violation</code> без проверки правил не формируется. Выделенные эпизоды требуют проверки специалистом.</p>
      <h3>Отзыв сохранённого ключа</h3>
      <pre><code>{`curl -X DELETE "${apiBaseUrl}/api/v1/api-keys/current" \\\n  -H "X-API-Key: YOUR_API_KEY"`}</code></pre>
    </section>
  </main>;
}
