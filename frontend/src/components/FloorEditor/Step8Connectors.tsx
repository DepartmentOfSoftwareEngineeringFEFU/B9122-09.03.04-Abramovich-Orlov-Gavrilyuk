// Step 8 (+): on the master schema, either DRAW corridor connector walls
// or ERASE rectangular cutout zones, and optionally show the warped vector mask.
//
// Connector tool (two-click, mirrors WallEditorCanvas `wall`):
//  • Click 1 anchors the start; mouse-move previews a dashed line; click 2 commits
//    ONE segment {points:[start,end], thickness_m}; Esc cancels; Shift snaps to axis.
//  • Each segment extrudes into a wall (the floor mesh is walls-only).
//
// Cutout tool (drag a rectangle):
//  • Press anchors a corner; drag rubber-bands; release commits a 4-corner zone
//    {points} that ERASES walls (free for nav, no 3D wall). Esc cancels.
//
// Vector-mask toggle: overlays each ok section's warped wall mask (like Step 7) so
// the operator can place walls/cutouts against the real geometry.
//
// Presentational only — committed drafts live in useFloorAssembly; the in-progress
// connector anchor / cutout drag corner / cursor are local UI concerns kept here.

import React, { useRef, useEffect, useCallback, useState } from 'react';
import { fitContain } from './croppedImage';
import {
  toImageCoords,
  toDisplayCoords,
  type CanvasLayout,
} from '../controlPointCanvasCore';
import type { ConnectorDraft, CutoutDraft } from '../../hooks/useFloorAssembly';
import type {
  AssemblySection,
  SolveTransformsResponse,
} from '../../types/floorAssembly';
import wizardStyles from './WizardStep.module.css';
import styles from './Step8Connectors.module.css';

type Tool = 'connector' | 'cutout';

interface Step8ConnectorsProps {
  // Drawn on the cropped floor-schema mask (карта отсеков), so [0,1] coords
  // round-trip with the mesh builder (de-normalised over the cropped canvas).
  masterMaskUrl: string | null;
  connectorDrafts: ConnectorDraft[];
  isSaving: boolean;
  onChangeDrafts: (drafts: ConnectorDraft[]) => void;
  onSave: () => Promise<void>;
  onBack: () => void;
  onNext: () => void;
  /** Metric scale of the master schema — display hint only (optional). */
  pixelsPerMeter?: number | null;
  // --- cutouts + vector-mask overlay (this feature) ---
  cutoutDrafts: CutoutDraft[];
  onChangeCutouts: (drafts: CutoutDraft[]) => void;
  sections: AssemblySection[];
  solveResult: SolveTransformsResponse | null;
}

const BAND_COLOR = '#2563eb';
const DRAFT_COLOR = '#f05123';
const CUTOUT_FILL = 'rgba(34, 197, 94, 0.30)';
const CUTOUT_DRAG_FILL = 'rgba(34, 197, 94, 0.18)';
const CUTOUT_STROKE = 'rgba(22, 163, 74, 0.9)';
const VERTEX_R = 4;

/** Display multiplier: metres → preview band width in px on the (tiny) schema. */
const PX_PER_METRE = 36;
/** Default wall thickness in metres for new segments. */
const DEFAULT_THICKNESS_M = 0.3;

/** Preview band width in px for a given metric thickness (min 3 px to stay visible). */
const bandWidthPx = (thicknessM: number): number =>
  Math.max(3, thicknessM * PX_PER_METRE);

/** Two opposite corners → a clamped 4-point [0,1] rectangle polygon. */
export const rectToPolygon = (
  a: [number, number],
  b: [number, number],
): [number, number][] => {
  const cl = (v: number) => Math.min(1, Math.max(0, v));
  const x0 = cl(Math.min(a[0], b[0]));
  const y0 = cl(Math.min(a[1], b[1]));
  const x1 = cl(Math.max(a[0], b[0]));
  const y1 = cl(Math.max(a[1], b[1]));
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
};

