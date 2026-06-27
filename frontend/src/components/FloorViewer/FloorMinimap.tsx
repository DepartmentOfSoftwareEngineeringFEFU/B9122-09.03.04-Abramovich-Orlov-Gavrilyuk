import React from 'react';
import type { SectionPublic } from '../../hooks/useFloorViewer';
import styles from './FloorMinimap.module.css';

interface FloorMinimapProps {
  sections: SectionPublic[];
  /** Normalized [0,1] wall polygons of the floor, drawn under sections as backdrop */
  wallPolygons?: [number, number][][] | null;
  activeSectionId: number | null;
  highlightedSectionIds: number[];
  onSelectSection: (id: number) => void;
}

/** Compute centroid of a polygon's points */
function centroid(points: [number, number][]): { x: number; y: number } {
  const n = points.length;
  if (n === 0) return { x: 0.5, y: 0.5 };
  const sum = points.reduce(
    (acc, [px, py]) => ({ x: acc.x + px, y: acc.y + py }),
    { x: 0, y: 0 },
  );
  return { x: sum.x / n, y: sum.y / n };
}

/** Convert points array to SVG polygon points string */
function toSvgPoints(points: [number, number][]): string {
  return points.map(([px, py]) => `${px},${py}`).join(' ');
}


export const FloorMinimap: React.FC<FloorMinimapProps> = ({
  sections,
  wallPolygons,
  activeSectionId,
  highlightedSectionIds,
  onSelectSection,
}) => {
  if (sections.length === 0) {
    return (
      <div className={styles.minimapWrapper}>
        <div className={styles.empty}>Нет отсеков</div>
      </div>
    );
  }

  return (
    <div className={styles.minimapWrapper}>
      <svg
        className={styles.svg}
        viewBox="0 0 1 1"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Floor walls as a backdrop (under sections) */}
        {wallPolygons && wallPolygons.length > 0 && (
          <g className={styles.wallsLayer}>
            {wallPolygons.map((poly, idx) => (
              <polygon
                key={`wall-${idx}`}
                className={styles.wallPolygon}
                points={toSvgPoints(poly as [number, number][])}
              />
            ))}
          </g>
        )}
        {sections.map((section) => {
          const points = section.geometry.points as [number, number][];
          const c = centroid(points);
          const isActive = section.id === activeSectionId;
          const isHighlighted = !isActive && highlightedSectionIds.includes(section.id);

          let polygonClass = styles.sectionPolygon;
          if (isActive) polygonClass = `${styles.sectionPolygon} ${styles.sectionActive}`;
          else if (isHighlighted) polygonClass = `${styles.sectionPolygon} ${styles.sectionHighlighted}`;

          return (
            <g key={section.id} onClick={() => onSelectSection(section.id)}>
              <polygon
                className={polygonClass}
                points={toSvgPoints(points)}
              />
              <text
                className={`${styles.sectionLabel} ${isActive ? styles.sectionLabelActive : ''}`}
                x={c.x}
                y={c.y}
              >
                {section.number}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
