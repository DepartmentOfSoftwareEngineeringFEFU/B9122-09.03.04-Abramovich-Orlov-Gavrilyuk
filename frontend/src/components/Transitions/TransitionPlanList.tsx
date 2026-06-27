import React from 'react';
import type { FloorTransition } from '../../types/transitions';
import styles from './TransitionPlanList.module.css';

interface PlanListItem {
  id: number;
  name: string;
}

interface TransitionPlanListProps {
  plans: PlanListItem[];
  transitions: FloorTransition[];
  selectedPlanId: number | null;
  onSelectPlan: (id: number) => void;
}

export const TransitionPlanList: React.FC<TransitionPlanListProps> = ({
  plans,
  transitions,
  selectedPlanId,
  onSelectPlan,
}) => {
  return (
    <div className={styles.sidebar}>
      <div className={styles.sidebarHeader}>
        <span>Планы</span>
        <span className={styles.sidebarCount}>{plans.length}</span>
      </div>
      <div className={styles.list}>
        {plans.length === 0 ? (
          <div className={styles.emptyList}>Нет планов</div>
        ) : (
          plans.map((plan) => {
            const count = transitions.filter(
              (t) => t.from_reconstruction_id === plan.id || t.to_reconstruction_id === plan.id,
            ).length;
            const isActive = plan.id === selectedPlanId;
            return (
              <div
                key={plan.id}
                className={`${styles.row} ${isActive ? styles.rowActive : ''}`}
                onClick={() => onSelectPlan(plan.id)}
              >
                <span className={`${styles.rowName} ${isActive ? styles.rowActiveText : ''}`}>
                  {plan.name}
                </span>
                {count > 0 && <span className={styles.badge}>{count}</span>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
