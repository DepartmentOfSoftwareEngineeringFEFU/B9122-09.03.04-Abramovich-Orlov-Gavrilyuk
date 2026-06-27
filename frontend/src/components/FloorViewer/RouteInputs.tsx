import React from 'react';
import styles from './RouteInputs.module.css';

interface RouteInputsProps {
  start: string;
  end: string;
  onStartChange: (v: string) => void;
  onEndChange: (v: string) => void;
  onSwap: () => void;
  onSubmit: () => void;
  disabled?: boolean;
  error?: string | null;
}

export const RouteInputs: React.FC<RouteInputsProps> = ({
  start,
  end,
  onStartChange,
  onEndChange,
  onSwap,
  onSubmit,
  disabled = false,
  error = null,
}) => {
  const submitDisabled = disabled || !start || !end;

  return (
    <div className={styles.root}>
      <div className={styles.row}>
        <div className={styles.inputs}>
          <input
            type="text"
            className={styles.input}
            placeholder="Начальная точка"
            value={start}
            onChange={(e) => onStartChange(e.target.value)}
          />
          <input
            type="text"
            className={styles.input}
            placeholder="Конечная точка"
            value={end}
            onChange={(e) => onEndChange(e.target.value)}
          />
        </div>
        <button
          type="button"
          className={styles.swap}
          onClick={onSwap}
          aria-label="Поменять начало и конец местами"
        >
          ⇄
        </button>
      </div>
      <div className={styles.helper}>Пример: D304</div>
      <button
        type="button"
        className={styles.submit}
        onClick={onSubmit}
        disabled={submitDisabled}
      >
        Построить маршрут
      </button>
      {error && <div className={styles.error}>{error}</div>}
    </div>
  );
};

export default RouteInputs;
