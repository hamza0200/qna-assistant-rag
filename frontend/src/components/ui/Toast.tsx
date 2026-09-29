"use client";

import { useEffect } from "react";

interface ToastProps {
  message: string | null;
  onDismiss: () => void;
  durationMs?: number;
}

/** Transient error notice, announced to screen readers via role="alert". */
export function Toast({ message, onDismiss, durationMs = 7000 }: ToastProps) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(t);
  }, [message, onDismiss, durationMs]);

  if (!message) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex justify-center px-4">
      <div
        role="alert"
        className="pointer-events-auto flex max-w-md items-start gap-3 rounded-md bg-ink px-4 py-3 text-sm text-white shadow-lg"
      >
        <p>{message}</p>
        <button type="button" onClick={onDismiss} className="shrink-0 text-white/70 hover:text-white">
          Dismiss
        </button>
      </div>
    </div>
  );
}
