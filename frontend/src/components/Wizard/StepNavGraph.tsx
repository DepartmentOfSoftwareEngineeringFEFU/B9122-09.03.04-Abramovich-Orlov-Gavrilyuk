import React, { useEffect, useRef, useState } from 'react';
import { reconstructionApi } from '../../api/apiService';
import styles from './StepNavGraph.module.css';

interface NavNode {
  id: string | number;
  type: string;
  pos: [number, number];
  room_name?: string;
}

interface NavLink {
  source: string | number;
  target: string | number;
  type: string;
  pts?: [number, number][];
}

interface NavGraphData {
  metadata: {
    nodes_count: number;
    edges_count: number;
    room_nodes: string[];
    door_nodes: string[];
    mask_width: number;
    mask_height: number;
  };
  graph: {
    nodes: NavNode[];
    edges: NavLink[];
  };
}

interface StepNavGraphProps {
  navGraphId: string | null;
  maskUrl: string;
}

export const StepNavGraph: React.FC<StepNavGraphProps> = ({ navGraphId, maskUrl }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [graphData, setGraphData] = useState<NavGraphData | null>(null);
  const [stats, setStats] = useState({ nodes: 0, edges: 0, rooms: 0, doors: 0 });
  const [isLoading, setIsLoading] = useState(false);

  const loadAndDraw = (id: string) => {
    setIsLoading(true);
    reconstructionApi.getNavGraph(id).then((data: NavGraphData) => {
      setGraphData(data);
      setStats({
        nodes: data.metadata.nodes_count,
        edges: data.metadata.edges_count,
        rooms: data.metadata.room_nodes.length,
        doors: data.metadata.door_nodes.length,
      });
      setIsLoading(false);
    }).catch(() => setIsLoading(false));
  };

  useEffect(() => {
    if (!navGraphId) return;
    loadAndDraw(navGraphId);
  }, [navGraphId]);

  useEffect(() => {
    if (!canvasRef.current || !graphData) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const mw = graphData.metadata.mask_width;
    const mh = graphData.metadata.mask_height;

    const img = new Image();
    img.onload = () => {
      // Set canvas intrinsic size to image dimensions to prevent aspect ratio distortion
      // CSS object-fit: contain will handle visual scaling correctly
      canvas.width = mw;
      canvas.height = mh;
      const scaleX = 1;
      const scaleY = 1;

      ctx.drawImage(img, 0, 0, mw, mh);

      const nodeMap = new Map<string | number, NavNode>();
      for (const node of graphData.graph.nodes) nodeMap.set(node.id, node);

      // Draw edges
      for (const link of graphData.graph.edges) {
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
          ctx.moveTo(pts[0][0] * scaleX, pts[0][1] * scaleY);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0] * scaleX, pts[i][1] * scaleY);
          }
        } else {
          ctx.moveTo(src.pos[0] * scaleX, src.pos[1] * scaleY);
          ctx.lineTo(tgt.pos[0] * scaleX, tgt.pos[1] * scaleY);
        }
        ctx.stroke();
      }

      // Draw nodes
      for (const node of graphData.graph.nodes) {
        const x = node.pos[0] * scaleX;
        const y = node.pos[1] * scaleY;
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
    img.src = maskUrl;
  }, [graphData, maskUrl]);

  const handleRebuild = () => {
    if (navGraphId) loadAndDraw(navGraphId);
  };

  return (
    <div className={styles.step}>
      <div className={styles.canvasArea}>
        <div className={styles.gridBg} />
        <div className={styles.canvasBox}>
          {isLoading && <div className={styles.loadingOverlay}>Загрузка графа...</div>}
          <canvas ref={canvasRef} className={styles.canvas} />
        </div>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelInner}>
          <div>
            <div className={styles.sectionTitle}>// НАВИГАЦИОННЫЙ ГРАФ</div>
            <div className={styles.statsGrid}>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.nodes}</span>
                <span className={styles.statLabel}>Узлов</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.edges}</span>
                <span className={styles.statLabel}>Рёбер</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.rooms}</span>
                <span className={styles.statLabel}>Комнат</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.doors}</span>
                <span className={styles.statLabel}>Дверей</span>
              </div>
            </div>
          </div>

          <div className={styles.divider} />

          <div>
            <div className={styles.sectionTitle}>// ЛЕГЕНДА</div>
            <div className={styles.legendSection}>
              <div className={styles.legendItem}>
                <span className={styles.dot} style={{ background: '#666' }} />
                <span>Узел коридора</span>
              </div>
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
            </div>
          </div>

          <div className={styles.divider} />

          <div>
            <div className={styles.sectionTitle}>// ДЕЙСТВИЯ</div>
            <div className={styles.actionsSection}>
              <button className={styles.actionBtn} onClick={handleRebuild}>
                Перестроить граф
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
