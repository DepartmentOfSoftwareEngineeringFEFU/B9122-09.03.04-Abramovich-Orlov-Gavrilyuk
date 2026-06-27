import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useBuildings } from '../../hooks/useBuildings';
import { useFloors } from '../../hooks/useFloors';
import styles from './BuildingFloorPicker.module.css';

interface BuildingFloorPickerProps {
  selectedBuildingId: number | null;
  selectedFloorId: number | null;
  onChange: (data: { buildingId: number | null; floorId: number | null }) => void;
  planName?: string;
  onPlanNameChange?: (name: string) => void;
  disabled?: boolean;
}

export const BuildingFloorPicker: React.FC<BuildingFloorPickerProps> = ({
  selectedBuildingId,
  selectedFloorId,
  onChange,
  planName,
  onPlanNameChange,
  disabled = false,
}) => {
  const { buildings, isLoading: buildingsLoading } = useBuildings();
  const { floors, isLoading: floorsLoading, loadForBuilding, createFloor } = useFloors();

  const [newFloorNum, setNewFloorNum] = useState('');
  const [isCreatingFloor, setIsCreatingFloor] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const handleCreateFloor = async () => {
    if (selectedBuildingId === null || !newFloorNum) return;
    const num = parseInt(newFloorNum, 10);
    if (isNaN(num)) return;
    setIsCreatingFloor(true);
    try {
      const created = await createFloor(selectedBuildingId, num);
      onChange({ buildingId: selectedBuildingId, floorId: created.id });
      setNewFloorNum('');
      setShowCreate(false);
    } catch (e) {
      console.error('Ошибка при создании этажа', e);
    } finally {
      setIsCreatingFloor(false);
    }
  };

  // Load floors when building changes
  useEffect(() => {
    if (selectedBuildingId !== null) {
      void loadForBuilding(selectedBuildingId);
    }
  }, [selectedBuildingId, loadForBuilding]);

  const handleBuildingChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    const buildingId = value === '' ? null : parseInt(value, 10);
    // Reset floor when building changes
    onChange({ buildingId, floorId: null });
  };

  const handleFloorChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    const floorId = value === '' ? null : parseInt(value, 10);
    onChange({ buildingId: selectedBuildingId, floorId });
  };

  if (buildingsLoading) {
    return <div className={styles.loading}>Загрузка корпусов...</div>;
  }

  if (buildings.length === 0) {
    return (
      <div className={styles.empty}>
        <span>Нет доступных корпусов.</span>
        <Link to="/admin/buildings" className={styles.createLink}>
          Создать корпус
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.picker}>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="bfp-building">
          Корпус
        </label>
        <select
          id="bfp-building"
          className={styles.select}
          value={selectedBuildingId ?? ''}
          onChange={handleBuildingChange}
          disabled={disabled}
        >
          <option value="">— выберите корпус —</option>
          {buildings.map((b) => (
            <option key={b.id} value={b.id}>
              {b.code} — {b.name}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="bfp-floor">
          Этаж
        </label>
        
        {selectedBuildingId === null ? (
          <select className={styles.select} disabled>
            <option value="">— сначала выберите корпус —</option>
          </select>
        ) : floorsLoading ? (
          <select className={styles.select} disabled>
            <option value="">Загрузка этажей...</option>
          </select>
        ) : floors.length === 0 || showCreate ? (
          <div className={styles.createInline}>
            <input
              type="number"
              placeholder="Номер этажа"
              className={styles.inlineInput}
              value={newFloorNum}
              onChange={(e) => setNewFloorNum(e.target.value)}
              disabled={isCreatingFloor}
            />
            <button
              type="button"
              className={styles.inlineBtn}
              onClick={handleCreateFloor}
              disabled={isCreatingFloor || !newFloorNum}
            >
              {isCreatingFloor ? '...' : 'Создать'}
            </button>
            {floors.length > 0 && (
              <button
                type="button"
                className={styles.inlineBtnCancel}
                onClick={() => setShowCreate(false)}
              >
                Отмена
              </button>
            )}
          </div>
        ) : (
          <div className={styles.selectWithAdd}>
            <select
              id="bfp-floor"
              className={styles.select}
              value={selectedFloorId ?? ''}
              onChange={handleFloorChange}
              disabled={disabled}
              style={{ flex: 1 }}
            >
              <option value="">— выберите этаж —</option>
              {floors.map((f) => (
                <option key={f.id} value={f.id}>
                  Этаж {f.number}
                </option>
              ))}
            </select>
            <button
              type="button"
              className={styles.addBtn}
              onClick={() => setShowCreate(true)}
              title="Создать новый этаж"
              disabled={disabled}
            >
              +
            </button>
          </div>
        )}
      </div>

      {planName !== undefined && onPlanNameChange && (
        <div className={styles.field}>
          <label className={styles.label} htmlFor="bfp-plan-name">
            Название плана
          </label>
          <input
            id="bfp-plan-name"
            type="text"
            className={styles.input}
            value={planName}
            onChange={(e) => onPlanNameChange(e.target.value)}
            placeholder="Введите название плана"
            disabled={disabled}
          />
        </div>
      )}
    </div>
  );
};
