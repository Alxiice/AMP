/** App-wide toasts and name/confirm dialogs. Rendered once by components/UiLayer. */

import { useSyncExternalStore } from "react";

export interface Toast {
  id: number;
  text: string;
  error: boolean;
}

export interface DialogRequest {
  title: string;
  /** Text input with this initial value; null = plain confirmation. */
  initial: string | null;
  confirmLabel: string;
  danger: boolean;
  resolve: (value: string | null) => void;
}

const TOAST_MS = 3500;

let toasts: Toast[] = [];
let dialog: DialogRequest | null = null;
let snapshot: { toasts: Toast[]; dialog: DialogRequest | null } = { toasts, dialog };
let nextId = 1;
const listeners = new Set<() => void>();

function emit(): void {
  snapshot = { toasts, dialog };
  for (const l of listeners) l();
}

export function toast(text: string, error = false): void {
  const id = nextId++;
  toasts = [...toasts, { id, text, error }];
  emit();
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    emit();
  }, TOAST_MS);
}

export function toastError(e: unknown, fallback: string): void {
  toast(e instanceof Error && e.message ? `${fallback}: ${e.message}` : fallback, true);
}

function open(req: Omit<DialogRequest, "resolve">): Promise<string | null> {
  dialog?.resolve(null);
  return new Promise((resolve) => {
    dialog = { ...req, resolve };
    emit();
  });
}

export function closeDialog(value: string | null): void {
  dialog?.resolve(value);
  dialog = null;
  emit();
}

/** Resolves to the trimmed name, or null if cancelled. */
export function askName(title: string, initial = "", confirmLabel = "Save"): Promise<string | null> {
  return open({ title, initial, confirmLabel, danger: false });
}

export async function askConfirm(title: string, confirmLabel: string): Promise<boolean> {
  return (await open({ title, initial: null, confirmLabel, danger: true })) !== null;
}

export function useUi() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => snapshot,
  );
}
