import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useStitching } from '../hooks/useStitching';
import { useStitchingHistory } from '../hooks/useStitchingHistory';
import { PlanSelectionStep } from '../components/Stitching/PlanSelectionStep';
import { StitchingCanvas } from '../components/Stitching/StitchingCanvas';
import { StitchingSidebar } from '../components/Stitching/StitchingSidebar';
import type { StitchingSnapshot } from '../types/stitching';
import styles from './StitchingPage.module.css';
export const StitchingPage: React.FC = () => {
  const navigate = useNavigate();
  const stitching = useStitching();
  const history = useStitchingHistory();

  const { state } = stitching;

  const restoreCanvasFromSnapshot = stitching.restoreCanvasFromSnapshot;

  const handleNext = () => {
    if (state.step === 1) {
      stitching.nextStep();
    } else if (state.step === 2) {
      const name = prompt('Введите название объединённого плана:');
      if (name) {
        stitching.submitStitching(name);
      }
    }
  };

  const handlePrev = () => {
    if (state.step === 1) {
      navigate('/admin');
    } else if (state.step === 2) {
      if (window.confirm('Вернуться к выбору планов? Все изменения будут потеряны.')) {
        stitching.prevStep();
      }
    }
  };

  const handleUndo = () => {
    const snapshot = history.undo();
    if (snapshot) {
      // Restore layers from snapshot
      snapshot.layers.forEach((layerSnapshot) => {
        stitching.updateLayer(layerSnapshot.reconstructionId, {
          transform: layerSnapshot.transform,
          clipPolygons: layerSnapshot.clipPolygons,
          rectCrop: layerSnapshot.rectCrop,
          zIndex: layerSnapshot.zIndex,
        });
      });
      restoreCanvasFromSnapshot(snapshot);
    }
  };

  const handleRedo = () => {
    const snapshot = history.redo();
    if (snapshot) {
      // Restore layers from snapshot
      snapshot.layers.forEach((layerSnapshot) => {
        stitching.updateLayer(layerSnapshot.reconstructionId, {
          transform: layerSnapshot.transform,
          clipPolygons: layerSnapshot.clipPolygons,
          rectCrop: layerSnapshot.rectCrop,
          zIndex: layerSnapshot.zIndex,
        });
      });
      restoreCanvasFromSnapshot(snapshot);
    }
  };

  // Step 2 renders fullscreen editor without WizardShell
  if (state.step === 2) {
    return (
      <div className={styles.stitchingEditor}>
        <div className={styles.editorMain}>
          <div className={styles.stitchingCanvasArea}>
            <div className={styles.undoRedoBar}>
              <button className={styles.undoRedoBtn} onClick={handleUndo} disabled={!history.canUndo}>
                ↶ Отменить
              </button>
              <button className={styles.undoRedoBtn} onClick={handleRedo} disabled={!history.canRedo}>
                ↷ Повторить
              </button>
            </div>
            <StitchingCanvas
              layers={state.layers}
              activeTool={state.activeTool}
              selectedLayerId={state.selectedLayerId}
              onLayerUpdate={stitching.updateLayer}
              onSnapshotPush={(snapshot: unknown) => {
                history.pushState(snapshot as StitchingSnapshot);
              }}
              onUndo={handleUndo}
              onRedo={handleRedo}
            />
          </div>
          <StitchingSidebar
            activeTool={state.activeTool}
            onToolChange={stitching.setActiveTool}
            layers={state.layers}
            selectedLayerId={state.selectedLayerId}
            onLayerSelect={stitching.setSelectedLayerId}
            onLayerMove={(id, direction) => {
              stitching.reorderLayers(id, direction);
            }}
            onMaskOpacityChange={(id, opacity) => {
              stitching.updateLayer(id, { maskOpacity: opacity });
            }}
            onShowMaskToggle={(id) => {
              const layer = state.layers.find((l) => l.reconstructionId === id);
              if (layer) {
                stitching.updateLayer(id, { showMask: !layer.showMask });
              }
            }}
            onPropertyChange={(id, property, value) => {
              const layer = state.layers.find((l) => l.reconstructionId === id);
              if (layer) {
                stitching.updateLayer(id, {
                  transform: { ...layer.transform, [property]: value },
                });
              }
            }}
          />
        </div>
        <div className={styles.stitchingFooter}>
          <button onClick={handlePrev} className={styles.btnSecondary}>
            Назад
          </button>
          <button onClick={handleNext} className={styles.btnPrimary} disabled={state.isLoading}>
            &gt; СШИТЬ
          </button>
        </div>
      </div>
    );
  }

  // Step 1 renders inside WizardShell (with AppLayout menu)
  return (
    <PlanSelectionStep
      onNext={async (ids, buildingId, floorNumber) => {
        await stitching.selectPlans(ids, buildingId, floorNumber);
        stitching.nextStep();
      }}
      onCancel={() => navigate('/admin')}
    />
  );
};
