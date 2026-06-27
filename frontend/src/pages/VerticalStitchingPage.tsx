import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Boxes, Layers, X, ArrowRight } from 'lucide-react';
import { useBuildings } from '../hooks/useBuildings';
import type { Building } from '../types/hierarchy';
import styles from './VerticalStitchingPage.module.css';

// Building picker landing for "Вертикальное сшивание" (subfeature A). Lists the
// buildings and opens the existing per-building editor
// (/admin/buildings/:id/assembly → BuildingAssemblyPage), where the user aligns
// adjacent floors over one another. Buildings with < 2 floors can't be stitched
// (no pair to align) and are shown disabled with a hint.

const getPluralFloors = (count: number): string => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod100 >= 11 && mod100 <= 19) return `${count} этажей`;
  if (mod10 === 1) return `${count} этаж`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} этажа`;
  return `${count} этажей`;
};

export const VerticalStitchingPage: React.FC = () => {
  const navigate = useNavigate();
  const { buildings, isLoading, error } = useBuildings();

  const openEditor = (building: Building): void => {
    navigate(`/admin/buildings/${building.id}/assembly`);
  };

  return (
    <div className={styles.page}>
      <div className={styles.darkHeader}>
        <span className={styles.darkHeaderLabel}>Вертикальное сшивание</span>
        <button
          className={styles.darkHeaderClose}
          type="button"
          onClick={() => navigate('/admin')}
          title="Закрыть"
        >
          <X size={20} />
        </button>
      </div>

      <div className={styles.content}>
        <div className={styles.inner}>
          <header className={styles.pageHeader}>
            <h1 className={styles.title}>Вертикальное сшивание</h1>
            <p className={styles.subtitle}>
              Выберите корпус, чтобы соединить его этажи по вертикали — выровнять
              их друг над другом по общим опорным точкам. Нужно минимум два этажа.
            </p>
          </header>

          {isLoading && <div className={styles.stateMsg}>Загрузка корпусов…</div>}

          {!isLoading && error && (
            <div className={`${styles.stateMsg} ${styles.stateError}`}>{error}</div>
          )}

          {!isLoading && !error && buildings.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>
                <Building2 size={64} strokeWidth={1} />
              </div>
              <h3 className={styles.emptyTitle}>Нет корпусов</h3>
              <p className={styles.emptyText}>
                Сначала создайте корпус и добавьте в него хотя бы два этажа на
                странице «Корпуса и этажи».
              </p>
              <button
                className={styles.btnPrimary}
                type="button"
                onClick={() => navigate('/admin/buildings')}
              >
                Перейти к корпусам
              </button>
            </div>
          )}

          {!isLoading && !error && buildings.length > 0 && (
            <div className={styles.list}>
              {buildings.map((building) => {
                const ready = building.floors_count >= 2;
                return (
                  <button
                    key={building.id}
                    type="button"
                    className={`${styles.card} ${ready ? '' : styles.cardDisabled}`}
                    onClick={() => { if (ready) openEditor(building); }}
                    disabled={!ready}
                    title={
                      ready
                        ? 'Открыть редактор вертикального сшивания'
                        : 'Для сшивания нужно минимум два этажа'
                    }
                  >
                    <div className={styles.cardIcon}>
                      <Boxes size={22} />
                    </div>
                    <div className={styles.cardMain}>
                      <div className={styles.cardName}>{building.name}</div>
                      <div className={styles.cardCode}>Код: {building.code}</div>
                    </div>
                    <div className={styles.cardMeta}>
                      <span className={styles.floorsBadge}>
                        <Layers size={14} /> {getPluralFloors(building.floors_count)}
                      </span>
                      {ready ? (
                        <span className={styles.openHint}>
                          Открыть <ArrowRight size={16} />
                        </span>
                      ) : (
                        <span className={styles.needHint}>нужно ≥ 2 этажей</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VerticalStitchingPage;
