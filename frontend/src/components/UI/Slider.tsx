import React from 'react';
import styles from './Slider.module.css';

interface SliderProps {
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  label?: string;
}

export const Slider: React.FC<SliderProps> = ({
  value,
  min,
  max,
  onChange,
  label = 'px',
}) => {
  return (
    <div className={styles.slider}>
      <input
        type="range"
        className={styles.track}
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className={styles.value}>
        {value} {label}
      </span>
    </div>
  );
};
