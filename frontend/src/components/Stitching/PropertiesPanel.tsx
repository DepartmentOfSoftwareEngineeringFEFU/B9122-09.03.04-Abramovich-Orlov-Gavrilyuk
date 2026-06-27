import React from 'react';
import type { LayerData } from '../../types/stitching';
import styles from './PropertiesPanel.module.css';

interface PropertiesPanelProps {
  selectedLayer: LayerData | null;
  onPropertyChange: (property: string, value: number) => void;
}

export const PropertiesPanel: React.FC<PropertiesPanelProps> = ({
  selectedLayer,
  onPropertyChange,
}) => {
  if (!selectedLayer) {
    return (
      <div className={styles.propertiesPanel}>
        <div className={styles.sectionHeader}>// СВОЙСТВА СЛОЯ</div>
        <div className={styles.noSelection}>Выберите слой</div>
      </div>
    );
  }

  return (
    <div className={styles.propertiesPanel}>
      <div className={styles.sectionHeader}>// СВОЙСТВА СЛОЯ</div>
      <div className={styles.propertyControls}>
        <div className={styles.propertyRow}>
          <label>X</label>
          <input
            type="number"
            value={Math.round(selectedLayer.transform.translate_x)}
            onChange={(e) => onPropertyChange('translate_x', parseFloat(e.target.value))}
          />
        </div>
        <div className={styles.propertyRow}>
          <label>Y</label>
          <input
            type="number"
            value={Math.round(selectedLayer.transform.translate_y)}
            onChange={(e) => onPropertyChange('translate_y', parseFloat(e.target.value))}
          />
        </div>
        <div className={styles.propertyRow}>
          <label>Угол</label>
          <input
            type="range"
            min="0"
            max="360"
            value={selectedLayer.transform.rotation_deg}
            onChange={(e) => onPropertyChange('rotation_deg', parseFloat(e.target.value))}
          />
          <span className={styles.propertyValue}>{Math.round(selectedLayer.transform.rotation_deg)}°</span>
        </div>
        <div className={styles.propertyRow}>
          <label>Масштаб</label>
          <input
            type="range"
            min="50"
            max="200"
            value={selectedLayer.transform.scale_x * 100}
            onChange={(e) => onPropertyChange('scale_x', parseFloat(e.target.value) / 100)}
          />
          <span className={styles.propertyValue}>{Math.round(selectedLayer.transform.scale_x * 100)}%</span>
        </div>
      </div>
    </div>
  );
};
