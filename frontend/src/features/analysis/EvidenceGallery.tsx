import { useState } from "react";
import { mediaUrl } from "../../api/client";
import { Icon } from "../../components/Icon";
import { Modal } from "../../components/Modal";
import { LoadingState } from "../../components/LoadingState";
import { t, useLocale } from "../../i18n";
import { evidenceTime, SeekToEvidence } from "./playback";

export interface EvidenceImage { image_url: string; timestamp_sec: number; caption: string }

export function EvidenceGallery({ frames, onSeek }: { frames: EvidenceImage[]; onSeek: SeekToEvidence }) {
  useLocale();
  const [selected, setSelected] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const select = (index: number) => { setReady(false); setFailed(false); setSelected(index); };
  const frame = selected === null ? null : frames[selected];
  return <>
    <div className="ml-evidence-grid">{frames.map((item, index) => <button
      className="ml-evidence-card" key={`${item.timestamp_sec}-${index}`} onClick={() => select(index)}
      aria-label={t("Увеличить кадр {0}: {1}", [evidenceTime(item.timestamp_sec), item.caption])}>
      <span className="evidence-thumbnail"><img src={mediaUrl(item.image_url)} alt="" loading="lazy" referrerPolicy="no-referrer" /><span className="evidence-expand"><Icon name="search" size={16} />{t("Увеличить")}</span></span>
      <span className="evidence-caption"><strong>{evidenceTime(item.timestamp_sec)}</strong><span>{item.caption}</span></span>
    </button>)}</div>
    {frame && selected !== null && <Modal title={t("Кадр {0}", [evidenceTime(frame.timestamp_sec)])} wide onClose={() => setSelected(null)}>
      <div className="evidence-viewer" onKeyDown={event => {
        if (event.key === "ArrowLeft" && selected > 0) { event.preventDefault(); select(selected - 1); }
        if (event.key === "ArrowRight" && selected < frames.length - 1) { event.preventDefault(); select(selected + 1); }
      }}>
        <div className="evidence-viewer-image">
          {!ready && !failed && <LoadingState label="Загружаем кадр…" />}
          {failed ? <p role="alert">{t("Кадр не загрузился. Закройте окно и обновите кадры и ссылки.")}</p> :
            <img key={frame.image_url} src={mediaUrl(frame.image_url)} alt={frame.caption} referrerPolicy="no-referrer"
              onLoad={() => setReady(true)} onError={() => setFailed(true)} />}
        </div>
        <div className="evidence-viewer-toolbar">
          <button className="icon-button" disabled={selected === 0} aria-label={t("Предыдущий кадр")} onClick={() => select(selected - 1)}><Icon name="chevron" style={{ transform: "rotate(180deg)" }} /></button>
          <span>{t("Кадр {0} из {1}", [selected + 1, frames.length])}</span>
          <button className="icon-button" disabled={selected === frames.length - 1} aria-label={t("Следующий кадр")} onClick={() => select(selected + 1)}><Icon name="chevron" /></button>
          <button className="button button-primary" onClick={() => {
            const seconds = frame.timestamp_sec;
            setSelected(null);
            // Wait for dialog cleanup/focus restoration before focusing the player.
            requestAnimationFrame(() => onSeek(seconds));
          }}><Icon name="play" size={17} />{t("Открыть этот момент в видео")}</button>
        </div>
        <p className="evidence-viewer-description">{frame.caption}</p>
      </div>
    </Modal>}
  </>;
}
