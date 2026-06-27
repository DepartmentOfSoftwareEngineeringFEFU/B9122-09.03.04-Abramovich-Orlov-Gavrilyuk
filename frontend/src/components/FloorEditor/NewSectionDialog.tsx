/**
 * NewSectionDialog — RIGHT SIDE PANEL (not a modal overlay).
 * Light theme, takes real layout space, no backdrop.
 *
 * Includes:
 *  - Номер отсека (required, duplicate-validated)
 * Описание (optional, client-only — not sent to backend)
 *  - Цвет отсека (palette of 7 colors, presentation-only via localStorage)
 */
import React, { useState, useEffect, useRef } from 'react';
import styles from './NewSectionDialog.module.css';
import { SECTION_COLOR_PALETTE } from './sectionColors';

interface NewSectionDialogProps {
  open: boolean;
  initialNumber: number | null;
  initialColor?: string;
  takenNumbers: number[];
  onConfirm: (number: number, color: string) => void;
  onCancel: () => void;
}

export const NewSectionDialog: React.FC<NewSectionDialogProps> = ({
  open,
  initialNumber,
  initialColor,
  takenNumbers,
  onConfirm,
  onCancel,
}) => {
  const [value, setValue] = useState<string>(String(initialNumber ?? 1));
  const [color, setColor] = useState<string>(initialColor ?? SECTION_COLOR_PALETTE[0]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setValue(String(initialNumber ?? 1));
      setColor(initialColor ?? SECTION_COLOR_PALETTE[0]);
      setTimeout(() => inputRef.current?.select(), 50);
    }
  }, [open, initialNumber, initialColor]);

  if (!open) return null;

  const num = parseInt(value, 10);
  const isValid = !isNaN(num) && num >= 1;
  const isDuplicate = isValid && takenNumbers.includes(num);
  const canConfirm = isValid && !isDuplicate;

  const handleConfirm = () => {
    if (canConfirm) onConfirm(num, color);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && canConfirm) handleConfirm();
    if (e.key === 'Escape') onCancel();
  };

  return (
    <div className={styles.overlay}>
      <aside className={styles.panel} role="dialog" aria-label="Новый отсек">
        <div className={styles.panelHeader}>
        <h3 className={styles.title}>Новый отсек</h3>
        <button
          className={styles.closeBtn}
          onClick={onCancel}
          type="button"
          aria-label="Закрыть"
        >
          ✕
        </button>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="section-number-input">
          Номер отсека <span className={styles.required}>*</span>
        </label>
        <input
          id="section-number-input"
          ref={inputRef}
          className={`${styles.input} ${isDuplicate ? styles.inputError : ''}`}
          type="number"
          min={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        {isDuplicate && (
          <p className={styles.error}>Отсек с номером {num} уже существует</p>
        )}
      </div>

      <div className={styles.field}>
        <span className={styles.label}>Цвет отсека</span>
        <div className={styles.colorRow}>
          {SECTION_COLOR_PALETTE.map((c) => (
            <button
              key={c}
              type="button"
              className={`${styles.colorSwatch} ${c === color ? styles.colorSwatchActive : ''}`}
              style={{ backgroundColor: c }}
              onClick={() => setColor(c)}
              aria-label={`Цвет ${c}`}
              aria-pressed={c === color}
            />
          ))}
        </div>
      </div>

      <div className={styles.actions}>
        <button className={styles.btnCancel} onClick={onCancel} type="button">
          Отмена
        </button>
        <button
          className={styles.btnConfirm}
          onClick={handleConfirm}
          disabled={!canConfirm}
          type="button"
        >
          Применить
        </button>
      </div>
    </aside>
    </div>
  );
};
