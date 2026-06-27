// Step 7: solve every bound section's uniform similarity transform and
// review the result. "Решить" runs POST /solve-transforms; each section then
// shows a status chip (green ok / amber ok+warning / red needs_points / red
// degenerate) with its registration residual in METRES, and every ok section's
// warped footprint is overlaid on the master schema in its section colour so the
// operator can eyeball the registration before building.
//
// Residual in metres = transform.residual_rms_px / pixels_per_meter (both from
// the SolveTransformsResponse). pixels_per_meter null/0 → "—" (never NaN/∞).
//
// Presentational only — solve state/actions live in useFloorAssembly.

import React, { useRef, useEffect, useCallback } from 'react';
import { getSectionColor } from './sectionColors';
import { fitContain } from './croppedImage';
import type {
  AssemblySection,
  SolveSectionResult,
  SolveTransformsResponse,
} from '../../types/floorAssembly';
import wizardStyles from './WizardStep.module.css';
import styles from './Step7SolveTransforms.module.css';

interface Step7SolveTransformsProps {
  sections: AssemblySection[];
  // Cropped floor-schema mask (карта отсеков) — the frame the transforms map into.
  masterMaskUrl: string | null;
  solveResult: SolveTransformsResponse | null;
  isSolving: boolean;
  onSolve: () => Promise<void>;
  onBack: () => void;
  onNext: () => void;
}

type ChipKind = 'ok' | 'warning' | 'error';

const STATUS_LABEL: Record<SolveSectionResult['status'], string> = {
  ok: 'OK',
  needs_points: 'Мало точек',
  degenerate: 'Вырождено',
};

const chipKindFor = (r: SolveSectionResult): ChipKind => {
  if (r.status !== 'ok') return 'error';
  return r.warning ? 'warning' : 'ok';
};

/**
 * Residual in metres, guarded. Returns "—" when no transform or ppm is null/0
 * (never NaN/∞). Pure helper kept local to the step (display-only).
 */
export const residualMetres = (
  r: SolveSectionResult,
  pixelsPerMeter: number | null,
): string => {
  if (r.transform === null) return '—';
  if (pixelsPerMeter === null || pixelsPerMeter <= 0) return '—';
  const metres = r.transform.residual_rms_px / pixelsPerMeter;
  if (!Number.isFinite(metres)) return '—';
  return `${metres.toFixed(3)} м`;
};

