/**
 * useToast — simple in-module singleton toast queue.
 * No external dependencies — uses useSyncExternalStore for React integration.
 *
 * Usage:
 *   const { toasts, showSuccess, showError, dismiss } = useToast();
 *   showSuccess('Отсеки сохранены');
 *   showError('Ошибка: ...');
 */

import { useSyncExternalStore, useCallback } from 'react';

export type ToastType = 'success' | 'error';

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

// Singleton store

let _toasts: Toast[] = [];
const _listeners = new Set<() => void>();
let _nextId = 1;

function getSnapshot(): Toast[] {
  return _toasts;
}

function subscribe(listener: () => void): () => void {
  _listeners.add(listener);
  return () => { _listeners.delete(listener); };
}

function notify(): void {
  _listeners.forEach((l) => l());
}

function addToast(type: ToastType, message: string, durationMs = 4000): string {
  const id = String(_nextId++);
  _toasts = [..._toasts, { id, type, message }];
  notify();
  if (durationMs > 0) {
    setTimeout(() => dismissToast(id), durationMs);
  }
  return id;
}

function dismissToast(id: string): void {
  _toasts = _toasts.filter((t) => t.id !== id);
  notify();
}

// Public API (usable outside React too)

export const toastApi = {
  success: (message: string, durationMs?: number) => addToast('success', message, durationMs),
  error: (message: string, durationMs?: number) => addToast('error', message, durationMs),
  dismiss: dismissToast,
};

// React hook

export function useToast() {
  const toasts = useSyncExternalStore(subscribe, getSnapshot);

  const showSuccess = useCallback((message: string, durationMs?: number) => {
    return addToast('success', message, durationMs);
  }, []);

  const showError = useCallback((message: string, durationMs?: number) => {
    return addToast('error', message, durationMs);
  }, []);

  const dismiss = useCallback((id: string) => {
    dismissToast(id);
  }, []);

  return { toasts, showSuccess, showError, dismiss };
}
