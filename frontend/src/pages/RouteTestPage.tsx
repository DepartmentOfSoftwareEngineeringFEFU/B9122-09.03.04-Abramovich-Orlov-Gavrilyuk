import React from 'react';
import { useNavigate } from 'react-router-dom';
import MeshViewer from '../components/MeshViewer';
import { FloorRouteView } from '../components/MeshViewer/FloorRouteView';
import { RouteBottomBar } from '../components/MeshViewer/RouteBottomBar';
import { useRouteTest } from '../hooks/useRouteTest';
import { adjacentTransitions } from '../hooks/useRouteTest.helpers';
import styles from './RouteTestPage.module.css';

export const RouteTestPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    isLoadingRegistry,
    isRouting,
    error,
    rooms,
    fromRoom,
    toRoom,
    setFromRoom,
    setToRoom,
    currentMeshUrl,
    invalidPairReason,
    routeResult,
    currentSegment,
    currentSegmentIndex,
    goToNextSegment,
    goToPrevSegment,
    findRoute,
  } = useRouteTest();

  const meshFormat: 'glb' | 'obj' | undefined = currentMeshUrl
    ? currentMeshUrl.toLowerCase().endsWith('.glb')
      ? 'glb'
      : 'obj'
    : undefined;

  const success = routeResult?.status === 'success';
  const noPath = routeResult?.status === 'no_path';
  const pathSegments = routeResult?.path_segments ?? [];
  const transitionsUsed = routeResult?.transitions_used ?? [];
  const totalSegments = pathSegments.length;

  const { incoming, outgoing } = currentSegment
    ? adjacentTransitions(currentSegmentIndex, pathSegments, transitionsUsed)
    : { incoming: null, outgoing: null };

  const isFirst = currentSegmentIndex === 0;
  const isLast = currentSegmentIndex === Math.max(0, totalSegments - 1);

  // Resolve from/to room display names from the synthetic-id-keyed list.
  // Label format: "<BuildingCode>-<FloorNum>-<SectionNum>__<RoomName>"
  // Extract the room name portion after the last '__'.
  const fromRoomLabel = rooms.find((r) => r.id === fromRoom)?.name?.split('__').pop();
  const toRoomLabel = rooms.find((r) => r.id === toRoom)?.name?.split('__').pop();

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <strong>Тестовый маршрут</strong>
        <span style={{ color: '#666', fontSize: 13 }}>
          Выберите две комнаты — система сама определит этаж и здание.
        </span>
        <span className={styles.spacer} />
        {success && totalSegments > 1 && currentSegment && (
          <span style={{ color: '#333', fontSize: 13 }}>
            Этаж {currentSegmentIndex + 1} / {totalSegments}
            {currentSegment.floor_number != null
              ? ` · ${currentSegment.floor_name}`
              : ''}
          </span>
        )}
        {isLoadingRegistry && (
          <span style={{ color: '#666' }}>Загрузка комнат…</span>
        )}
        {error && <span style={{ color: '#dc3545' }}>{error}</span>}
        {isRouting && <span style={{ color: '#666' }}>Поиск маршрута…</span>}
        {success && routeResult.total_distance_meters != null && (
          <span style={{ color: '#198754' }}>
            Длина: {routeResult.total_distance_meters.toFixed(1)} м
            {routeResult.estimated_time_seconds != null
              ? ` · ${Math.round(routeResult.estimated_time_seconds)} с`
              : ''}
          </span>
        )}
      </div>

      <div className={styles.viewer}>
        {currentMeshUrl ? (
          <MeshViewer url={currentMeshUrl} format={meshFormat}>
            {success && currentSegment && (
              <FloorRouteView
                segment={currentSegment}
                outgoing={outgoing}
                incoming={incoming}
                fromRoom3D={routeResult.from_room_3d}
                toRoom3D={routeResult.to_room_3d}
                fromRoomLabel={fromRoomLabel}
                toRoomLabel={toRoomLabel}
                isFirst={isFirst}
                isLast={isLast}
                onTeleportForward={goToNextSegment}
                onTeleportBack={goToPrevSegment}
              />
            )}
          </MeshViewer>
        ) : (
          <div className={styles.placeholder}>
            {isLoadingRegistry
              ? 'Загрузка…'
              : rooms.length === 0
                ? 'Нет доступных комнат. Сначала постройте этажи.'
                : 'Выберите начальную комнату «От», чтобы открыть 3D-этаж'}
          </div>
        )}

        {/* Floor navigation controls (visible for multi-floor routes only) */}
        {success && totalSegments > 1 && (
          <div className={styles.floorNav}>
            <button
              type="button"
              className={styles.navBtn}
              onClick={goToPrevSegment}
              disabled={isFirst}
            >
              ← Этаж назад
            </button>
            <span className={styles.floorLabel}>
              {currentSegment?.floor_name ??
                (currentSegment?.floor_number != null
                  ? `Этаж ${currentSegment.floor_number}`
                  : '—')}
            </span>
            <button
              type="button"
              className={styles.navBtn}
              onClick={goToNextSegment}
              disabled={isLast}
            >
              Этаж вперёд →
            </button>
          </div>
        )}

        {invalidPairReason && (
          <div className={styles.errorHud}>{invalidPairReason}</div>
        )}
        {noPath && (
          <div className={styles.errorHud}>
            Маршрут не найден. Проверьте разметку дверей и переходов.
          </div>
        )}
        {routeResult?.status === 'error' && routeResult.message && (
          <div className={styles.errorHud}>{routeResult.message}</div>
        )}
      </div>

      <RouteBottomBar
        rooms={rooms}
        fromRoom={fromRoom}
        toRoom={toRoom}
        onFromChange={setFromRoom}
        onToChange={setToRoom}
        onFindRoute={findRoute}
        isLoading={isRouting}
        onPrev={() => navigate('/admin')}
        onNext={() => undefined}
        isNextDisabled={true}
      />
    </div>
  );
};

export default RouteTestPage;
