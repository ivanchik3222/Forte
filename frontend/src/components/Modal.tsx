import { ReactNode, useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

export function Modal({
  title,
  onClose,
  children,
  wide = false,
  closeLabel,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  closeLabel?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const closingRef = useRef(false);
  const [closing, setClosing] = useState(false);
  const requestClose = () => {
    if (closingRef.current) return;
    closingRef.current = true;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      onClose();
      return;
    }
    setClosing(true);
    closeTimer.current = setTimeout(onClose, 220);
  };
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute("open", "");
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      clearTimeout(closeTimer.current);
      document.body.style.overflow = old;
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "modal-wide" : ""} ${closing ? "modal-closing" : ""}`}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div className="modal-inner">
        <span className="modal-handle" aria-hidden="true" />
        <div className="modal-header">
          <div>
            <span className="modal-eyebrow">FORTE CONTROL</span>
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Закрыть окно"
            onClick={requestClose}
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {closeLabel && (
          <div className="modal-footer">
            <button className="button button-primary" onClick={requestClose}>
              {closeLabel}
              <Icon name="check" size={18} />
            </button>
          </div>
        )}
      </div>
    </dialog>
  );
}
