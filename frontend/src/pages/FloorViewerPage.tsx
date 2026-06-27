import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import MeshViewer, { type MeshViewerHandle } from '../components/MeshViewer';
import { BuildingFloorSectionSelector } from '../components/FloorViewer/BuildingFloorSectionSelector';
import { FloorMinimap } from '../components/FloorViewer/FloorMinimap';
import { RouteInputs } from '../components/FloorViewer/RouteInputs';
import { ZoomControls } from '../components/FloorViewer/ZoomControls';
import { useFloorViewer } from '../hooks/useFloorViewer';
import styles from './FloorViewerPage.module.css';

export const FloorViewerPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    catalog,
    isLoading,
    error,
    selectedBuildingId,
    selectedFloorId,
    selectedSectionId,
    visibleFloors,
    visibleSections,
    activeMeshUrl,
    selectBuilding,
    selectFloor,
    selectSection,
    planRoute,
    routeError,
    highlightedSectionIds,
  } = useFloorViewer();

  const [startPoint, setStartPoint] = useState('');
  const [endPoint, setEndPoint] = useState('');
  const [isRouting, setIsRouting] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Show toast when routeError appears
  useEffect(() => {
    if (routeError) {
      setShowToast(true);
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      toastTimerRef.current = setTimeout(() => setShowToast(false), 4000);
    }
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, [routeError]);

  const handlePlanRoute = useCallback(async () => {
    if (!startPoint.trim() || !endPoint.trim()) return;
    setIsRouting(true);
    try {
      await planRoute(startPoint.trim(), endPoint.trim());
    } finally {
      setIsRouting(false);
    }
  }, [planRoute, startPoint, endPoint]);

  const handleSwap = useCallback(() => {
    setStartPoint((prevStart) => {
      const prevEnd = endPoint;
      setEndPoint(prevStart);
      return prevEnd;
    });
  }, [endPoint]);

  // Zoom: programmatic via MeshViewer ref
  const meshRef = useRef<MeshViewerHandle>(null);
  const handleZoomIn = useCallback(() => meshRef.current?.zoomIn(), []);
  const handleZoomOut = useCallback(() => meshRef.current?.zoomOut(), []);

  // Derive selected building code for header
  const selectedBuilding = catalog.find((b) => b.id === selectedBuildingId);

  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>Загрузка каталога...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>{error}</div>
      </div>
    );
  }

  if (catalog.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>Контент пока не загружен</div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Header */}
      <header className={styles.header}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={() => navigate('/')}
        >
          ← ДВФУ
        </button>
        {selectedBuilding && (
          <>
            <span className={styles.headerSeparator}>›</span>
            <span className={styles.headerTitle}>Корпус {selectedBuilding.code}</span>
          </>
        )}
      </header>

      {/* Body */}
      <div className={styles.body}>
        {/* Left panel */}
        <aside className={styles.leftPanel}>
          {/* Route inputs */}
          <div className={styles.routeSection}>
            <RouteInputs
              start={startPoint}
              end={endPoint}
              onStartChange={setStartPoint}
              onEndChange={setEndPoint}
              onSwap={handleSwap}
              onSubmit={() => void handlePlanRoute()}
              disabled={isRouting}
              error={null}
            />
          </div>

          {/* Building/Floor/Section selector */}
          <div className={styles.selectorSection}>
            <BuildingFloorSectionSelector
              buildings={catalog}
              visibleFloors={visibleFloors}
              visibleSections={visibleSections}
              selectedBuildingId={selectedBuildingId}
              selectedFloorId={selectedFloorId}
              selectedSectionId={selectedSectionId}
              onSelectBuilding={selectBuilding}
              onSelectFloor={selectFloor}
              onSelectSection={selectSection}
            />
          </div>

          {/* Minimap */}
          <div className={styles.minimapSection}>
            <FloorMinimap
              sections={visibleSections}
              wallPolygons={
                visibleFloors.find((f) => f.id === selectedFloorId)?.wall_polygons ?? null
              }
              activeSectionId={selectedSectionId}
              highlightedSectionIds={highlightedSectionIds}
              onSelectSection={selectSection}
            />
          </div>
        </aside>

        {/* Right panel (3D viewer) */}
        <main className={styles.rightPanel}>
          <div className={styles.viewerContainer}>
            {activeMeshUrl ? (
              <MeshViewer ref={meshRef} url={activeMeshUrl} format="glb" />
            ) : (
              <div className={styles.placeholder}>Выберите отсек</div>
            )}
          </div>

          {/* Zoom controls (only meaningful when mesh is shown) */}
          {activeMeshUrl && (
            <ZoomControls onZoomIn={handleZoomIn} onZoomOut={handleZoomOut} />
          )}

          {/* Route error toast */}
          {showToast && routeError && (
            <div className={styles.toast}>{routeError}</div>
          )}
        </main>
      </div>
    </div>
  );
};

export default FloorViewerPage;
