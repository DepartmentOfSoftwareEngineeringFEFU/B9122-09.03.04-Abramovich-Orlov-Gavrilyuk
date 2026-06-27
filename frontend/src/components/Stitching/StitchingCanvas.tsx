import React, { useRef, useEffect } from 'react';
import type { LayerData, StitchingSnapshot } from '../../types/stitching';
import { useStitchingCanvas } from '../../hooks/useStitchingCanvas';
import styles from './StitchingCanvas.module.css';

interface StitchingCanvasProps {
  layers: LayerData[];
  activeTool: 'move' | 'rotate' | 'rect_crop' | 'polygon_clip';
  selectedLayerId: string | null;
  onLayerUpdate: (layerId: string, updates: Partial<LayerData>) => void;
  onSnapshotPush: (snapshot: StitchingSnapshot) => void;
  onUndo: () => void;
  onRedo: () => void;
}

export const StitchingCanvas: React.FC<StitchingCanvasProps> = ({
  layers,
  activeTool,
  selectedLayerId,
  onLayerUpdate,
  onSnapshotPush,
  onUndo,
  onRedo,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  const { loadPlanToCanvas } = useStitchingCanvas({
    containerRef,
    layers,
    activeTool,
    selectedLayerId,
    onLayerUpdate,
    onSnapshotPush,
  });

  // Load plans to canvas when layers change
  useEffect(() => {
    if (layers.length > 0) {
      layers.forEach((layer) => {
        loadPlanToCanvas(layer);
      });
    }
  }, [layers.map((layer) => layer.reconstructionId).join(',')]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === 'KeyZ' && !e.shiftKey) {
        e.preventDefault();
        onUndo();
      } else if (e.ctrlKey && e.shiftKey && e.code === 'KeyZ') {
        e.preventDefault();
        onRedo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onUndo, onRedo]);

  return (
    <div ref={containerRef} className={styles.stitchingCanvasContainer}>
      <canvas />
      <div className={styles.canvasHint}>
        Пробел + мышь = перемещение холста
      </div>
    </div>
  );
};
