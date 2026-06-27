import React, { useState, useEffect } from 'react';
import type { PublicBuilding } from '../../types/hierarchy';
import type { FloorPublic, SectionPublic } from '../../hooks/useFloorViewer';
import styles from './BuildingFloorSectionSelector.module.css';

// Window size — how many items are shown at once
const WINDOW_SIZE = 3;

interface CarouselRowProps {
  label: string;
  items: Array<{ id: number; label: string }>;
  activeId: number | null;
  onSelect: (id: number) => void;
}

const CarouselRow: React.FC<CarouselRowProps> = ({ label, items, activeId, onSelect }) => {
  const [windowStart, setWindowStart] = useState(0);

  // Recenter window when activeId changes
  useEffect(() => {
    const activeIndex = items.findIndex((item) => item.id === activeId);
    if (activeIndex < 0) {
      setWindowStart(0);
      return;
    }
    // If active item is outside current window, recenter
    if (activeIndex < windowStart || activeIndex >= windowStart + WINDOW_SIZE) {
      const newStart = Math.max(0, Math.min(activeIndex, items.length - WINDOW_SIZE));
      setWindowStart(newStart);
    }
  }, [activeId, items, windowStart]);

  const canScrollLeft = windowStart > 0;
  const canScrollRight = windowStart + WINDOW_SIZE < items.length;
  const visibleItems = items.slice(windowStart, windowStart + WINDOW_SIZE);

  const handlePrev = () => {
    setWindowStart((s) => Math.max(0, s - 1));
  };

  const handleNext = () => {
    setWindowStart((s) => Math.min(s + 1, Math.max(0, items.length - WINDOW_SIZE)));
  };

  return (
    <div className={styles.row}>
      <span className={styles.label}>{label}</span>
      <div className={styles.carousel}>
        <button
          type="button"
          className={styles.arrowBtn}
          onClick={handlePrev}
          disabled={!canScrollLeft}
          aria-label="Назад"
        >
          {'<'}
        </button>
        <div className={styles.items}>
          {visibleItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`${styles.item} ${item.id === activeId ? styles.itemActive : ''}`}
              onClick={() => onSelect(item.id)}
              title={item.label}
            >
              {item.label}
            </button>
          ))}
          {/* Disabled placeholder pills so the row always shows WINDOW_SIZE slots */}
          {visibleItems.length < WINDOW_SIZE &&
            Array.from({ length: WINDOW_SIZE - visibleItems.length }).map((_, i) => (
              <div
                key={`empty-${i}`}
                className={`${styles.item} ${styles.itemPlaceholder}`}
                aria-hidden="true"
              >
                —
              </div>
            ))}
        </div>
        <button
          type="button"
          className={styles.arrowBtn}
          onClick={handleNext}
          disabled={!canScrollRight}
          aria-label="Вперёд"
        >
          {'>'}
        </button>
      </div>
    </div>
  );
};

interface BuildingFloorSectionSelectorProps {
  buildings: PublicBuilding[];
  visibleFloors: FloorPublic[];
  visibleSections: SectionPublic[];
  selectedBuildingId: number | null;
  selectedFloorId: number | null;
  selectedSectionId: number | null;
  onSelectBuilding: (id: number) => void;
  onSelectFloor: (id: number) => void;
  onSelectSection: (id: number) => void;
}

export const BuildingFloorSectionSelector: React.FC<BuildingFloorSectionSelectorProps> = ({
  buildings,
  visibleFloors,
  visibleSections,
  selectedBuildingId,
  selectedFloorId,
  selectedSectionId,
  onSelectBuilding,
  onSelectFloor,
  onSelectSection,
}) => {
  const buildingItems = buildings.map((b) => ({ id: b.id, label: b.code }));
  const floorItems = visibleFloors.map((f) => ({ id: f.id, label: String(f.number) }));
  const sectionItems = visibleSections.map((s) => ({ id: s.id, label: String(s.number) }));

  return (
    <div className={styles.selector}>
      <CarouselRow
        label="Корпус"
        items={buildingItems}
        activeId={selectedBuildingId}
        onSelect={onSelectBuilding}
      />
      <CarouselRow
        label="Этаж"
        items={floorItems}
        activeId={selectedFloorId}
        onSelect={onSelectFloor}
      />
      <CarouselRow
        label="Отсек"
        items={sectionItems}
        activeId={selectedSectionId}
        onSelect={onSelectSection}
      />
    </div>
  );
};
