import React from 'react';
import type { LayerData } from '../../types/stitching';
import styles from './LayerPanel.module.css';

interface LayerPanelProps {
  layers: LayerData[];
  selectedLayerId: string | null;
  onLayerSelect: (layerId: string) => void;
  onLayerMove: (layerId: string, direction: 'up' | 'down') => void;
  onMaskOpacityChange: (layerId: string, opacity: number) => void;
  onShowMaskToggle: (layerId: string) => void;
}

export const LayerPanel: React.FC<LayerPanelProps> = ({
  layers,
  selectedLayerId,
  onLayerSelect,
  onLayerMove,
  onMaskOpacityChange,
  onShowMaskToggle,
}) => {
  return (
    <div className={styles.layerPanel}>
      <div className={styles.sectionHeader}>// СЛОИ</div>
      <div className={styles.layerList}>
        {layers.map((layer, index) => {
          const isActive = selectedLayerId === layer.reconstructionId;
          const opacity = Math.round((layer.maskOpacity || 1) * 100);

          return (
            <div
              key={layer.reconstructionId}
              className={`${styles.layerCard} ${isActive ? styles.active : ''}`}
              onClick={() => onLayerSelect(layer.reconstructionId)}
            >
              <div className={styles.layerCardHeader}>
                <div className={styles.layerCardLeft}>
                  <div className={styles.layerColor} style={{ backgroundColor: layer.color }} />
                  <div className={styles.layerInfo}>
                    <div className={styles.layerName}>{layer.name}</div>
                  </div>
                </div>
                <div className={styles.layerControls}>
                  <button
                    onClick={(e) => { e.stopPropagation(); onLayerMove(layer.reconstructionId, 'up'); }}
                    disabled={index === 0}
                    title="Переместить вверх"
                  >
                    ↑
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onLayerMove(layer.reconstructionId, 'down'); }}
                    disabled={index === layers.length - 1}
                    title="Переместить вниз"
                  >
                    ↓
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onShowMaskToggle(layer.reconstructionId); }}
                    title="Показать/скрыть"
                    style={{ marginLeft: '8px' }}
                  >
                    👁
                  </button>
                </div>
              </div>

              <div className={styles.layerMaskControls}>
                <div className={styles.opacityLabel}>
                  <span>Непрозрачность</span>
                  <span className={styles.opacityValue}>{opacity}%</span>
                </div>
                <div className={styles.sliderContainer}>
                  <div
                    className={styles.sliderTrack}
                    style={{ width: `${opacity}%`, background: layer.color }}
                  />
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={opacity}
                    onChange={(e) => {
                      e.stopPropagation();
                      onMaskOpacityChange(layer.reconstructionId, parseInt(e.target.value) / 100);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      position: 'absolute',
                      width: '100%',
                      height: '100%',
                      opacity: 0,
                      cursor: 'pointer',
                      margin: 0,
                      padding: 0,
                      top: 0,
                      left: 0,
                    }}
                  />
                  <div
                    className={styles.sliderThumb}
                    style={{ left: `${opacity}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
