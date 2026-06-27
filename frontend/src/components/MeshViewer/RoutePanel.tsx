import React, { useState } from 'react';
import styles from './RoutePanel.module.css';
import type { RoomAnnotation } from '../../types/wizard';

interface RouteResult {
  status: string;
  from_room?: string;
  to_room?: string;
  total_distance_meters?: number;
  estimated_time_seconds?: number;
  message?: string;
}

interface RoutePanelProps {
  rooms: RoomAnnotation[];
  onFindRoute: (fromId: string, toId: string) => void;
  isLoading: boolean;
  routeResult: RouteResult | null;
}

export const RoutePanel: React.FC<RoutePanelProps> = ({
  rooms,
  onFindRoute,
  isLoading,
  routeResult,
}) => {
  const [fromRoom, setFromRoom] = useState<string>('');
  const [toRoom, setToRoom] = useState<string>('');

  const handleFind = () => {
    if (fromRoom && toRoom && fromRoom !== toRoom) {
      onFindRoute(fromRoom, toRoom);
    }
  };

  const canFind = fromRoom && toRoom && fromRoom !== toRoom && !isLoading;

  return (
    <div className={styles.panel}>
      <div className={styles.inner}>
        <div className={styles.sectionTitle}>// МАРШРУТИЗАЦИЯ</div>

        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel}>Откуда</label>
          <select
            className={styles.select}
            value={fromRoom}
            onChange={(e) => setFromRoom(e.target.value)}
          >
            <option value="">— Выберите комнату —</option>
            {rooms.map((room) => (
              <option key={room.id} value={room.id}>
                {room.name || room.room_type} ({room.id.slice(0, 8)})
              </option>
            ))}
          </select>
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel}>Куда</label>
          <select
            className={styles.select}
            value={toRoom}
            onChange={(e) => setToRoom(e.target.value)}
          >
            <option value="">— Выберите комнату —</option>
            {rooms.filter((r) => r.id !== fromRoom).map((room) => (
              <option key={room.id} value={room.id}>
                {room.name || room.room_type} ({room.id.slice(0, 8)})
              </option>
            ))}
          </select>
        </div>

        <button
          className={styles.findBtn}
          onClick={handleFind}
          disabled={!canFind}
        >
          {isLoading ? 'Поиск...' : '> НАЙТИ МАРШРУТ'}
        </button>

        <div className={styles.divider} />

        {routeResult && routeResult.status === 'success' && (
          <div>
            <div className={styles.sectionTitle}>// МАРШРУТ</div>
            <div className={styles.routeInfo}>
              <div className={styles.routeRow}>
                <span className={styles.routeLabel}>От</span>
                <span className={styles.routeValue}>{routeResult.from_room}</span>
              </div>
              <div className={styles.routeRow}>
                <span className={styles.routeLabel}>До</span>
                <span className={styles.routeValue}>{routeResult.to_room}</span>
              </div>
              <div className={styles.divider} />
              <div className={styles.metricsGrid}>
                <div className={styles.metricItem}>
                  <span className={styles.metricValue}>
                    {routeResult.total_distance_meters?.toFixed(1)}
                  </span>
                  <span className={styles.metricLabel}>метров</span>
                </div>
                <div className={styles.metricItem}>
                  <span className={styles.metricValue}>
                    {routeResult.estimated_time_seconds}
                  </span>
                  <span className={styles.metricLabel}>секунд</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {routeResult && routeResult.status === 'no_path' && (
          <div className={styles.errorMsg}>
            Маршрут не найден. Проверьте разметку дверей.
          </div>
        )}
      </div>
    </div>
  );
};
