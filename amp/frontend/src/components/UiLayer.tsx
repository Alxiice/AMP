import { useEffect, useState } from "react";
import { closeDialog, useUi, type DialogRequest } from "../ui";

function Dialog({ req }: { req: DialogRequest }) {
  const [value, setValue] = useState(req.initial ?? "");
  const isInput = req.initial !== null;
  const canConfirm = !isInput || value.trim().length > 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDialog(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) closeDialog(null); }}>
      <form
        className="dialog"
        role="dialog"
        aria-label={req.title}
        onSubmit={(e) => {
          e.preventDefault();
          if (canConfirm) closeDialog(isInput ? value.trim() : "ok");
        }}
      >
        <h3>{req.title}</h3>
        {isInput && (
          <input
            className="search-input"
            autoFocus
            maxLength={120}
            placeholder="Name"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        <div className="btn-row">
          <button type="submit" className={`btn${req.danger ? " btn-danger" : ""}`} disabled={!canConfirm} autoFocus={!isInput}>
            {req.confirmLabel}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => closeDialog(null)}>Cancel</button>
        </div>
      </form>
    </div>
  );
}

export function UiLayer() {
  const { toasts, dialog } = useUi();
  return (
    <>
      {dialog && <Dialog key={dialog.title} req={dialog} />}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast${t.error ? " error" : ""}`}>{t.text}</div>
        ))}
      </div>
    </>
  );
}
