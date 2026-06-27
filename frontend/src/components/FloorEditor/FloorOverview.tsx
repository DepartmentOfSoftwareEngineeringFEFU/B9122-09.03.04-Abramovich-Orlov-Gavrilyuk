import React, { useRef, useEffect, useCallback, useState } from 'react';
import styles from './WizardStep.module.css';
import overviewStyles from './FloorOverview.module.css';
import { CanvasControls } from './CanvasControls';
import { SectionContextMenu } from './SectionContextMenu';
import { NewSectionDialog } from './NewSectionDialog';
import { getSectionColor } from './sectionColors';
import { reconstructionApi } from '../../api/apiService';
import type { SectionDraft, Point2D } from '../../hooks/useFloorEditorWizard';
import type { CropBbox } from '../../types/hierarchy';

interface ContextMenuState {
  x: number;
  y: number;
  sectionIdx: number;
}

interface FloorOverviewProps {
  schemaImageUrl: string | null;
  /** Id of the uploaded schema file — needed to refetch the binary mask from the
   * backend when no editedMaskUrl is present (e.g. after reopening the editor). */
  schemaImageId?: string | null;
  /** Crop bbox so the refetched mask matches the section coordinate system. */
  cropBbox?: CropBbox | null;
  /** Edited mask blob URL from Step 3/4. When present, shown as dark background. */
  editedMaskUrl?: string | null;
  wallPolygons: Point2D[][] | null;
  sectionDrafts: SectionDraft[];
  isDirty: boolean;
  isLoading: boolean;
  onUpdateSectionDraft: (idx: number, partial: Partial<SectionDraft>) => void;
  onDeleteSectionDraft: (idx: number) => void;
  onSave: () => Promise<void>;
  onClearAll?: () => Promise<void>;
  onSwitchToTable: () => void;
  onSwitchToWizard: () => void;
  /** Enter the floor-assembly steps (6–9): bind master control points → solve
   *  scale+shift → draw connectors → 3D preview + save. Jumps straight to step 6
   *  (no need to redo upload→crop→walls→sections→bind). */
  onStartAssembly: () => void;
}

