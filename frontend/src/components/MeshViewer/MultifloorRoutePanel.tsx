// Route-building controls for the cross-floor 3D routes view (subfeature D):
// from/to floor + room pickers, a run button, a distance/time readout, and a
// not_aligned prompt. Self-contained (owns useMultifloorRoute); reports each
// result via onResult so the host can render the route in its 3D scene. Reusable
// in both the admin view and the end-user start screen.

import React, { useEffect, useMemo } from 'react';
import { ArrowRight } from 'lucide-react';
import { useMultifloorRoute } from '../../hooks/useMultifloorRoute';
import type { MultifloorRouteResponse } from '../../types/buildingNav';
import type { Room3DApi } from '../../api/apiService';
import styles from './MultifloorRoutePanel.module.css';

export interface RouteFloorOption {
  floor_id: number;
  number: number;
}

interface Props {
  buildingId: number;
  floors: RouteFloorOption[];
  roomsByFloor: Record<number, Room3DApi[]>;
  onResult?: (result: MultifloorRouteResponse | null) => void;
  onGoToAssembly?: () => void;
}

// Only real rooms (cabinets) are pickable endpoints — stairs and elevators are
// transit points the route passes THROUGH, so they're excluded from the list.
function roomOptions(rooms: Room3DApi[] | undefined): Room3DApi[] {
  return (rooms ?? []).filter(
    (r) =>
      r.id !== undefined &&
      r.id !== null &&
      r.room_type !== 'staircase' &&
      r.room_type !== 'elevator',
  );
}

export const MultifloorRoutePanel: React.FC<Props> = ({
  buildingId,
  floors,
  roomsByFloor,
  onResult,
  onGoToAssembly,
}) => {
  const route = useMultifloorRoute(buildingId);
  const {
    fromFloorId,
    setFromFloorId,
    fromRoom,
    setFromRoom,
    toFloorId,
    setToFloorId,
    toRoom,
    setToRoom,
    result,
    loading,
    error,
    run,
  } = route;

  useEffect(() => {
    onResult?.(result);
  }, [result, onResult]);

  // Rooms have globally-unique names, so the operator picks a room directly —
  // no floor step. The composite value `${floorId}:${roomId}` lets us set BOTH
  // the room and its floor (the route payload still needs the floor id).
  const allRooms = useMemo(() => {
    const out: { key: string; floorId: number; roomId: string; label: string }[] = [];
    for (const f of floors) {
      for (const r of roomOptions(roomsByFloor[f.floor_id])) {
        const roomId = String(r.id);
        out.push({
          key: `${f.floor_id}:${roomId}`,
          floorId: f.floor_id,
          roomId,
          label: r.name || roomId,
        });
      }
    }
    return out;
  }, [floors, roomsByFloor]);

  const fromValue = fromFloorId !== null && fromRoom ? `${fromFloorId}:${fromRoom}` : '';
  const toValue = toFloorId !== null && toRoom ? `${toFloorId}:${toRoom}` : '';
  // Block routing a room to itself — same floor AND same room (identical value).
  const sameRoom = fromValue !== '' && fromValue === toValue;

  const pickRoom = (
    value: string,
    setFloor: (n: number | null) => void,
    setRoom: (s: string) => void,
  ): void => {
    if (value === '') {
      setFloor(null);
      setRoom('');
      return;
    }
    const idx = value.indexOf(':');
    setFloor(Number(value.slice(0, idx)));
    setRoom(value.slice(idx + 1));
  };

  return (
    <div className={styles.panel}>
      <h3 className={styles.heading}>Маршрут</h3>

      <div className={styles.group}>
        <span className={styles.groupLabel}>Откуда</span>
        <select
          className={styles.select}
          value={fromValue}
          onChange={(e) => pickRoom(e.target.value, setFromFloorId, setFromRoom)}
        >
          <option value="">Кабинет…</option>
          {allRooms.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.group}>
        <span className={styles.groupLabel}>Куда</span>
        <select
          className={styles.select}
          value={toValue}
          onChange={(e) => pickRoom(e.target.value, setToFloorId, setToRoom)}
        >
          <option value="">Кабинет…</option>
          {allRooms.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        className={styles.runBtn}
        onClick={() => void run()}
        disabled={loading || sameRoom}
      >
        {loading ? (
          'Поиск…'
        ) : (
          <>
            Построить маршрут
            <ArrowRight size={18} />
          </>
        )}
      </button>

      {sameRoom && (
        <div className={styles.warn}>Откуда и куда — один и тот же кабинет.</div>
      )}

      {error && <div className={styles.error}>{error}</div>}

      {result && result.status === 'no_path' && (
        <div className={styles.warn}>Маршрут не найден.</div>
      )}
      {result && result.status === 'not_aligned' && (
        <div className={styles.warn}>
          {result.message || 'Этажи не выровнены.'}
          {onGoToAssembly && (
            <button type="button" className={styles.linkBtn} onClick={onGoToAssembly}>
              К сборке здания
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default MultifloorRoutePanel;
