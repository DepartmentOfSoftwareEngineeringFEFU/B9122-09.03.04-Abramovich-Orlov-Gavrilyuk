import React from 'react';
import styles from './ZoomControls.module.css';

interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
}

export const ZoomControls: React.FC<ZoomControlsProps> = ({ onZoomIn, onZoomOut }) => (
  <div className={styles.root}>
    <button
      type="button"
      className={styles.btn}
      onClick={onZoomIn}
      aria-label="Приблизить"
      title="Приблизить"
    >
      +
    </button>
    <button
      type="button"
      className={styles.btn}
      onClick={onZoomOut}
      aria-label="Отдалить"
      title="Отдалить"
    >
      −
    </button>
  </div>
);

export default ZoomControls;
