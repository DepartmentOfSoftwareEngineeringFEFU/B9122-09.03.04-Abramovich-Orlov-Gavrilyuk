import React from 'react';
import { Link } from 'react-router-dom';
import type { ReconstructionFloor, ReconstructionSectionBrief } from '../../types/hierarchy';
import styles from './SectionBindingBadge.module.css';

interface SectionBindingBadgeProps {
  floor: ReconstructionFloor | null;
  section: ReconstructionSectionBrief | null;
}

export const SectionBindingBadge: React.FC<SectionBindingBadgeProps> = ({ floor, section }) => {
  if (!floor) {
    return (
      <div className={styles.badge}>
        <p className={styles.label}>Привязка к этажу</p>
        <p className={styles.statusNoFloor}>План без привязки к этажу</p>
      </div>
    );
  }

  const floorHref = `/admin/floor-editor?floor=${floor.id}`;

  if (section) {
    return (
      <div className={styles.badge}>
        <p className={styles.label}>Привязка к отсеку</p>
        <p className={styles.statusBound}>
          Привязан к отсеку №{section.number} (Корпус {floor.building.code}, этаж {floor.number})
        </p>
        <Link to={floorHref} className={styles.actionBtn}>
          Сменить
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.badge}>
      <p className={styles.label}>Привязка к отсеку</p>
      <p className={styles.statusUnbound}>
        Не привязан к отсеку. Этаж: Корпус {floor.building.code}, этаж {floor.number}
      </p>
      <Link to={floorHref} className={styles.actionBtn}>
        Привязать
      </Link>
    </div>
  );
};