export const Step7SolveTransforms: React.FC<Step7SolveTransformsProps> = ({
  sections,
  masterMaskUrl,
  solveResult,
  isSolving,
  onSolve,
  onBack,
  onNext,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  // Each ok section's wall mask, loaded once for the warped semi-transparent
  // overlay (keyed by section id).
  const sectionImgsRef = useRef<Map<number, HTMLImageElement>>(new Map());

  const sectionIndexById = new Map<number, number>();
  sections.forEach((s, i) => sectionIndexById.set(s.section_id, i));

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

    // The cropped floor mask is the frame the transforms map into (master px).
    const img = imgRef.current;
    const masterW = img?.naturalWidth ?? 0;
    const masterH = img?.naturalHeight ?? 0;
    if (!img || masterW <= 0 || masterH <= 0) return;

    const { dx, dy, dw, dh } = fitContain(masterW, masterH, cw, ch, 1);
    ctx.save();
    ctx.filter = 'invert(1)'; // mask is white-on-black → show black walls on white
    ctx.drawImage(img, dx, dy, dw, dh);
    ctx.restore();

    if (solveResult === null) return;

    const kx = dw / masterW; // master-px → canvas-px scale (x)
    const ky = dh / masterH; // master-px → canvas-px scale (y)

    for (const result of solveResult.sections) {
      if (result.status !== 'ok' || result.transform === null) continue;
      const section = sections.find((s) => s.section_id === result.section_id);
      if (!section) continue;
      const [secW, secH] = section.image_size_cropped ?? [masterW, masterH];
      if (secW <= 0 || secH <= 0) continue;

      const { scale, tx, ty } = result.transform;
      // Apply the FULL solved similarity scale·R(rotation_rad) + translation so
      // the footprint shows the TRUE placement — size AND tilt — exactly like the
      // 3D build. rotation_rad defaults to 0 for legacy transforms.
      const rot = result.transform.rotation_rad ?? 0;
      const cos = Math.cos(rot);
      const sin = Math.sin(rot);
      const idx = sectionIndexById.get(section.section_id) ?? 0;
      const color = getSectionColor(idx, section.section_id);

      // section-px (sxp, syp) → canvas-px under the rotated similarity.
      const toCanvas = (sxp: number, syp: number): [number, number] => {
        const mpx = scale * (cos * sxp - sin * syp) + tx; // master px
        const mpy = scale * (sin * sxp + cos * syp) + ty;
        return [dx + kx * mpx, dy + ky * mpy];
      };

      // Overlay the section's OWN wall mask, warped by the SAME similarity, so the
      // operator sees the real walls land on the карта отсеков (not just a box).
      // invert+multiply paints the white-on-black mask as dark walls over the
      // white backdrop — only walls show; the black background stays transparent.
      const maskImg = sectionImgsRef.current.get(section.section_id);
      if (maskImg && maskImg.naturalWidth > 0 && maskImg.naturalHeight > 0) {
        const iw = maskImg.naturalWidth;
        const ih = maskImg.naturalHeight;
        const rx = secW / iw; // image-px → section-px (≈ 1)
        const ry = secH / ih;
        ctx.save();
        // image-px (ix, iy) → canvas-px: folds (rx,ry) · scale·R · (kx,ky) + offset.
        ctx.setTransform(
          kx * scale * cos * rx,
          ky * scale * sin * rx,
          -kx * scale * sin * ry,
          ky * scale * cos * ry,
          dx + kx * tx,
          dy + ky * ty,
        );
        ctx.globalAlpha = 0.55;
        ctx.filter = 'invert(1)';
        ctx.globalCompositeOperation = 'multiply';
        ctx.drawImage(maskImg, 0, 0, iw, ih);
        ctx.restore(); // back to identity transform / no filter / source-over
      }

      // Coloured rotated footprint: a light identity tint + the outline.
      ctx.beginPath();
      (
        [
          [0, 0],
          [secW, 0],
          [secW, secH],
          [0, secH],
        ] as [number, number][]
      ).forEach(([px, py], i) => {
        const [cx, cy] = toCanvas(px, py);
        if (i === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      });
      ctx.closePath();
      ctx.globalAlpha = 0.08;
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }, [solveResult, sections]);

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

  // Load each ok section's wall mask once (for the warped semi-transparent
  // overlay). Stored in a ref keyed by section id; redraw as each image arrives.
  useEffect(() => {
    if (solveResult === null) return;
    let cancelled = false;
    for (const result of solveResult.sections) {
      if (result.status !== 'ok') continue;
      const section = sections.find((s) => s.section_id === result.section_id);
      if (!section || !section.mask_url) continue;
      if (sectionImgsRef.current.has(section.section_id)) continue;
      const img = new Image();
      // Reserve immediately so a re-render does not re-request the same mask.
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

  // Redraw on overlay/solve change + on resize.
  useEffect(() => {
    draw();
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => draw());
    observer.observe(el);
    return () => observer.disconnect();
  }, [draw]);

  const resultById = new Map<number, SolveSectionResult>();
  solveResult?.sections.forEach((r) => resultById.set(r.section_id, r));
  const boundSections = sections.filter((s) => s.reconstruction_id !== null);
  const ppm = solveResult?.pixels_per_meter ?? null;
  const okCount = solveResult
    ? solveResult.sections.filter((s) => s.status === 'ok').length
    : 0;

  return (
    <div className={wizardStyles.layout}>
      <div className={styles.body}>
        {/* Center — master schema with warped overlays */}
        <div className={styles.canvasPanel}>
          <div className={styles.canvasWrap} ref={containerRef}>
            <canvas
              ref={canvasRef}
              style={{ width: '100%', height: '100%', display: 'block' }}
            />
            {!masterMaskUrl && (
              <div className={styles.canvasEmpty}>Нет карты отсеков</div>
            )}
          </div>
        </div>

        {/* Right panel — solve button + per-section status chips */}
        <aside className={styles.panel}>
          <div className={styles.panelTitle}>РЕШЕНИЕ</div>
          <button
            type="button"
            className={styles.solveBtn}
            onClick={() => void onSolve()}
            disabled={isSolving}
          >
            {isSolving ? 'Расчёт…' : 'Рассчитать преобразования'}
          </button>

          {solveResult && (
            <div className={styles.ppmRow}>
              <span className={styles.ppmLabel}>px / м</span>
              <span className={styles.ppmValue}>
                {ppm !== null && ppm > 0 ? ppm.toFixed(1) : '—'}
              </span>
            </div>
          )}

          <div className={styles.chipList}>
            {boundSections.map((s) => {
              const result = resultById.get(s.section_id);
              const idx = sectionIndexById.get(s.section_id) ?? 0;
              const color = getSectionColor(idx, s.section_id);
              if (!result) {
                return (
                  <div key={s.section_id} className={styles.chipRow}>
                    <span
                      className={styles.chipDot}
                      style={{ background: color }}
                    />
                    <span className={styles.chipName}>Отсек {s.number}</span>
                    <span className={styles.chipPending}>—</span>
                  </div>
                );
              }
              const kind = chipKindFor(result);
              return (
                <div key={s.section_id} className={styles.chipRow}>
                  <span
                    className={styles.chipDot}
                    style={{ background: color }}
                  />
                  <span className={styles.chipName}>Отсек {s.number}</span>
                  <span className={`${styles.chip} ${styles[`chip_${kind}`]}`}>
                    {STATUS_LABEL[result.status]}
                  </span>
                  <span className={styles.chipResidual}>
                    {residualMetres(result, ppm)}
                  </span>
                  {result.warning && (
                    <div className={styles.chipWarning}>{result.warning}</div>
                  )}
                </div>
              );
            })}
            {boundSections.length === 0 && (
              <div className={styles.emptyHint}>Нет отсеков с планами</div>
            )}
          </div>
        </aside>
      </div>

      <footer className={wizardStyles.footer}>
        <button className={wizardStyles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={wizardStyles.footerHint}>
          {solveResult ? `${okCount} отсек(ов) готово к сборке` : ''}
        </span>
        <button
          className={wizardStyles.btnNext}
          onClick={onNext}
          type="button"
          disabled={okCount === 0}
        >
          Далее ▸
        </button>
      </footer>
    </div>
  );
};
