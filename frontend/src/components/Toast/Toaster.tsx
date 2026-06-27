/**
 * Toaster — renders queued toasts at the bottom of the screen.
 * Place <Toaster /> once at the root of any page that needs toasts.
 */
import React from 'react';
import { useToast } from '../../hooks/useToast';
import styles from './Toaster.module.css';

export const Toaster: React.FC = () => {
  const { toasts, dismiss } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className={styles.container} aria-live="polite" aria-label="Уведомления">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`${styles.toast} ${toast.type === 'success' ? styles.toastSuccess : styles.toastError}`}
          role="alert"
        >
          <span className={styles.icon}>
            {toast.type === 'success' ? (
              // Green check icon
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <circle cx="9" cy="9" r="9" fill="#22c55e" />
                <path
                  d="M5 9l3 3 5-6"
                  stroke="#fff"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              // Red X icon
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <circle cx="9" cy="9" r="9" fill="#ef4444" />
                <path
                  d="M6 6l6 6M12 6l-6 6"
                  stroke="#fff"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            )}
          </span>
          <span className={styles.message}>{toast.message}</span>
          <button
            className={styles.closeBtn}
            onClick={() => dismiss(toast.id)}
            type="button"
            aria-label="Закрыть уведомление"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path
                d="M2 2l10 10M12 2L2 12"
                stroke="#9ca3af"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
};
