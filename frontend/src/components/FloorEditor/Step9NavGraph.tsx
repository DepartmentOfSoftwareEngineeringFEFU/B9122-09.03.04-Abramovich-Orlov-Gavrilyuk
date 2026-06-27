// Step 9: dedicated «Навигационный граф» step. Build the floor nav graph
// from the assembled DB state, then draw its 2D node/edge data over the master
// схема as a backdrop. Extracted out of Step9FloorPreview so the graph build has
// its own step before the 3D model (now step 10).
//
// 2D rendering MIRRORS StepNavGraph (the single-plan reconstruction step): the
// canvas intrinsic size is metadata.mask_width × mask_height, the backdrop image
// is stretched to fill it, and node `pos` / edge `pts` are drawn directly (already
// in canvas px). CSS `object-fit: contain` scales the canvas without distortion.
//
// Presentational only — build state lives in useFloorNavGraph; the fetched 2D
// payload is a local UI concern (only this step draws it).

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useFloorNavGraph } from '../../hooks/useFloorNavGraph';
import { floorNavApi } from '../../api/floorNavApi';
import type { NavGraph2DResponse, NavGraph2DNode } from '../../api/floorNavApi';
import wizardStyles from './WizardStep.module.css';
import styles from './Step9NavGraph.module.css';

interface Step9NavGraphProps {
  floorId: number | null;
  masterMaskUrl: string | null;
  onBack: () => void;
  onNext: () => void;
}

export const Step9NavGraph: React.FC<Step9NavGraphProps> = ({
  floorId,
  masterMaskUrl,
  onBack,
  onNext,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nav = useFloorNavGraph();
  const [graph2d, setGraph2d] = useState<NavGraph2DResponse | null>(null);

  // Build the graph, then fetch its 2D payload for drawing. Errors surface via the
  // hook's toasts; a missing graph (404) simply leaves graph2d null.
  const handleBuild = useCallback(async () => {
    if (floorId === null) return;
    await nav.buildFloorGraph(floorId);
    try {
      const data = await floorNavApi.getNavGraph2d(floorId);
      setGraph2d(data);
    } catch {
      setGraph2d(null);
    }
  }, [floorId, nav]);

  // Draw the graph onto the canvas. Mirrors StepNavGraph: intrinsic canvas size =
  // mask dims; backdrop (master mask) stretched to fill; edges then nodes in px.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !graph2d) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const mw = graph2d.metadata.mask_width;
    const mh = graph2d.metadata.mask_height;
    if (!mw || !mh) return;

    const drawGraph = () => {
      const nodeMap = new Map<string | number, NavGraph2DNode>();
      for (const node of graph2d.graph.nodes) nodeMap.set(node.id, node);

      // Edges.
      for (const link of graph2d.graph.edges) {
        const src = nodeMap.get(link.source);
        const tgt = nodeMap.get(link.target);
        if (!src || !tgt) continue;

        const color =
          link.type === 'corridor_edge' ? 'rgba(255,255,255,0.35)' :
          link.type === 'room_to_door' ? '#FF4500' :
          link.type === 'door_to_corridor' ? '#4CAF50' :
          'rgba(255,255,255,0.2)';

        ctx.strokeStyle = color;
        ctx.lineWidth = link.type === 'corridor_edge' ? 1 : 2;
        ctx.beginPath();

        const pts = link.pts;
        if (pts && pts.length > 1) {
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }
        } else {
          ctx.moveTo(src.pos[0], src.pos[1]);
          ctx.lineTo(tgt.pos[0], tgt.pos[1]);
        }
        ctx.stroke();
      }

      // Nodes.
      for (const node of graph2d.graph.nodes) {
        const x = node.pos[0];
        const y = node.pos[1];
        const radius =
          node.type === 'room' ? 6 :
          node.type === 'door' ? 5 :
          node.type === 'corridor_entry' ? 4 : 3;
        const color =
          node.type === 'room' ? '#FF4500' :
          node.type === 'door' ? '#4CAF50' :
          node.type === 'corridor_entry' ? '#2196F3' :
          '#666';

        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();

        if (node.type === 'room' && node.room_name) {
          ctx.fillStyle = '#FF4500';
          ctx.font = '10px Courier New';
          ctx.fillText(node.room_name, x + 8, y + 4);
        }
      }
    };

    canvas.width = mw;
    canvas.height = mh;

    let cancelled = false;
    let img: HTMLImageElement | null = null;

    if (masterMaskUrl) {
      img = new Image();
      img.onload = () => {
        if (cancelled) return;
        ctx.drawImage(img as HTMLImageElement, 0, 0, mw, mh);
        drawGraph();
      };
      img.onerror = () => {
        if (cancelled) return;
        // No backdrop — fall back to a plain dark background.
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, mw, mh);
        drawGraph();
      };
      img.src = masterMaskUrl;
    } else {
      // No mask — draw the graph on a plain dark background (no crash).
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(0, 0, mw, mh);
      drawGraph();
    }

    return () => {
      cancelled = true;
      if (img) {
        img.onload = null;
        img.onerror = null;
      }
    };
  }, [graph2d, masterMaskUrl]);

  const meta = nav.graphMeta;

  return (
    <div className={wizardStyles.layout}>
      <div className={styles.body}>
        {/* Center — 2D nav-graph over the master схема backdrop */}
        <div className={styles.canvasPanel}>
          <div className={styles.gridBg} />
          <div className={styles.canvasBox}>
            {nav.isBuilding && (
              <div className={styles.loadingOverlay}>Строю граф…</div>
            )}
            {!graph2d && !nav.isBuilding && (
              <div className={styles.placeholder}>
                Нажмите «Построить граф навигации»
              </div>
            )}
            <canvas ref={canvasRef} className={styles.canvas} />
          </div>
        </div>

        {/* Right panel — build button + stats + legend */}
        <aside className={styles.panel}>
          <div className={styles.panelTitle}>НАВИГАЦИОННЫЙ ГРАФ</div>

          <button
            type="button"
            className={styles.buildBtn}
            onClick={() => void handleBuild()}
            disabled={floorId === null || nav.isBuilding}
          >
            {nav.isBuilding ? 'Строю граф…' : 'Построить граф навигации'}
          </button>

          {meta && (
            <div className={styles.statsGrid}>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{meta.nodes_count}</span>
                <span className={styles.statLabel}>Узлов</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{meta.edges_count}</span>
                <span className={styles.statLabel}>Рёбер</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{meta.rooms_count}</span>
                <span className={styles.statLabel}>Комнат</span>
              </div>
            </div>
          )}

          <div className={styles.legend}>
            <div className={styles.legendTitle}>ЛЕГЕНДА</div>
            <div className={styles.legendItem}>
              <span className={styles.dot} style={{ background: '#FF4500' }} />
              <span>Комната</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.dot} style={{ background: '#4CAF50' }} />
              <span>Дверь</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.dot} style={{ background: '#2196F3' }} />
              <span>Вход в коридор</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.dot} style={{ background: '#666' }} />
              <span>Узел коридора</span>
            </div>
          </div>
        </aside>
      </div>

      <footer className={wizardStyles.footer}>
        <button className={wizardStyles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={wizardStyles.footerHint} />
        <button className={wizardStyles.btnNext} onClick={onNext} type="button">
          Далее ▸
        </button>
      </footer>
    </div>
  );
};