export const FloorOverview: React.FC<FloorOverviewProps> = ({
  schemaImageUrl,
  schemaImageId,
  cropBbox,
  editedMaskUrl,
  wallPolygons: _wallPolygons,
  sectionDrafts,
  isDirty,
  isLoading,
  onUpdateSectionDraft,
  onDeleteSectionDraft,
  onSave,
  onClearAll,
  onSwitchToTable,
  onSwitchToWizard,
  onStartAssembly,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const maskImgRef = useRef<HTMLImageElement | null>(null);

  const [zoom, setZoom] = useState(1);
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameTargetIdx, setRenameTargetIdx] = useState<number | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  // Increment this to force re-render when localStorage colors change
  const [colorVersion, setColorVersion] = useState(0);

  const draftsRef = useRef(sectionDrafts);
  useEffect(() => { draftsRef.current = sectionDrafts; }, [sectionDrafts]);

  const getCanvasSize = useCallback(() => {
    const c = containerRef.current;
    return c ? { w: c.clientWidth, h: c.clientHeight } : { w: 800, h: 600 };
  }, []);

  const getImageParams = useCallback((imgW: number, imgH: number, cw: number, ch: number) => {
    const scale = Math.min((cw * zoom) / imgW, (ch * zoom) / imgH);
    const dw = imgW * scale;
    const dh = imgH * scale;
    const dx = (cw - dw) / 2;
    const dy = (ch - dh) / 2;
    return { dx, dy, dw, dh };
  }, [zoom]);

  const toCanvas = useCallback((nx: number, ny: number) => {
    // Section polygons are normalised against the CROPPED+ROTATED region (i.e.
    // the binary mask), not the raw uploaded photo. Always anchor to the mask
    // when available so polygons stay aligned with the visible walls.
    const img = maskImgRef.current ?? imageRef.current;
    const { w: cw, h: ch } = getCanvasSize();
    if (!img) {
      return { cx: nx * cw, cy: ny * ch };
    }
    const { dx, dy, dw, dh } = getImageParams(img.naturalWidth, img.naturalHeight, cw, ch);
    return { cx: dx + nx * dw, cy: dy + ny * dh };
  }, [getCanvasSize, getImageParams]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { w: cw, h: ch } = getCanvasSize();
    canvas.width = cw;
    canvas.height = ch;
    ctx.clearRect(0, 0, cw, ch);

    // White background — same as Step 5 final preview
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cw, ch);

    // Mask: inverted (black walls on white). Only render once the cropped mask
    // is loaded — falling back to the raw uploaded photo would give the wrong
    // aspect ratio (sections are normalised to the cropped region).
    const src = maskImgRef.current;
    if (src && src.naturalWidth > 0) {
      const { dx, dy, dw, dh } = getImageParams(src.naturalWidth, src.naturalHeight, cw, ch);
      ctx.save();
      ctx.filter = 'invert(1)';
      ctx.drawImage(src, dx, dy, dw, dh);
      ctx.restore();
    }

    // Sections — same look as Step 5: active = orange #F05123 @ 0.9, inactive = #f3f4f6
    for (let idx = 0; idx < draftsRef.current.length; idx++) {
      const draft = draftsRef.current[idx];
      const pts = draft.geometry.points;
      if (!pts || pts.length < 3) continue;
      const isActive = idx === activeIdx;

      ctx.fillStyle = isActive ? 'rgba(240, 81, 35, 0.9)' : '#f3f4f6';
      ctx.strokeStyle = '#d1d5db';
      ctx.lineWidth = 2;

      ctx.beginPath();
      const f = toCanvas(pts[0][0], pts[0][1]);
      ctx.moveTo(f.cx, f.cy);
      for (let i = 1; i < pts.length; i++) {
        const p = toCanvas(pts[i][0], pts[i][1]);
        ctx.lineTo(p.cx, p.cy);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Centered number label
      let avgX = 0, avgY = 0;
      for (const [px, py] of pts) { avgX += px; avgY += py; }
      avgX /= pts.length;
      avgY /= pts.length;
      const center = toCanvas(avgX, avgY);
      ctx.fillStyle = isActive ? '#ffffff' : '#6b7280';
      ctx.font = 'bold 16px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(draft.number), center.cx, center.cy);
    }
  }, [getCanvasSize, getImageParams, toCanvas, activeIdx, colorVersion]); // colorVersion forces redraw

  useEffect(() => { draw(); }, [draw, sectionDrafts, activeIdx]);

  const drawRef = useRef(draw);
  useEffect(() => { drawRef.current = draw; }, [draw]);

  // Keep the drawing buffer in sync with the displayed/container size. The
  // canvas has no CSS width/height, so its on-screen size equals the buffer
  // attributes set in draw() from the container's clientW/H. Without these
  // listeners the buffer goes stale on layout reflow (mask finishing load,
  // window resize) — a stale buffer offsets clicks from the drawn sections.
  useEffect(() => {
    const handleResize = () => drawRef.current();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => drawRef.current());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (schemaImageUrl) {
      const img = new Image();
      img.src = schemaImageUrl;
      img.onload = () => { imageRef.current = img; draw(); };
    }
    return () => { imageRef.current = null; };
  }, [schemaImageUrl, draw]);

  // Load the cropped+rotated binary mask. Prefer the in-session edited mask blob;
  // otherwise refetch from backend so coordinates match the section polygons
  // (which are normalised to the cropped region, not the raw uploaded photo).
  const cropKey = cropBbox
    ? `${cropBbox.x}|${cropBbox.y}|${cropBbox.width}|${cropBbox.height}|${cropBbox.rotation}`
    : '';
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    const loadFromUrl = (url: string) => {
      const img = new Image();
      img.onload = () => {
        if (cancelled) return;
        maskImgRef.current = img;
        draw();
      };
      img.onerror = () => {
        if (cancelled) return;
        maskImgRef.current = null;
        draw();
      };
      img.src = url;
    };

    if (editedMaskUrl) {
      loadFromUrl(editedMaskUrl);
      return () => { cancelled = true; };
    }

    if (schemaImageId) {
      const cropPayload = cropBbox
        ? { x: cropBbox.x, y: cropBbox.y, width: cropBbox.width, height: cropBbox.height }
        : null;
      const rotation = cropBbox?.rotation ?? 0;
      reconstructionApi
        .previewMask(schemaImageId, cropPayload, rotation)
        .then((url) => {
          if (cancelled) { URL.revokeObjectURL(url); return; }
          objectUrl = url;
          loadFromUrl(url);
        })
        .catch(() => {
          if (cancelled) return;
          maskImgRef.current = null;
          draw();
        });
      return () => {
        cancelled = true;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
      };
    }

    maskImgRef.current = null;
    draw();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editedMaskUrl, schemaImageId, cropKey]);

  // Hit test: find section under canvas coordinates
  const hitSection = useCallback((canvX: number, canvY: number): number | null => {
    for (let idx = 0; idx < draftsRef.current.length; idx++) {
      const pts = draftsRef.current[idx].geometry.points;
      const xs = pts.map((p) => toCanvas(p[0], p[1]).cx);
      const ys = pts.map((p) => toCanvas(p[0], p[1]).cy);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      if (canvX >= minX && canvX <= maxX && canvY >= minY && canvY <= maxY) {
        return idx;
      }
    }
    return null;
  }, [toCanvas]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const hit = hitSection(cx, cy);
    setActiveIdx(hit);
    setContextMenu(null);
  };

  const handleCanvasContextMenu = (e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const rect = canvasRef.current!.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const hit = hitSection(cx, cy);
    if (hit !== null) {
      setActiveIdx(hit);
      setContextMenu({ x: e.clientX, y: e.clientY, sectionIdx: hit });
    }
  };

  const handleRename = () => {
    if (contextMenu !== null) {
      setRenameTargetIdx(contextMenu.sectionIdx);
      setRenameDialogOpen(true);
    }
    setContextMenu(null);
  };

  const handleDelete = () => {
    if (contextMenu !== null) {
      const idx = contextMenu.sectionIdx;
      const section = sectionDrafts[idx];
      if (window.confirm(`Удалить отсек №${section.number}? Действие нельзя отменить без перезагрузки`)) {
        onDeleteSectionDraft(idx);
        setActiveIdx(null);
      }
    }
    setContextMenu(null);
  };

  const handleRenameConfirm = (num: number, _color: string) => {
    if (renameTargetIdx !== null) {
      onUpdateSectionDraft(renameTargetIdx, { number: num });
    }
    setRenameDialogOpen(false);
    setRenameTargetIdx(null);
  };

  const boundCount = sectionDrafts.filter((d) => d.reconstruction_id !== null).length;
  const takenNumbers = sectionDrafts
    .filter((_, i) => i !== renameTargetIdx)
    .map((d) => d.number);

  return (
    <div className={styles.layout}>
      {/* Top bar: title + view toggle */}
      <div className={overviewStyles.topBar}>
        <span className={overviewStyles.topBarTitle}>Итоговая схема этажа</span>
        <div className={overviewStyles.viewToggles}>
          <button
            className={`${overviewStyles.viewToggle} ${overviewStyles.viewToggleActive}`}
            type="button"
            disabled
            aria-current="true"
          >
            ▦ Схема
          </button>
          <button
            className={overviewStyles.viewToggle}
            onClick={onSwitchToTable}
            type="button"
          >
            ☰ Таблица
          </button>
        </div>
      </div>

      <div className={styles.body}>
        {/* Left: colored section list */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTitle}>Отсеки на схеме</div>
          <div className={styles.sectionList}>
            {sectionDrafts.map((d, idx) => {
              const color = getSectionColor(idx, d.id);
              return (
                <button
                  key={idx}
                  className={`${styles.sectionItem} ${idx === activeIdx ? styles.sectionItemActive : ''}`}
                  onClick={() => setActiveIdx(idx)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setActiveIdx(idx);
                    const rect = (e.target as HTMLElement).getBoundingClientRect();
                    setContextMenu({ x: rect.right, y: rect.top, sectionIdx: idx });
                  }}
                  type="button"
                >
                  <span
                    className={styles.sectionDot}
                    style={{
                      background: color,
                      borderRadius: '2px',
                    }}
                  />
                  {idx === activeIdx ? (
                    <span style={{ flex: 1 }}>Отсек {d.number}</span>
                  ) : (
                    <span style={{ flex: 1 }}>Отсек {d.number}</span>
                  )}
                  {d.reconstruction_id !== null && (
                    <span style={{ fontSize: '0.625rem', color: idx === activeIdx ? '#fff' : '#22c55e' }}>✓</span>
                  )}
                </button>
              );
            })}
          </div>
        </aside>

        {/* Canvas — light background */}
        <div className={styles.canvasArea} ref={containerRef}>
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            onClick={handleCanvasClick}
            onContextMenu={handleCanvasContextMenu}
            style={{ cursor: 'pointer' }}
          />
          <CanvasControls
            onZoomIn={() => setZoom((z) => Math.min(z + 0.25, 4))}
            onZoomOut={() => setZoom((z) => Math.max(z - 0.25, 0.25))}
            onReset={() => setZoom(1)}
          />
          {isLoading && (
            <div className={styles.spinnerOverlay}>
              <div className={styles.spinner} />
              <span className={styles.spinnerText}>Сохранение...</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <footer className={styles.footer} style={{ justifyContent: 'space-between', padding: '0.75rem 1.5rem' }}>
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <button className={styles.btnBack} onClick={onSwitchToWizard} type="button">
            ← Назад
          </button>
          <div className={styles.statsRow}>
            <span className={styles.statItem}>
              Всего отсеков: <strong className={styles.statValue}>{sectionDrafts.length}</strong>
            </span>
            <span className={styles.statItem}>
              Привязано: <strong className={styles.statValue}>{boundCount}</strong>
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <button
            className={`${styles.btnBack} ${styles.btnDanger}`}
            style={{ color: '#ef4444', borderColor: '#ef4444' }}
            onClick={() => setDeleteModalOpen(true)}
            type="button"
          >
            Удалить карту отсеков
          </button>
          <button
            className={styles.btnSave}
            onClick={() => void onSave()}
            disabled={isLoading || !isDirty}
            type="button"
          >
            Сохранить изменения
          </button>
          <button
            className={styles.btnSave}
            style={{ background: '#F05123', borderColor: '#F05123', color: '#ffffff' }}
            onClick={onStartAssembly}
            disabled={boundCount === 0}
            title={
              boundCount === 0
                ? 'Сначала привяжите планы к отсекам'
                : 'Контрольные точки → решение (масштаб+сдвиг) → 3D-модель этажа'
            }
            type="button"
          >
            Собрать 3D-этаж →
          </button>
        </div>
      </footer>

      {/* Context menu */}
      {contextMenu && (
        <SectionContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          sectionNumber={sectionDrafts[contextMenu.sectionIdx]?.number ?? 0}
          sectionId={sectionDrafts[contextMenu.sectionIdx]?.id}
          sectionIdx={contextMenu.sectionIdx}
          onRename={handleRename}
          onDelete={handleDelete}
          onColorChange={() => setColorVersion((v) => v + 1)}
          onClose={() => setContextMenu(null)}
        />
      )}

      {/* Rename dialog */}
      <NewSectionDialog
        open={renameDialogOpen}
        initialNumber={renameTargetIdx !== null ? sectionDrafts[renameTargetIdx]?.number ?? null : null}
        takenNumbers={takenNumbers}
        onConfirm={handleRenameConfirm}
        onCancel={() => { setRenameDialogOpen(false); setRenameTargetIdx(null); }}
      />

      {/* Delete Confirmation Modal */}
      {deleteModalOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,23,42,0.4)', backdropFilter: 'blur(4px)' }} onClick={() => setDeleteModalOpen(false)}>
          <div style={{ background: '#fff', padding: '2rem', maxWidth: '420px', width: '100%', borderRadius: '0', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1.25rem', fontWeight: 600, color: '#0f172a' }}>Удалить карту отсеков?</h3>
            <p style={{ margin: '0 0 2rem', fontSize: '0.9375rem', color: '#64748b', lineHeight: 1.5 }}>
              Будут удалены отсеки и их привязки, а также сама карта отсеков: загруженная схема этажа, кадрирование, стены и маска. Вы вернётесь к шагу загрузки, чтобы загрузить новую карту отсеков. Действие нельзя отменить.
            </p>
            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className={styles.btnBack}
                style={{ borderRadius: '0', background: '#ffffff', color: '#374151', border: '1px solid #d1d5db', padding: '0.625rem 1.25rem' }}
                onClick={() => setDeleteModalOpen(false)}
              >
                Отмена
              </button>
              <button
                type="button"
                className={`${styles.btnBack} ${styles.btnDanger}`}
                style={{ borderRadius: '0', background: '#ef4444', color: '#ffffff', border: 'none', padding: '0.625rem 1.25rem' }}
                onClick={() => {
                  setDeleteModalOpen(false);
                  if (onClearAll) {
                    void onClearAll();
                  } else {
                    for (let i = sectionDrafts.length - 1; i >= 0; i--) {
                      onDeleteSectionDraft(i);
                    }
                  }
                }}
              >
                Удалить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
