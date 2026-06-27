import React, { useEffect, useRef, useState } from 'react';
import type { TransitionSpec } from '../../types/wizard';
import {
  resolveConfirmPayload,
  validateElevator,
  type PopupRoomType,
} from './roomPopup.helpers';
import styles from './RoomPopup.module.css';

interface RoomPopupProps {
  position: { x: number; y: number };
  roomType: PopupRoomType;
  onConfirm: (name: string, transition?: TransitionSpec) => void;
  onCancel: () => void;
}

export const RoomPopup: React.FC<RoomPopupProps> = ({
  position,
  roomType,
  onConfirm,
  onCancel,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [floorFrom, setFloorFrom] = useState('');
  const [floorTo, setFloorTo] = useState('');
  const [excludedRaw, setExcludedRaw] = useState('');
  // Stair directional gates (multifloor-routing, D) — both ON by default.
  const [connectsUp, setConnectsUp] = useState(true);
  const [connectsDown, setConnectsDown] = useState(true);
  const popupRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-focus first input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Click outside → cancel
  useEffect(() => {
    const handleMouseDown = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        onCancel();
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [onCancel]);

  // Keyboard: Escape → cancel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  const elevator = validateElevator(floorFrom, floorTo, excludedRaw);
  const canConfirm =
    roomType === 'elevator'
      ? elevator.valid
      : roomType === 'room'
        ? inputValue.trim().length > 0
        : true;

  const handleConfirm = () => {
    const payload = resolveConfirmPayload(
      roomType,
      inputValue,
      floorFrom,
      floorTo,
      excludedRaw,
      connectsUp,
      connectsDown,
    );
    if (!payload) return;
    onConfirm(payload.name, payload.transition);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleConfirm();
  };

  return (
    <div
      ref={popupRef}
      className={styles.popup}
      style={{ left: position.x, top: position.y }}
    >
      {roomType === 'room' && (
        <>
          <p className={styles.label}>Номер кабинета</p>
          <input
            ref={inputRef}
            type="text"
            className={styles.input}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="например, 301"
          />
        </>
      )}

      {roomType === 'staircase' && (
        <>
          <p className={styles.note}>Соединяет соседние этажи</p>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={connectsUp}
              onChange={(e) => setConnectsUp(e.target.checked)}
            />
            <span className={styles.rowLabel}>Доступ на верхний этаж</span>
          </label>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={connectsDown}
              onChange={(e) => setConnectsDown(e.target.checked)}
            />
            <span className={styles.rowLabel}>Доступ на нижний этаж</span>
          </label>
        </>
      )}

      {roomType === 'elevator' && (
        <>
          <div className={styles.row}>
            <span className={styles.rowLabel}>Этажи с</span>
            <input
              ref={inputRef}
              type="number"
              min={1}
              step={1}
              className={styles.input}
              value={floorFrom}
              onChange={(e) => setFloorFrom(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <span className={styles.rowLabel}>по</span>
            <input
              type="number"
              min={1}
              step={1}
              className={styles.input}
              value={floorTo}
              onChange={(e) => setFloorTo(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <p className={styles.label}>Исключить этажи</p>
          <input
            type="text"
            className={styles.input}
            value={excludedRaw}
            onChange={(e) => setExcludedRaw(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="например, 5, 7"
          />
          {elevator.hint && <p className={styles.hint}>{elevator.hint}</p>}
        </>
      )}

      <button
        type="button"
        className={styles.confirmBtn}
        onClick={handleConfirm}
        disabled={!canConfirm}
      >
        Подтвердить
      </button>
    </div>
  );
};
