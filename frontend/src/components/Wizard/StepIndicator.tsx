import React from 'react';
import styles from './StepIndicator.module.css';

interface StepIndicatorProps {
  totalSteps: number;
  currentStep: number;
}

export const StepIndicator: React.FC<StepIndicatorProps> = ({ totalSteps, currentStep }) => {
  return (
    <div className={styles.indicator}>
      {Array.from({ length: totalSteps }, (_, i) => {
        const step = i + 1;
        const isActive = step === currentStep;
        const isPassed = step < currentStep;
        const dotClass = [
          styles.dot,
          isActive ? styles.active : '',
          isPassed ? styles.passed : '',
        ]
          .filter(Boolean)
          .join(' ');
        return <span key={step} className={dotClass} />;
      })}
    </div>
  );
};
