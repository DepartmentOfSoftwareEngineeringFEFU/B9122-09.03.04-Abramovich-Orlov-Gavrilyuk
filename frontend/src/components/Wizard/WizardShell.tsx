import React from 'react';
import { X } from 'lucide-react';
import { StepIndicator } from './StepIndicator';
import styles from './WizardShell.module.css';

interface WizardShellProps {
  currentStep: number;
  totalSteps: number;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
  hideFooter?: boolean;
  hideHeader?: boolean;
  children: React.ReactNode;
}

export const WizardShell: React.FC<WizardShellProps> = ({
  currentStep,
  totalSteps,
  onNext,
  onPrev,
  onClose,
  nextDisabled = false,
  nextLabel,
  hideFooter = false,
  hideHeader = false,
  children,
}) => {
  const resolvedNextLabel = nextLabel ?? (currentStep === totalSteps ? 'Сохранить' : '> Далее');

  return (
    <div className={styles.shell}>
      {!hideHeader && (
        <header className={styles.header}>
          <StepIndicator totalSteps={totalSteps} currentStep={currentStep} />
          <button type="button" className={styles.closeBtn} onClick={onClose} title="Закрыть">
            <X size={20} />
          </button>
        </header>
      )}

      <div className={styles.content}>{children}</div>

      {!hideFooter && (
        <footer className={styles.footer}>
          <button type="button" className={styles.btnBack} onClick={onPrev}>
            Назад
          </button>
          <button type="button" className={styles.btnNext} onClick={onNext} disabled={nextDisabled}>
            {resolvedNextLabel}
          </button>
        </footer>
      )}
    </div>
  );
};
