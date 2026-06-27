import React, { useEffect, useRef, useState } from 'react';
import styles from './SectionContextMenu.module.css';
import { SECTION_COLOR_PALETTE, getSectionColor, setSectionColor } from './sectionColors';

interface SectionContextMenuProps {
  x: number;
  y: number;
  sectionNumber: number;
  /** Numeric DB id of the section — used to persist color in localStorage */
  sectionId?: number;
  /** Palette index used as deterministic fallback (position in list) */
  sectionIdx: number;
  onRename: () => void;
  onDelete: () => void;
  /** Called after color is changed so parent can re-render */
  onColorChange: () => void;
  onClose: () => void;
}

export const SectionContextMenu: React.FC<SectionContextMenuProps> = ({
  x,
  y,
  sectionNumber,
  sectionId,
  sectionIdx,
  onRename,
  onDelete,
  onColorChange,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const [showColorPicker, setShowColorPicker] = useState(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  // Auto-flip to avoid viewport overflow
  const menuStyle: React.CSSProperties = { left: x, top: y };
  if (x + 200 > window.innerWidth) menuStyle.left = x - 200;
  if (y + 160 > window.innerHeight) menuStyle.top = y - 160;

  const handlePickColor = (color: string) => {
    if (sectionId !== undefined && sectionId > 0) {
      setSectionColor(sectionId, color);
    } else {
      // No saved id yet — store by fallback index key so it survives re-render
      setSectionColor(-(sectionIdx + 1), color);
    }
    onColorChange();
    onClose();
  };

  const currentColor = getSectionColor(sectionIdx, sectionId);

  return (
    <div
      ref={menuRef}
      className={styles.menu}
      style={menuStyle}
      role="menu"
      aria-label={`Меню отсека ${sectionNumber}`}
    >
      <button
        className={styles.item}
        onClick={() => { onRename(); onClose(); }}
        type="button"
        role="menuitem"
      >
        <span className={styles.icon}>✏</span>
        Изменить номер
      </button>

      <button
        className={styles.item}
        onClick={() => setShowColorPicker((v) => !v)}
        type="button"
        role="menuitem"
      >
        <span className={styles.icon} style={{ fontSize: '0.875rem' }}>🎨</span>
        Изменить цвет
      </button>

      {showColorPicker && (
        <div className={styles.colorPicker}>
          {SECTION_COLOR_PALETTE.map((color) => (
            <button
              key={color}
              className={`${styles.colorSwatch} ${color === currentColor ? styles.colorSwatchActive : ''}`}
              style={{ background: color }}
              onClick={() => handlePickColor(color)}
              type="button"
              title={color}
              aria-label={`Цвет ${color}`}
            />
          ))}
        </div>
      )}

      <button
        className={`${styles.item} ${styles.itemDanger}`}
        onClick={() => { onDelete(); onClose(); }}
        type="button"
        role="menuitem"
      >
        <span className={styles.icon}>🗑</span>
        Удалить отсек
      </button>
    </div>
  );
};
