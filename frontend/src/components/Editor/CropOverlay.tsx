import React, { useEffect, useRef, useCallback } from 'react';
import type { CropRect } from '../../types/wizard';
import styles from './CropOverlay.module.css';

interface CropOverlayProps {
  imageRef: React.RefObject<HTMLImageElement>;
  cropRect: CropRect;
  onChange: (rect: CropRect) => void;
}

export function normalizeCropRect(
  pixelRect: { x: number; y: number; width: number; height: number },
  imageWidth: number,
  imageHeight: number,
): CropRect {
  return {
    x: pixelRect.x / imageWidth,
    y: pixelRect.y / imageHeight,
    width: pixelRect.width / imageWidth,
    height: pixelRect.height / imageHeight,
  };
}

export function clampCropRect(rect: CropRect, minSize = 0.1): CropRect {
  const width = Math.max(minSize, Math.min(rect.width, 1));
  const height = Math.max(minSize, Math.min(rect.height, 1));
  const x = Math.max(0, Math.min(rect.x, 1 - width));
  const y = Math.max(0, Math.min(rect.y, 1 - height));
  return { x, y, width, height };
}

type Corner = 'tl' | 'tr' | 'bl' | 'br';

export const CropOverlay: React.FC<CropOverlayProps> = ({ imageRef, cropRect, onChange }) => {
  const dragStateRef = useRef<{
    type: 'corner' | 'interior';
    corner?: Corner;
    startMouseX: number;
    startMouseY: number;
    startRect: CropRect;
  } | null>(null);

  const getImageBounds = useCallback(() => {
    const img = imageRef.current;
    if (!img) return null;
    return img.getBoundingClientRect();
  }, [imageRef]);

  const toPixel = useCallback(
    (norm: CropRect, bounds: DOMRect) => ({
      x: norm.x * bounds.width,
      y: norm.y * bounds.height,
      width: norm.width * bounds.width,
      height: norm.height * bounds.height,
    }),
    [],
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      const drag = dragStateRef.current;
      if (!drag) return;
      const bounds = getImageBounds();
      if (!bounds) return;

      const dx = e.clientX - drag.startMouseX;
      const dy = e.clientY - drag.startMouseY;
      const dxN = dx / bounds.width;
      const dyN = dy / bounds.height;

      const s = drag.startRect;
      let next: CropRect;

      if (drag.type === 'interior') {
        next = clampCropRect({ x: s.x + dxN, y: s.y + dyN, width: s.width, height: s.height });
      } else {
        const c = drag.corner!;
        let { x, y, width, height } = s;

        if (c === 'tl') {
          x = s.x + dxN;
          y = s.y + dyN;
          width = s.width - dxN;
          height = s.height - dyN;
        } else if (c === 'tr') {
          y = s.y + dyN;
          width = s.width + dxN;
          height = s.height - dyN;
        } else if (c === 'bl') {
          x = s.x + dxN;
          width = s.width - dxN;
          height = s.height + dyN;
        } else {
          // br
          width = s.width + dxN;
          height = s.height + dyN;
        }
        next = clampCropRect({ x, y, width, height });
      }

      onChange(next);
    },
    [getImageBounds, onChange],
  );

  const handleMouseUp = useCallback(() => {
    dragStateRef.current = null;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  }, [handleMouseMove]);

  const startDrag = useCallback(
    (e: React.MouseEvent, type: 'corner' | 'interior', corner?: Corner) => {
      e.preventDefault();
      e.stopPropagation();
      dragStateRef.current = {
        type,
        corner,
        startMouseX: e.clientX,
        startMouseY: e.clientY,
        startRect: { ...cropRect },
      };
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [cropRect, handleMouseMove, handleMouseUp],
  );

  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const bounds = getImageBounds();
  if (!bounds) return null;

  const px = toPixel(cropRect, bounds);
  // Position relative to the overlay container (which is inset:0 over the image)
  const left = px.x;
  const top = px.y;
  const width = px.width;
  const height = px.height;

  return (
    <div className={styles.overlay}>
      {/* Dim strips */}
      <div
        className={styles.dimTop}
        style={{ left: 0, top: 0, right: 0, height: top }}
      />
      <div
        className={styles.dimBottom}
        style={{ left: 0, top: top + height, right: 0, bottom: 0 }}
      />
      <div
        className={styles.dimLeft}
        style={{ left: 0, top, width: left, height }}
      />
      <div
        className={styles.dimRight}
        style={{ left: left + width, top, right: 0, height }}
      />

      {/* Crop rect */}
      <div
        className={styles.cropRect}
        style={{ left, top, width, height }}
      >
        {/* Interior drag */}
        <div
          className={styles.interior}
          onMouseDown={(e) => startDrag(e, 'interior')}
        />
        {/* Corner handles */}
        <div
          className={styles.handle}
          style={{ top: -6, left: -6 }}
          onMouseDown={(e) => startDrag(e, 'corner', 'tl')}
        />
        <div
          className={styles.handle}
          style={{ top: -6, right: -6 }}
          onMouseDown={(e) => startDrag(e, 'corner', 'tr')}
        />
        <div
          className={styles.handle}
          style={{ bottom: -6, left: -6 }}
          onMouseDown={(e) => startDrag(e, 'corner', 'bl')}
        />
        <div
          className={styles.handle}
          style={{ bottom: -6, right: -6 }}
          onMouseDown={(e) => startDrag(e, 'corner', 'br')}
        />
      </div>
    </div>
  );
};
