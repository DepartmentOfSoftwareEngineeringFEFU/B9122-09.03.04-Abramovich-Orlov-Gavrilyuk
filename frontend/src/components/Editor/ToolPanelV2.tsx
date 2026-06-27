import React from 'react';
import styles from './ToolPanelV2.module.css';

export interface ToolButton {
  id: string;
  label: string;
  icon: React.ReactNode;
}

export interface ToolSection {
  title: string;
  tools: ToolButton[];
}

interface ToolPanelV2Props {
  sections: ToolSection[];
  activeTool: string | null;
  onToolChange: (id: string) => void;
  brushSize?: number;
  onBrushSizeChange?: (size: number) => void;
  brushSizeLabel?: string;
  extraContent?: React.ReactNode;
}

export const ToolPanelV2: React.FC<ToolPanelV2Props> = ({
  sections,
  activeTool,
  onToolChange,
  brushSize,
  onBrushSizeChange,
  brushSizeLabel = '// ТОЛЩИНА ЛИНИИ',
  extraContent,
}) => {
  const showSlider = brushSize !== undefined && onBrushSizeChange !== undefined;

  return (
    <div className={styles.panel}>
      <div className={styles.inner}>
        {sections.map((section) => (
          <section key={section.title} className={styles.section}>
            <h4 className={styles.sectionTitle}>{section.title}</h4>
            <div className={styles.buttons}>
              {section.tools.map((tool) => {
                const isActive = activeTool === tool.id;
                return (
                  <button
                    key={tool.id}
                    type="button"
                    className={`${styles.toolBtn} ${isActive ? styles.toolBtnActive : ''}`}
                    onClick={() => onToolChange(tool.id)}
                  >
                    <div className={styles.toolIcon}>{tool.icon}</div>
                    <span className={styles.toolLabel}>{tool.label}</span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}

        {showSlider && (
          <section className={styles.section}>
            <h4 className={styles.sliderLabel}>{brushSizeLabel}</h4>
            <div className={styles.sliderRow}>
              <input
                type="range"
                className={styles.sliderInput}
                min={1}
                max={50}
                value={brushSize}
                onChange={(e) => onBrushSizeChange!(Number(e.target.value))}
              />
              <span className={styles.sliderValue}>{brushSize} px</span>
            </div>
          </section>
        )}

        {extraContent}
      </div>
    </div>
  );
};
