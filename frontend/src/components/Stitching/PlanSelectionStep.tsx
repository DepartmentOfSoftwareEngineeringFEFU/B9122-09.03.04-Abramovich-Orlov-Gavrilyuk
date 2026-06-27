import React, { useState, useEffect } from 'react';
import { Layers, ChevronDown, ImageIcon, Check, AlertTriangle, FileImage, ArrowRight } from 'lucide-react';
import type { ReconstructionListItem } from '../../types/stitching';
import { reconstructionApi } from '../../api/apiService';
import type { ReconstructionListItem as ApiReconstructionListItem } from '../../api/apiService';
import styles from './PlanSelectionStep.module.css';

interface Building {
  id: string;
  name: string;
}

interface PlanSelectionStepProps {
  onNext: (selectedIds: string[], buildingId: string, floorNumber: number) => void;
  onCancel: () => void;
}

export const PlanSelectionStep: React.FC<PlanSelectionStepProps> = ({
  onNext,
}) => {
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<string>('');
  const [floorNumber, setFloorNumber] = useState<number>(1);
  const [reconstructions, setReconstructions] = useState<ReconstructionListItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);

  // Load buildings on mount
  useEffect(() => {
    const loadBuildings = async () => {
      try {
        // Fetch all reconstructions to extract unique building_id values
        const apiResult = await reconstructionApi.getReconstructions();
        // Cast to local stitching type — stitching feature uses its own shape
        const allReconstructions = apiResult.map((r: ApiReconstructionListItem): ReconstructionListItem => ({
          id: r.id,
          name: r.name,
          preview_url: r.preview_url,
          rooms_count: 0,
          walls_count: 0,
          created_at: r.updated_at,
          rotation_angle: 0,
          building_id: r.floor?.building_code ?? null,
          floor_number: r.floor?.number ?? null,
          status: String(r.status),
        }));

        // Extract unique building IDs
        const uniqueBuildings = new Map<string, string>();
        allReconstructions.forEach((r: ReconstructionListItem) => {
          if (r.building_id) {
            uniqueBuildings.set(r.building_id, r.building_id);
          }
        });

        // Convert to building list
        const buildingList = Array.from(uniqueBuildings.entries()).map(([id, name]) => ({
          id,
          name,
        }));

        setBuildings(buildingList);

        // Auto-select first building with ≥2 plans
        if (buildingList.length > 0) {
          for (const building of buildingList) {
            // Check all floors for this building
            const buildingReconstructions = allReconstructions.filter(
              (r: ReconstructionListItem) => r.building_id === building.id
            );

            // Group by floor
            const floorGroups = new Map<number, ReconstructionListItem[]>();
            buildingReconstructions.forEach((r: ReconstructionListItem) => {
              if (r.floor_number !== null && r.floor_number !== undefined) {
                const floor = r.floor_number;
                if (!floorGroups.has(floor)) {
                  floorGroups.set(floor, []);
                }
                floorGroups.get(floor)!.push(r);
              }
            });

            // Find first floor with ≥2 plans
            for (const [floor, plans] of floorGroups.entries()) {
              if (plans.length >= 2) {
                setSelectedBuildingId(building.id);
                setFloorNumber(floor);
                return;
              }
            }
          }
        }
      } catch (error) {
        console.error('Failed to load buildings:', error);
      }
    };

    loadBuildings();
  }, []);

  // Load reconstructions when building/floor changes
  useEffect(() => {
    if (!selectedBuildingId) {
      setReconstructions([]);
      return;
    }

    const loadReconstructions = async () => {
      setIsLoading(true);
      try {
        const apiData = await reconstructionApi.getReconstructions({
          buildingCode: selectedBuildingId || undefined,
        });
        const data = apiData.map((r: ApiReconstructionListItem): ReconstructionListItem => ({
          id: r.id,
          name: r.name,
          preview_url: r.preview_url,
          rooms_count: 0,
          walls_count: 0,
          created_at: r.updated_at,
          rotation_angle: 0,
          building_id: r.floor?.building_code ?? null,
          floor_number: r.floor?.number ?? null,
          status: String(r.status),
        }));

        // Filter by building and floor if available
        const filtered = data.filter((r: ReconstructionListItem) => {
          const matchesBuilding = r.building_id === selectedBuildingId;
          const matchesFloor = r.floor_number === floorNumber;
          return matchesBuilding && matchesFloor;
        });

        setReconstructions(filtered);
      } catch (error) {
        console.error('Failed to load reconstructions:', error);
        setReconstructions([]);
      } finally {
        setIsLoading(false);
      }
    };

    loadReconstructions();
  }, [selectedBuildingId, floorNumber]);

  const handleToggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleNext = () => {
    if (selectedIds.size < 2) return;
    onNext(Array.from(selectedIds), selectedBuildingId, floorNumber);
  };

  const isNextDisabled = selectedIds.size < 2 || !selectedBuildingId;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>Сшивание планов</h1>
          <p className={styles.subtitle}>
            <Layers size={16} className={styles.subtitleIcon} />
            Шаг 1: Выбор обработанных фрагментов этажа
          </p>
        </div>
        <div className={styles.stepIndicator}>
          <div className={styles.stepActive}>01 ВЫБОР</div>
          <div className={styles.stepDivider}>---</div>
          <div className={styles.stepInactive}>02 РЕДАКТОР</div>
        </div>
      </div>

      {/* Filters Panel */}
      <div className={styles.filtersPanel}>
        <div className={styles.filterControl}>
          <div className={styles.filterLabel}>Объект</div>
          <div className={styles.filterInputWrapper}>
            <select
              className={styles.filterSelect}
              value={selectedBuildingId}
              onChange={(e) => {
                setSelectedBuildingId(e.target.value);
                setSelectedIds(new Set());
              }}
            >
              <option value="">Выберите здание</option>
              {buildings.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
            <ChevronDown size={20} className={styles.filterIcon} />
          </div>
        </div>

        <div className={styles.filterControl}>
          <div className={styles.filterLabel}>Этаж</div>
          <div className={styles.filterInputWrapper}>
            <input
              type="number"
              className={styles.filterInput}
              value={floorNumber}
              onChange={(e) => {
                setFloorNumber(parseInt(e.target.value, 10) || 1);
                setSelectedIds(new Set());
              }}
              min={0}
            />
          </div>
        </div>
      </div>

      {/* Plans List */}
      <div className={styles.plansContainer}>
        {isLoading && (
          <div className={styles.loading}>Загрузка планов...</div>
        )}

        {!isLoading && reconstructions.length === 0 && selectedBuildingId && (
          <div className={styles.emptyState}>
            <p className={styles.emptyText}>
              Для сшивания нужно минимум 2 обработанных плана
            </p>
            <button
              className={styles.emptyButton}
              onClick={() => (window.location.href = '/wizard')}
            >
              Загрузить план
            </button>
          </div>
        )}

        {!isLoading && reconstructions.length > 0 && (
          <>
            <div className={styles.plansHeader}>
              <h3 className={styles.plansTitle}>
                <FileImage size={18} className={styles.plansTitleIcon} />
                Доступные фрагменты ({reconstructions.length})
              </h3>
              <span className={styles.selectionBadge}>
                ВЫБРАНО: <span className={styles.selectionCount}>{selectedIds.size}</span>
              </span>
            </div>

            <div className={styles.plansList}>
              {reconstructions.map((recon) => {
                const isSelected = selectedIds.has(String(recon.id));
                return (
                  <div
                    key={recon.id}
                    className={`${styles.planCard} ${isSelected ? styles.planCardSelected : ''}`}
                    onClick={() => handleToggleSelection(String(recon.id))}
                  >
                    <div className={styles.planPreview}>
                      <div className={styles.planPreviewGrid} />
                      {recon.preview_url ? (
                        <img
                          src={recon.preview_url}
                          alt={recon.name}
                          className={styles.planPreviewImage}
                          style={recon.rotation_angle ? { transform: `rotate(${recon.rotation_angle}deg)` } : undefined}
                        />
                      ) : (
                        <ImageIcon size={24} className={styles.planPreviewIcon} />
                      )}
                    </div>

                    <div className={styles.planInfo}>
                      <div className={styles.planMeta}>
                        <span className={styles.planId}>P{recon.id}</span>
                        <span className={styles.planDate}>
                          {new Date(recon.created_at).toLocaleDateString('ru-RU')}
                        </span>
                      </div>
                      <h4 className={styles.planName}>{recon.name}</h4>
                    </div>

                    <div className={styles.planStats}>
                      <div className={styles.planStatsLabel}>
                        Размечено<br />
                        <span className={styles.planStatsValue}>{recon.rooms_count}</span> узлов
                      </div>
                    </div>

                    <div className={styles.planCheckbox}>
                      {isSelected && <Check size={20} strokeWidth={3} />}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* Sticky Bottom Bar */}
      <div className={styles.bottomBar}>
        <div className={styles.bottomBarLeft}>
          {!isNextDisabled ? null : (
            <div className={styles.warningMessage}>
              <AlertTriangle size={16} className={styles.warningIcon} />
              МИНИМУМ 2 ПЛАНА ДЛЯ ОБЪЕДИНЕНИЯ
            </div>
          )}
        </div>
        <button
          onClick={handleNext}
          disabled={isNextDisabled}
          className={styles.btnStitch}
        >
          Сшить ({selectedIds.size})
          <ArrowRight size={18} className={styles.btnIcon} />
        </button>
      </div>
    </div>
  );
};
