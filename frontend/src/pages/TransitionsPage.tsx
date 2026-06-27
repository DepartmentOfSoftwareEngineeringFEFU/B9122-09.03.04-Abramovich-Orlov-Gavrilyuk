import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTransitions } from '../hooks/useTransitions';
import { transitionsApi } from '../api/transitionsApi';
import { reconstructionApi } from '../api/apiService';
import { TransitionPlanCanvas } from '../components/Transitions/TransitionPlanCanvas';
import { TeleportParamsModal } from '../components/Transitions/TeleportParamsModal';
import type { BuildingListItem } from '../types/transitions';
import styles from './TransitionsPage.module.css';

type ActiveTool = 'pan' | 'teleport' | 'delete';

export const TransitionsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Building/floor navigation in sidebar
  const [buildings, setBuildings] = useState<BuildingListItem[]>([]);
  const [buildingsLoading, setBuildingsLoading] = useState(false);
  const [buildingsError, setBuildingsError] = useState<string | null>(null);

  // Sidebar view: 'buildings' | 'floors'
  const [sidebarView, setSidebarView] = useState<'buildings' | 'floors'>('buildings');

  // Currently selected building (for sidebar drill-down)
  const [selectedBuildingId, setSelectedBuildingId] = useState<string>(
    searchParams.get('buildingId') ?? '',
  );

  // Cropped image URL cache: planId → data URL
  const [croppedUrlCache, setCroppedUrlCache] = useState<Record<number, string>>({});
  const [isCroppingImage, setIsCroppingImage] = useState(false);
  // Track the plan id currently being cropped to avoid duplicate requests
  const croppingPlanIdRef = useRef<number | null>(null);

  // Tool state
  const [activeTool, setActiveTool] = useState<ActiveTool>('pan');

  // Modal state
  const [showModal, setShowModal] = useState(false);
  // Polygon drawn that opened the teleport modal — used as FROM
  // after the user confirms the modal.
  const [pendingFromPolygon, setPendingFromPolygon] = useState<number[][] | null>(null);

  // Hook drives plans + transitions data
  const {
    plans,
    transitions,
    selectedPlanId,
    mode,
    isLoading,
    selectPlan,
    startAddingTransition,
    handlePlanSubmit,
    cancelMode,
    deleteTransition,
  } = useTransitions(selectedBuildingId);

  // Once startAddingTransition flips mode to 'placing_from', auto-place the FROM
  // point at the polygon that originally opened the modal.
  useEffect(() => {
    if (mode.type === 'placing_from' && pendingFromPolygon) {
      const geometry = pendingFromPolygon;
      setPendingFromPolygon(null);
      handlePlanSubmit(geometry);
    }
  }, [mode.type, pendingFromPolygon, handlePlanSubmit]);

  // Load buildings list once
  useEffect(() => {
    setBuildingsLoading(true);
    transitionsApi
      .listBuildings()
      .then((data) => {
        setBuildings(data);
        // If a building was pre-selected from URL, go straight to floors view
        if (searchParams.get('buildingId')) {
          setSidebarView('floors');
        }
      })
      .catch((err: unknown) => {
        setBuildingsError(String(err));
      })
      .finally(() => {
        setBuildingsLoading(false);
      });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch and crop the original plan image when the selected plan changes
  useEffect(() => {
    if (selectedPlanId === null) return;
    if (croppedUrlCache[selectedPlanId] !== undefined) return;
    if (croppingPlanIdRef.current === selectedPlanId) return;

    croppingPlanIdRef.current = selectedPlanId;
    setIsCroppingImage(true);

    reconstructionApi
      .getReconstructionById(selectedPlanId)
      .then((rec) => {
        const originalUrl = rec.original_image_url;
        if (!originalUrl) {
          // Fallback: no original image available
          setCroppedUrlCache((prev) => ({ ...prev, [selectedPlanId]: rec.preview_url ?? '' }));
          return;
        }

        const rotation = rec.rotation_angle ?? 0;
        const cropRect = rec.crop_rect ?? undefined;

        return prepareCroppedPlanImage(originalUrl, rotation, cropRect).then((dataUrl) => {
          setCroppedUrlCache((prev) => ({
            ...prev,
            [selectedPlanId]: dataUrl ?? originalUrl,
          }));
        });
      })
      .catch(() => {
        // Fallback to preview_url on error
        const plan = plans.find((p) => p.id === selectedPlanId);
        setCroppedUrlCache((prev) => ({ ...prev, [selectedPlanId]: plan?.preview_url ?? '' }));
      })
      .finally(() => {
        if (croppingPlanIdRef.current === selectedPlanId) {
          croppingPlanIdRef.current = null;
        }
        setIsCroppingImage(false);
      });
  }, [selectedPlanId]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeBuilding = buildings.find((b) => b.code === selectedBuildingId) ?? null;
  const selectedPlan = plans.find((p) => p.id === selectedPlanId);
  const imageUrl =
    selectedPlanId !== null
      ? (croppedUrlCache[selectedPlanId] ?? '')
      : '';

  const visibleTransitions =
    selectedPlanId !== null
      ? transitions.filter(
          (t) => t.from_reconstruction_id === selectedPlanId || t.to_reconstruction_id === selectedPlanId,
        )
      : [];

  const handleSelectBuilding = (buildingId: string) => {
    setSelectedBuildingId(buildingId);
    setSidebarView('floors');
  };

  const handleBackToBuildings = () => {
    setSidebarView('buildings');
  };

  const getModeHint = (): string => {
    if (mode.type === 'placing_from') return `Шаг 1/2 — кликните точку FROM (переход: "${mode.name}")`;
    if (mode.type === 'placing_to') return 'Шаг 2/2 — выберите план назначения и кликните точку TO';
    return '';
  };

  const handleCanvasSubmit = (geometry: number[][]) => {
    if (activeTool === 'teleport' && mode.type === 'idle' && selectedPlanId !== null) {
      setPendingFromPolygon(geometry);
      setShowModal(true);
      return;
    }
    handlePlanSubmit(geometry);
  };

  // Derived cursor for canvas area
  const canvasCursor =
    mode.type !== 'idle'
      ? 'crosshair'
      : activeTool === 'teleport'
        ? 'crosshair'
        : activeTool === 'delete'
          ? 'default'
          : 'grab';

  return (
    <div className={styles.page}>
      {/* Dark header */}
      <header className={styles.header}>
        <button
          className={styles.headerCloseBtn}
          onClick={() => navigate('/admin')}
          title="Закрыть"
        >
          ×
        </button>
      </header>

      {/* Mode banner (placing_from / placing_to) */}
      {mode.type !== 'idle' && (
        <div className={styles.modeBanner}>
          <span className={styles.modeBannerIcon}>⌖</span>
          <div>
            <div className={styles.modeBannerText}>{getModeHint()}</div>
            <div className={styles.modeBannerSub}>Кликните на план, чтобы разместить точку</div>
          </div>
          <button className={styles.modeBannerCancel} onClick={cancelMode}>
            Отменить
          </button>
        </div>
      )}

      {/* Main body: canvas + right sidebar */}
      <div className={styles.body}>
        {/* Canvas area */}
        <main className={`${styles.canvasArea} ${styles[`cursor_${canvasCursor}`]}`}>
          {(isLoading || isCroppingImage) && (
            <div className={styles.loadingOverlay}>
              <span className={styles.loadingText}>ЗАГРУЗКА...</span>
            </div>
          )}
          {!isLoading && !isCroppingImage && selectedPlan && imageUrl ? (
            <TransitionPlanCanvas
              imageUrl={imageUrl}
              transitions={transitions}
              reconstructionId={selectedPlan.id}
              mode={mode}
              activeTool={activeTool}
              onCanvasSubmit={handleCanvasSubmit}
              onDeleteTransition={activeTool === 'delete' ? deleteTransition : undefined}
            />
          ) : (
            !isLoading && !isCroppingImage && (
              <div className={styles.emptyCanvas}>
                {!selectedBuildingId
                  ? 'Выберите здание в панели справа'
                  : plans.length === 0
                    ? 'Нет планов для этого здания'
                    : 'Выберите план из списка справа'}
              </div>
            )
          )}
        </main>

        {/* Right sidebar: building/floor nav */}
        <aside className={styles.sidebar}>
          {sidebarView === 'buildings' ? (
            <>
              <div className={styles.sidebarHeader}>
                <span className={styles.sidebarHeaderLabel}>// Здания</span>
              </div>
              <div className={styles.sidebarList}>
                {buildingsLoading && (
                  <div className={styles.sidebarEmpty}>Загрузка...</div>
                )}
                {buildingsError && (
                  <div className={styles.sidebarError}>{buildingsError}</div>
                )}
                {!buildingsLoading && !buildingsError && buildings.length === 0 && (
                  <div className={styles.sidebarEmpty}>Нет зданий</div>
                )}
                {buildings.map((b) => (
                  <button
                    key={b.id}
                    className={`${styles.buildingRow} ${selectedBuildingId === b.code ? styles.buildingRowActive : ''}`}
                    onClick={() => handleSelectBuilding(b.code)}
                  >
                    <span className={styles.buildingRowName}>{b.name}</span>
                    <span className={styles.buildingRowArrow}>›</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className={styles.sidebarHeader}>
                <button
                  className={styles.backBtn}
                  onClick={handleBackToBuildings}
                  disabled={mode.type !== 'idle'}
                >
                  ‹ Здания
                </button>
                <span className={styles.sidebarBuildingName}>
                  {activeBuilding?.name ?? selectedBuildingId}
                </span>
              </div>
              <div className={styles.sidebarList}>
                {plans.length === 0 && !isLoading && (
                  <div className={styles.sidebarEmpty}>Нет планов</div>
                )}
                {plans.map((plan) => {
                  const count = transitions.filter(
                    (t) =>
                      t.from_reconstruction_id === plan.id || t.to_reconstruction_id === plan.id,
                  ).length;
                  const isActive = plan.id === selectedPlanId;
                  return (
                    <button
                      key={plan.id}
                      className={`${styles.floorRow} ${isActive ? styles.floorRowActive : ''}`}
                      onClick={() => selectPlan(plan.id)}
                      disabled={mode.type !== 'idle'}
                    >
                      <span className={styles.floorRowName}>{plan.name}</span>
                      <span className={styles.floorRowRight}>
                        {count > 0 && <span className={styles.floorBadge}>{count}</span>}
                        <span className={styles.floorActiveDot} />
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Teleports list for selected plan */}
              {selectedPlanId !== null && (
                <div className={styles.teleportList}>
                  <div className={styles.teleportListHeader}>
                    Переходы{selectedPlan ? ` — ${selectedPlan.name}` : ''}
                  </div>
                  {visibleTransitions.length === 0 ? (
                    <div className={styles.sidebarEmpty}>Нет переходов</div>
                  ) : (
                    visibleTransitions.map((t) => (
                      <div key={t.id} className={styles.teleportItem}>
                        <div className={styles.teleportItemDir}>
                          {t.from_reconstruction_id === selectedPlanId ? 'FROM' : 'TO'}
                        </div>
                        <div className={styles.teleportItemName}>{t.name}</div>
                        <button
                          className={styles.teleportDeleteBtn}
                          onClick={() => deleteTransition(t.id)}
                          title="Удалить"
                        >
                          ×
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </aside>
      </div>

      {/* Bottom toolbar */}
      <footer className={`${styles.toolbar} ${mode.type !== 'idle' ? styles.toolbarDimmed : ''}`}>
        <div className={styles.toolGroup}>
          <button
            className={`${styles.toolBtn} ${activeTool === 'pan' ? styles.toolBtnActive : ''}`}
            onClick={() => setActiveTool('pan')}
          >
            <span className={styles.toolBtnIcon}>✥</span>
            Перемещение
          </button>
          <button
            className={`${styles.toolBtn} ${activeTool === 'teleport' ? styles.toolBtnActive : ''}`}
            onClick={() => setActiveTool('teleport')}
            disabled={selectedPlanId === null}
          >
            <span className={styles.toolBtnIcon}>⬡</span>
            Добавить переход
          </button>
          <div className={styles.toolSep} />
          <button
            className={`${styles.toolBtn} ${styles.toolBtnDelete} ${activeTool === 'delete' ? styles.toolBtnDeleteActive : ''}`}
            onClick={() => setActiveTool('delete')}
          >
            <span className={styles.toolBtnIcon}>⊗</span>
            Удалить
          </button>
        </div>
        <button className={styles.finishBtn} onClick={() => navigate('/admin')}>
          Завершить работу
        </button>
      </footer>

      {/* Modal */}
      {showModal && selectedPlanId !== null && (
        <TeleportParamsModal
          plans={plans}
          currentPlanId={selectedPlanId}
          onConfirm={(name, toReconId) => {
            setShowModal(false);
            setActiveTool('pan');
            startAddingTransition(name, toReconId);
            // pendingFromPoint stays set; the effect below auto-places it once
            // mode flips to 'placing_from'.
          }}
          onCancel={() => {
            setShowModal(false);
            setActiveTool('pan');
            setPendingFromPolygon(null);
          }}
        />
      )}
    </div>
  );
};

// Helper

const prepareCroppedPlanImage = (
  imageUrl: string,
  rotation?: number,
  cropRect?: { x: number; y: number; width: number; height: number } | null,
): Promise<string | null> => {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const rot = rotation ?? 0;
      const swap = rot === 90 || rot === 270;
      const rCanvas = document.createElement('canvas');
      rCanvas.width = swap ? img.height : img.width;
      rCanvas.height = swap ? img.width : img.height;
      const rCtx = rCanvas.getContext('2d');
      if (!rCtx) { resolve(null); return; }
      rCtx.translate(rCanvas.width / 2, rCanvas.height / 2);
      rCtx.rotate((rot * Math.PI) / 180);
      rCtx.drawImage(img, -img.width / 2, -img.height / 2);

      if (cropRect) {
        const cx = Math.round(cropRect.x * rCanvas.width);
        const cy = Math.round(cropRect.y * rCanvas.height);
        const cw = Math.round(cropRect.width * rCanvas.width);
        const ch = Math.round(cropRect.height * rCanvas.height);
        const cropCanvas = document.createElement('canvas');
        cropCanvas.width = cw;
        cropCanvas.height = ch;
        const cropCtx = cropCanvas.getContext('2d');
        if (!cropCtx) { resolve(rCanvas.toDataURL()); return; }
        cropCtx.drawImage(rCanvas, cx, cy, cw, ch, 0, 0, cw, ch);
        resolve(cropCanvas.toDataURL());
      } else {
        resolve(rCanvas.toDataURL());
      }
    };
    img.onerror = () => resolve(null);
    img.src = imageUrl;
  });
};
