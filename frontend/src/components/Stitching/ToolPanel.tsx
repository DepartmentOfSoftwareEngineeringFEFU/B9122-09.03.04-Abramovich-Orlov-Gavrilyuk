import React from 'react';
import styles from './ToolPanel.module.css';

interface ToolPanelProps {
  activeTool: "move" | "rotate" | "rect_crop" | "polygon_clip";
  onToolChange: (tool: "move" | "rotate" | "rect_crop" | "polygon_clip") => void;
}

export const ToolPanel: React.FC<ToolPanelProps> = ({ activeTool, onToolChange }) => {
  const tools = [
    { id: "move", label: "Перемещение", icon: "↔" },
    { id: "rotate", label: "Вращение", icon: "↻" },
    { id: "rect_crop", label: "Кадрирование", icon: "▭" },
    { id: "polygon_clip", label: "Полигон. обрезка", icon: "⬡" },
  ] as const;

  return (
    <div className={styles.toolPanel}>
      <div className={styles.sectionHeader}>// ИНСТРУМЕНТЫ</div>
      <div className={styles.toolButtons}>
        {tools.map((tool) => (
          <button
            key={tool.id}
            className={`${styles.toolButton} ${activeTool === tool.id ? styles.active : ''}`}
            onClick={() => onToolChange(tool.id)}
          >
            <span className={styles.toolIcon}>{tool.icon}</span>
            <span className={styles.toolLabel}>{tool.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
};
