import React from 'react';
import styles from './CanvasControls.module.css';

interface CanvasControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onRotate?: () => void;
  showRotate?: boolean;
}

export const CanvasControls: React.FC<CanvasControlsProps> = ({
  onZoomIn,
  onZoomOut,
  onReset,
  onRotate,
  showRotate = false,
}) => {
  return (
    <div className={styles.controls}>
      <button className={styles.btn} onClick={onZoomIn} title="Увеличить" type="button">
        +
      </button>
      <button className={styles.btn} onClick={onZoomOut} title="Уменьшить" type="button">
        −
      </button>
      <button className={styles.btn} onClick={onReset} title="Сбросить вид" type="button">
        ⤢
      </button>
      {showRotate && onRotate && (
        <button className={styles.btn} onClick={onRotate} title="Повернуть 90°" type="button">
          ↻
        </button>
      )}
    </div>
  );
};
