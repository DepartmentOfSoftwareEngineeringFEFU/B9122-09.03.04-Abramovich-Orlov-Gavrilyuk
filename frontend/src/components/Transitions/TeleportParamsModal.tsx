import React, { useState } from 'react';
import styles from './TeleportParamsModal.module.css';

interface PlanOption {
  id: number;
  name: string;
}

interface TeleportParamsModalProps {
  plans: PlanOption[];
  currentPlanId: number;
  onConfirm: (name: string, toReconstructionId: number) => void;
  onCancel: () => void;
}

export const TeleportParamsModal: React.FC<TeleportParamsModalProps> = ({
  plans,
  currentPlanId,
  onConfirm,
  onCancel,
}) => {
  const [name, setName] = useState('');
  const otherPlans = plans.filter((p) => p.id !== currentPlanId);
  const [targetPlanId, setTargetPlanId] = useState<number>(otherPlans[0]?.id ?? 0);

  const isValid = name.trim().length > 0 && targetPlanId !== 0;

  const handleConfirm = () => {
    if (!isValid) return;
    onConfirm(name.trim(), targetPlanId);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && isValid) handleConfirm();
    if (e.key === 'Escape') onCancel();
  };

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div className={styles.card} onKeyDown={handleKeyDown}>
        <h2 className={styles.cardTitle}>Новый переход</h2>

        <div className={styles.field}>
          <label className={styles.label}>Имя узла</label>
          <input
            className={styles.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Лестница А"
            autoFocus
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Целевой план</label>
          <select
            className={styles.select}
            value={targetPlanId}
            onChange={(e) => setTargetPlanId(Number(e.target.value))}
          >
            {otherPlans.length === 0 && (
              <option value={0}>Нет доступных планов</option>
            )}
            {otherPlans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.actions}>
          <button className={styles.btnCancel} onClick={onCancel}>
            Отмена
          </button>
          <button
            className={styles.btnConfirm}
            onClick={handleConfirm}
            disabled={!isValid}
          >
            Создать
          </button>
        </div>
      </div>
    </div>
  );
};
