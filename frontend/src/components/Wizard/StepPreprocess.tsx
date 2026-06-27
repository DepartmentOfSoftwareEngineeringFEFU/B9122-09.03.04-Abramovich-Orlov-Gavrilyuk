import React, { useEffect, useRef, useState } from 'react';
import { Crop, RotateCw } from 'lucide-react';
import { ToolPanelV2 } from '../Editor/ToolPanelV2';
import { CropOverlay } from '../Editor/CropOverlay';
import type { CropRect } from '../../types/wizard';
import styles from './StepPreprocess.module.css';

interface StepPreprocessProps {
  planUrl: string;
  cropRect: CropRect | null;
  rotation: 0 | 90 | 180 | 270;
  onCropChange: (rect: CropRect) => void;
  onRotate: () => void;
}

const DEFAULT_CROP: CropRect = { x: 0.05, y: 0.05, width: 0.9, height: 0.9 };

const SECTIONS = [
  {
    title: '// ПРЕПРОЦЕССИНГ',
    tools: [
      { id: 'crop', label: 'Кадрирование', icon: <Crop size={20} /> },
      { id: 'rotate', label: 'Повернуть 90°', icon: <RotateCw size={20} /> },
    ],
  },
];

export const StepPreprocess: React.FC<StepPreprocessProps> = ({
  planUrl,
  cropRect,
  rotation,
  onCropChange,
  onRotate,
}) => {
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [autoRotated, setAutoRotated] = useState(false);
  const [displayUrl, setDisplayUrl] = useState(planUrl);
  const imageRef = useRef<HTMLImageElement>(null);

  const effectiveCrop = cropRect ?? DEFAULT_CROP;

  useEffect(() => {
    if (rotation === 0) { setDisplayUrl(planUrl); return; }
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const swap = rotation === 90 || rotation === 270;
      canvas.width = swap ? img.height : img.width;
      canvas.height = swap ? img.width : img.height;
      const ctx = canvas.getContext('2d')!;
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate((rotation * Math.PI) / 180);
      ctx.drawImage(img, -img.width / 2, -img.height / 2);
      setDisplayUrl(canvas.toDataURL());
    };
    img.src = planUrl;
  }, [planUrl, rotation]);

  useEffect(() => {
    const img = imageRef.current;
    if (!img) return;

    const checkOrientation = () => {
      if (img.naturalHeight > img.naturalWidth && rotation === 0) {
        onRotate();
        setAutoRotated(true);
      }
    };

    if (img.complete) {
      checkOrientation();
    } else {
      img.addEventListener('load', checkOrientation, { once: true });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToolChange = (id: string) => {
    if (id === 'rotate') {
      onRotate();
      return;
    }
    setActiveTool((prev) => (prev === id ? null : id));
  };

  return (
    <div className={styles.step}>
      <div className={styles.canvasArea}>
        <div className={styles.gridBg} />

        <div className={styles.imageWrapper}>
          <img
            ref={imageRef}
            src={displayUrl}
            alt="План"
            className={styles.planImage}
          />
          {activeTool === 'crop' && (
            <CropOverlay
              imageRef={imageRef}
              cropRect={effectiveCrop}
              onChange={onCropChange}
            />
          )}
        </div>

        {autoRotated && (
          <div className={styles.notice}>
            // ИЗОБРАЖЕНИЕ АВТОМАТИЧЕСКИ ПОВЁРНУТО
          </div>
        )}
      </div>

      <ToolPanelV2
        sections={SECTIONS}
        activeTool={activeTool}
        onToolChange={handleToolChange}
      />
    </div>
  );
};
