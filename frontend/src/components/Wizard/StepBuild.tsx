import React from 'react';
import { Button } from '../UI/Button';
import styles from './StepBuild.module.css';
import buildingBlur from '../../assets/building-blur.png';

interface StepBuildProps {
  onBuild: () => Promise<void>;
  isBuilding: boolean;
  error: string | null;
}

export const StepBuild: React.FC<StepBuildProps> = ({ onBuild, isBuilding, error }) => {
  return (
    <div className={styles.step} style={{ backgroundImage: `url(${buildingBlur})` }}>
      <div className={styles.content}>
        {error && <p className={styles.error}>{error}</p>}
        <Button variant="primary" onClick={onBuild} disabled={isBuilding}>
          {isBuilding ? 'Построение...' : 'Построить'}
        </Button>
      </div>
    </div>
  );
};