export const Step8Connectors: React.FC<Step8ConnectorsProps> = ({
  masterMaskUrl,
  connectorDrafts,
  isSaving,
  onChangeDrafts,
  onSave,
  onBack,
  onNext,
  pixelsPerMeter,
  cutoutDrafts,
  onChangeCutouts,
  sections,
  solveResult,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  // Each ok section's wall mask, loaded once for the warped overlay (by section id).
  const sectionImgsRef = useRef<Map<number, HTMLImageElement>>(new Map());
  const layoutRef = useRef<CanvasLayout>({
    offsetX: 0,
    offsetY: 0,
    drawWidth: 0,
    drawHeight: 0,
  });

  const [tool, setTool] = useState<Tool>('connector');
  const [showMask, setShowMask] = useState(false);
  // Connector: first click anchors here. Cutout: drag corner anchors here.
  const [pendingStart, setPendingStart] = useState<[number, number] | null>(null);
  const [rectStart, setRectStart] = useState<[number, number] | null>(null);
  // Cursor position (normalised) for the live preview line / rubber-band.
  const [mouseNorm, setMouseNorm] = useState<[number, number] | null>(null);
  const [thicknessM, setThicknessM] = useState(DEFAULT_THICKNESS_M);

  // Refs mirror the latest state so the canvas draw + window listeners read them
  // synchronously without re-binding every render.
  const draftsRef = useRef(connectorDrafts);
  const cutoutDraftsRef = useRef(cutoutDrafts);
  const pendingStartRef = useRef(pendingStart);
  const rectStartRef = useRef(rectStart);
  const mouseNormRef = useRef(mouseNorm);
  const thicknessRef = useRef(thicknessM);
  const toolRef = useRef(tool);
  const showMaskRef = useRef(showMask);
  const sectionsRef = useRef(sections);
  const solveResultRef = useRef(solveResult);
  useEffect(() => {
    draftsRef.current = connectorDrafts;
  }, [connectorDrafts]);
  useEffect(() => {
    cutoutDraftsRef.current = cutoutDrafts;
  }, [cutoutDrafts]);
  useEffect(() => {
    pendingStartRef.current = pendingStart;
  }, [pendingStart]);
  useEffect(() => {
    rectStartRef.current = rectStart;
  }, [rectStart]);
  useEffect(() => {
    mouseNormRef.current = mouseNorm;
  }, [mouseNorm]);
  useEffect(() => {
    thicknessRef.current = thicknessM;
  }, [thicknessM]);
  useEffect(() => {
    toolRef.current = tool;
  }, [tool]);
  useEffect(() => {
    showMaskRef.current = showMask;
  }, [showMask]);
  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);
  useEffect(() => {
    solveResultRef.current = solveResult;
  }, [solveResult]);

  const computeLayout = useCallback((): CanvasLayout => {
    const container = containerRef.current;
    const img = imgRef.current;
    if (!container) return { offsetX: 0, offsetY: 0, drawWidth: 0, drawHeight: 0 };
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    // Size to the cropped floor mask, so [0,1] coords match the builder's canvas.
    const iw = img?.naturalWidth ?? cw;
    const ih = img?.naturalHeight ?? ch;
    const { dx, dy, dw, dh } = fitContain(iw, ih, cw, ch, 1);
    return { offsetX: dx, offsetY: dy, drawWidth: dw, drawHeight: dh };
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    if (cw <= 0 || ch <= 0) return;
    canvas.width = cw;
    canvas.height = ch;
    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cw, ch);

    const layout = computeLayout();
    layoutRef.current = layout;

    const img = imgRef.current;
    if (img && layout.drawWidth > 0) {
      ctx.save();
      ctx.filter = 'invert(1)'; // mask is white-on-black → black walls on white
      ctx.drawImage(
        img,
        layout.offsetX,
        layout.offsetY,
        layout.drawWidth,
        layout.drawHeight,
      );
      ctx.restore();
    }

    // Optional warped section-mask overlay (vector-mask toggle, like Step 7). The
    // setTransform maths folds (rx,ry)·scale·R(rotation_rad)·(kx,ky) + offset —
    // copied from Step7SolveTransforms so the walls land identically.
    const sr = solveResultRef.current;
    if (showMaskRef.current && sr && img && img.naturalWidth > 0) {
      const masterW = img.naturalWidth;
      const masterH = img.naturalHeight;
      const kx = layout.drawWidth / masterW;
      const ky = layout.drawHeight / masterH;
      for (const result of sr.sections) {
        if (result.status !== 'ok' || result.transform === null) continue;
        const section = sectionsRef.current.find(
          (s) => s.section_id === result.section_id,
        );
        if (!section) continue;
        const maskImg = sectionImgsRef.current.get(section.section_id);
        if (!maskImg || maskImg.naturalWidth <= 0 || maskImg.naturalHeight <= 0) {
          continue;
        }
        const [secW, secH] = section.image_size_cropped ?? [masterW, masterH];
        if (secW <= 0 || secH <= 0) continue;
        const { scale, tx, ty } = result.transform;
        const rot = result.transform.rotation_rad ?? 0;
        const cos = Math.cos(rot);
        const sin = Math.sin(rot);
        const iw = maskImg.naturalWidth;
        const ih = maskImg.naturalHeight;
        const rx = secW / iw;
        const ry = secH / ih;
        ctx.save();
        ctx.setTransform(
          kx * scale * cos * rx,
          ky * scale * sin * rx,
          -kx * scale * sin * ry,
          ky * scale * cos * ry,
          layout.offsetX + kx * tx,
          layout.offsetY + ky * ty,
        );
        ctx.globalAlpha = 0.55;
        ctx.filter = 'invert(1)';
        ctx.globalCompositeOperation = 'multiply';
        ctx.drawImage(maskImg, 0, 0, iw, ih);
        ctx.restore(); // resets transform / filter / composite / alpha
      }
    }

    // Render a polyline at a fixed band width. Handles 2 AND >2 points, so legacy
    // multi-vertex connectors still draw correctly.
    const drawPolyline = (
      pts: [number, number][],
      color: string,
      widthPx: number,
      dashed: boolean,
    ) => {
      if (pts.length === 0) return;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      if (pts.length >= 2) {
        ctx.beginPath();
        pts.forEach((p, i) => {
          const d = toDisplayCoords({ x: p[0], y: p[1] }, layout);
          if (i === 0) ctx.moveTo(d.x, d.y);
          else ctx.lineTo(d.x, d.y);
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = widthPx;
        ctx.globalAlpha = 0.6;
        if (dashed) ctx.setLineDash([6, 5]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.25;
        if (dashed) ctx.setLineDash([6, 5]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }
      pts.forEach((p) => {
        const d = toDisplayCoords({ x: p[0], y: p[1] }, layout);
        ctx.beginPath();
        ctx.arc(d.x, d.y, VERTEX_R, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      });
    };

    // Fill a closed polygon (cutout zone).
    const fillPolygon = (
      pts: [number, number][],
      fill: string,
      stroke: string,
      dashed: boolean,
    ) => {
      if (pts.length < 3) return;
      ctx.beginPath();
      pts.forEach((p, i) => {
        const d = toDisplayCoords({ x: p[0], y: p[1] }, layout);
        if (i === 0) ctx.moveTo(d.x, d.y);
        else ctx.lineTo(d.x, d.y);
      });
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1.5;
      if (dashed) ctx.setLineDash([6, 5]);
      ctx.stroke();
      ctx.setLineDash([]);
    };

    // Saved connector segments — each at ITS OWN thickness.
    draftsRef.current.forEach((conn) =>
      drawPolyline(conn.points, BAND_COLOR, bandWidthPx(conn.thickness_m), false),
    );

    // Saved cutout zones (green = erased wall area).
    cutoutDraftsRef.current.forEach((cut) =>
      fillPolygon(cut.points, CUTOUT_FILL, CUTOUT_STROKE, false),
    );

    // Connector preview line from the anchored start to the cursor.
    const start = pendingStartRef.current;
    const cursor = mouseNormRef.current;
    if (toolRef.current === 'connector' && start) {
      if (cursor) {
        drawPolyline([start, cursor], DRAFT_COLOR, bandWidthPx(thicknessRef.current), true);
      } else {
        const d = toDisplayCoords({ x: start[0], y: start[1] }, layout);
        ctx.beginPath();
        ctx.arc(d.x, d.y, VERTEX_R, 0, Math.PI * 2);
        ctx.fillStyle = DRAFT_COLOR;
        ctx.fill();
      }
    }

    // Cutout rubber-band rectangle while dragging.
    if (toolRef.current === 'cutout' && rectStartRef.current && cursor) {
      fillPolygon(
        rectToPolygon(rectStartRef.current, cursor),
        CUTOUT_DRAG_FILL,
        CUTOUT_STROKE,
        true,
      );
    }
  }, [computeLayout]);

  // Load the cropped floor-schema mask backdrop.
  useEffect(() => {
    if (!masterMaskUrl) {
      imgRef.current = null;
      draw();
      return;
    }
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      imgRef.current = img;
      draw();
    };
    img.onerror = () => {
      if (cancelled) return;
      imgRef.current = null;
      draw();
    };
    img.src = masterMaskUrl;
    return () => {
      cancelled = true;
    };
  }, [masterMaskUrl, draw]);

  // Load each ok section's wall mask once for the warped overlay (mirrors Step 7).
  useEffect(() => {
    if (solveResult === null) return;
    let cancelled = false;
    for (const result of solveResult.sections) {
      if (result.status !== 'ok') continue;
      const section = sections.find((s) => s.section_id === result.section_id);
      if (!section || !section.mask_url) continue;
      if (sectionImgsRef.current.has(section.section_id)) continue;
      const img = new Image();
      sectionImgsRef.current.set(section.section_id, img);
      img.onload = () => {
        if (!cancelled) draw();
      };
      img.src = section.mask_url;
    }
    return () => {
      cancelled = true;
    };
  }, [solveResult, sections, draw]);

  // Redraw on state change + resize.
  useEffect(() => {
    draw();
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => draw());
    observer.observe(el);
    return () => observer.disconnect();
  }, [
    draw,
    connectorDrafts,
    cutoutDrafts,
    pendingStart,
    rectStart,
    mouseNorm,
    thicknessM,
    tool,
    showMask,
    sections,
    solveResult,
  ]);

  const eventToNorm = useCallback(
    (event: React.MouseEvent<HTMLDivElement>): { x: number; y: number } | null => {
      const el = containerRef.current;
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return toImageCoords(
        event.clientX - rect.left,
        event.clientY - rect.top,
        layoutRef.current,
      );
    },
    [],
  );

  // --- mouse interactions --------------------------------------------------
  const handleMouseDown = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (event.button !== 0) return; // left only
      const norm = eventToNorm(event);
      if (!norm) return; // click outside the image — ignore

      // Cutout tool: anchor the drag corner (do NOT run the connector path).
      if (toolRef.current === 'cutout') {
        setRectStart([norm.x, norm.y]);
        setMouseNorm([norm.x, norm.y]);
        return;
      }

      const start = pendingStartRef.current;
      if (!start) {
        setPendingStart([norm.x, norm.y]);
        setMouseNorm([norm.x, norm.y]);
        return;
      }

      const dx = norm.x - start[0];
      const dy = norm.y - start[1];
      if (Math.hypot(dx, dy) < 1e-4) {
        setPendingStart(null);
        return;
      }

      let endX = norm.x;
      let endY = norm.y;
      if (event.shiftKey) {
        if (Math.abs(dx) >= Math.abs(dy)) endY = start[1];
        else endX = start[0];
      }

      onChangeDrafts([
        ...draftsRef.current,
        { points: [start, [endX, endY]], thickness_m: thicknessRef.current },
      ]);
      setPendingStart(null);
    },
    [eventToNorm, onChangeDrafts],
  );

  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const norm = eventToNorm(event);
      setMouseNorm(norm ? [norm.x, norm.y] : null);
    },
    [eventToNorm],
  );

  // Cutout tool: release commits the dragged rectangle (if it has area).
  const handleMouseUp = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (toolRef.current !== 'cutout') return;
      const start = rectStartRef.current;
      if (!start) return;
      const norm = eventToNorm(event);
      if (norm) {
        const poly = rectToPolygon(start, [norm.x, norm.y]);
        const w = poly[1][0] - poly[0][0];
        const h = poly[2][1] - poly[1][1];
        if (w > 1e-4 && h > 1e-4) {
          onChangeCutouts([...cutoutDraftsRef.current, { points: poly }]);
        }
      }
      setRectStart(null);
    },
    [eventToNorm, onChangeCutouts],
  );

  // Esc cancels the in-progress connector anchor / cutout drag.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPendingStart(null);
        setRectStart(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const selectTool = useCallback((next: Tool) => {
    setTool(next);
    setPendingStart(null);
    setRectStart(null);
  }, []);

  const deleteLine = useCallback(
    (index: number) => {
      onChangeDrafts(draftsRef.current.filter((_, i) => i !== index));
    },
    [onChangeDrafts],
  );

  const deleteCutout = useCallback(
    (index: number) => {
      onChangeCutouts(cutoutDraftsRef.current.filter((_, i) => i !== index));
    },
    [onChangeCutouts],
  );

  const ppmHint =
    pixelsPerMeter != null && pixelsPerMeter > 0
      ? `≈ ${(thicknessM * pixelsPerMeter).toFixed(0)} px на эталоне`
      : null;

  const maskToggleDisabled = solveResult === null;

  return (
    <div className={wizardStyles.layout}>
      <div className={styles.body}>
        {/* Center — master schema draw surface */}
        <div className={styles.canvasPanel}>
          <div
            className={styles.canvasWrap}
            ref={containerRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          >
            <canvas
              ref={canvasRef}
              style={{ width: '100%', height: '100%', display: 'block' }}
            />
            {!masterMaskUrl && (
              <div className={styles.canvasEmpty}>Нет карты отсеков</div>
            )}
          </div>
        </div>

        {/* Right panel — tool switch + per-tool controls + lists */}
        <aside className={styles.panel}>
          <div className={styles.panelTitle}>ПЕРЕХОДЫ И ВЫРЕЗЫ</div>

          <div className={styles.tools}>
            <button
              type="button"
              className={`${styles.toolBtn} ${
                tool === 'connector' ? styles.toolBtnActive : ''
              }`}
              onClick={() => selectTool('connector')}
            >
              Переход
            </button>
            <button
              type="button"
              className={`${styles.toolBtn} ${
                tool === 'cutout' ? styles.toolBtnActive : ''
              }`}
              onClick={() => selectTool('cutout')}
            >
              Вырез
            </button>
          </div>

          <label
            className={`${styles.toggleRow} ${
              maskToggleDisabled ? styles.disabled : ''
            }`}
          >
            <input
              type="checkbox"
              checked={showMask && !maskToggleDisabled}
              disabled={maskToggleDisabled}
              onChange={(e) => setShowMask(e.target.checked)}
            />
            Показать векторную маску
            {maskToggleDisabled && ' (сначала решите шаг 7)'}
          </label>

          {tool === 'connector' ? (
            <>
              <div className={styles.hint}>
                Клик — начало стены. Второй клик — конец стены. Shift — привязка к
                оси. Esc — отмена.
              </div>

              <div className={styles.paramRow}>
                <span className={styles.paramLabel}>Толщина стены</span>
                <input
                  className={styles.slider}
                  type="range"
                  min={0.1}
                  max={2.0}
                  step={0.05}
                  value={thicknessM}
                  onChange={(e) => setThicknessM(Number(e.target.value))}
                />
                <span className={styles.sliderValue}>{thicknessM.toFixed(2)} м</span>
              </div>
              {ppmHint && <div className={styles.paramHint}>{ppmHint}</div>}

              <div className={styles.connList}>
                {connectorDrafts.map((c, i) => (
                  <div key={c.id ?? `draft-${i}`} className={styles.connRow}>
                    <span className={styles.connDot} />
                    <span className={styles.connName}>
                      Линия {i + 1} · {c.thickness_m.toFixed(2)} м
                    </span>
                    <button
                      type="button"
                      className={styles.connDelete}
                      title="Удалить линию"
                      onClick={() => deleteLine(i)}
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {connectorDrafts.length === 0 && (
                  <div className={styles.emptyHint}>Нет переходов</div>
                )}
              </div>

              <button
                type="button"
                className={styles.saveBtn}
                onClick={() => void onSave()}
                disabled={isSaving}
              >
                Сохранить переходы
              </button>
            </>
          ) : (
            <>
              <div className={styles.hint}>
                Растяните прямоугольник — стена в этой зоне удаляется (нет стены в 3D,
                граф проходит насквозь). Перекрывайте обе соседние зоны, чтобы проём
                точно открылся. Esc — отмена.
              </div>

              <div className={styles.connList}>
                {cutoutDrafts.map((c, i) => (
                  <div key={c.id ?? `cutout-${i}`} className={styles.connRow}>
                    <span className={styles.cutoutDot} />
                    <span className={styles.connName}>Зона {i + 1}</span>
                    <button
                      type="button"
                      className={styles.connDelete}
                      title="Удалить зону"
                      onClick={() => deleteCutout(i)}
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {cutoutDrafts.length === 0 && (
                  <div className={styles.emptyHint}>Нет вырезов</div>
                )}
              </div>
            </>
          )}
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
