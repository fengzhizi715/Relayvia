import type { ReactNode } from "react";

type ModalProps = {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
};

export function Modal({ title, eyebrow = "CONFIGURATION", onClose, children }: ModalProps) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-modal="true" className="modal" role="dialog" aria-label={title}>
        <header className="modal-header">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h3>{title}</h3>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close">
            ×
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

