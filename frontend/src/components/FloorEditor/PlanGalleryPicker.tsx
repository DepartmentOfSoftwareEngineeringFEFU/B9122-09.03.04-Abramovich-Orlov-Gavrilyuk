/**
 * PlanGalleryPicker — shows reconstructions for selection in Step 5.
 *
 * Per mockup: search input + single "Все планы" status-filter dropdown.
 * Building/floor filtering has been removed from the gallery panel since
 * building+floor are now global selectors in the top header.
 * Cards display thumbnail + name like "A11.5 — Этаж 11" + optional tag.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { reconstructionApi, type ReconstructionListItem } from '../../api/apiService';
import type { Building, BuildingDetail } from '../../types/hierarchy';
import styles from './PlanGalleryPicker.module.css';



interface PlanGalleryPickerProps {
  buildings: BuildingDetail[] | Building[];
  selectedReconstructionId: number | null;
  assignedReconstructionIds?: number[];
  onSelect: (id: number) => void;
  /**
   * When provided, the gallery is hard-restricted to reconstructions of this floor.
   * The building/floor filter dropdowns are hidden in this mode, since the picker
   * should only show plans uploaded for the floor whose "Создать карту отсеков"
   * button was pressed.
   */
  restrictToFloorId?: number | null;
}

export const PlanGalleryPicker: React.FC<PlanGalleryPickerProps> = ({
  buildings,
  selectedReconstructionId,
  assignedReconstructionIds = [],
  onSelect,
  restrictToFloorId = null,
}) => {
  const [search, setSearch] = useState('');
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | ''>('');
  const [selectedFloorId, setSelectedFloorId] = useState<number | ''>('');
  const [reconstructions, setReconstructions] = useState<ReconstructionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchRecons = useCallback(async () => {
    setIsLoading(true);
    try {
      const filters: Parameters<typeof reconstructionApi.getReconstructions>[0] = {};
      // status=3 means "Done" / completed reconstructions
      filters.status = 3;
      if (search) filters.search = search;
      // Server-side restriction to the floor the editor was opened for.
      if (restrictToFloorId !== null) filters.floorId = restrictToFloorId;
      const data = await reconstructionApi.getReconstructions(filters);
      setReconstructions(data);
    } catch {
      setReconstructions([]);
    } finally {
      setIsLoading(false);
    }
  }, [search, restrictToFloorId]);

  useEffect(() => {
    void fetchRecons();
  }, [fetchRecons]);

  // Client-side filtering by building and floor
  const selectedBuilding = buildings.find(b => b.id === Number(selectedBuildingId));

  const filtered = reconstructions.filter((r) => {
    if (selectedBuildingId !== '') {
      if (!r.floor || !selectedBuilding || r.floor.building_code !== selectedBuilding.code) return false;
    }
    if (selectedFloorId !== '') {
      if (!r.floor || r.floor.id !== Number(selectedFloorId)) return false;
    }
    return true;
  });

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h2 className={styles.headerTitle}>ПЛАНЫ ЭТОГО ЭТАЖА</h2>
        <input
          className={styles.searchInput}
          type="text"
          placeholder="Поиск..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {restrictToFloorId === null && (
          <div className={styles.filters}>
            <select
              className={styles.filterSelect}
              value={selectedBuildingId}
              onChange={(e) => {
                setSelectedBuildingId(e.target.value === '' ? '' : Number(e.target.value));
                setSelectedFloorId(''); // reset floor
              }}
            >
              <option value="">Все здания</option>
              {buildings.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
            <select
              className={styles.filterSelect}
              value={selectedFloorId}
              disabled={selectedBuildingId === ''}
              onChange={(e) => setSelectedFloorId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">Все этажи</option>
              {((selectedBuilding as BuildingDetail)?.floors || []).map((f: { id: number; number: number }) => (
                <option key={f.id} value={f.id}>Этаж {f.number}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Gallery */}
      {isLoading ? (
        <div className={styles.loading}>Загрузка...</div>
      ) : filtered.length === 0 ? (
        <div className={styles.empty}>Нет планов</div>
      ) : (
        <div className={styles.gridWrap}>
          <div className={styles.grid}>
            {filtered.map((r) => {
              const isSelected = r.id === selectedReconstructionId;
              const isAssignedElsewhere = assignedReconstructionIds.includes(r.id) && !isSelected;
              // Build card label like "A11.5 — Этаж 11"
              const label = r.floor
                ? `${r.floor.building_code} — Этаж ${r.floor.number}`
                : r.name ?? '—';
              return (
                <button
                  key={r.id}
                  className={`${styles.card} ${isSelected ? styles.cardSelected : ''} ${isAssignedElsewhere ? styles.cardAssigned : ''}`}
                  onClick={() => {
                    if (!isAssignedElsewhere) {
                      onSelect(r.id);
                    }
                  }}
                  type="button"
                  disabled={isAssignedElsewhere}
                  title={isAssignedElsewhere ? "Этот план уже назначен другому отсеку" : ""}
                >
                  <div className={styles.cardThumbWrap}>
                    {r.preview_url ? (
                      <img
                        src={r.preview_url}
                        alt={r.name ?? 'Plan'}
                        className={styles.cardThumb}
                      />
                    ) : (
                      <div className={styles.cardThumbEmpty}>🖼</div>
                    )}
                    {isSelected && <div className={styles.cardOverlay} />}
                  </div>
                  <div className={styles.cardInfo}>
                    <span className={styles.cardName}>{r.name ?? label}</span>
                    {r.floor && (
                      <span className={styles.cardFloor}>{label}</span>
                    )}
                  </div>
                  {isSelected && <span className={styles.checkmark}>✓</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
