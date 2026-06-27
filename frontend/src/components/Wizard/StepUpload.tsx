import React, { useState, useEffect, useRef } from 'react';
import { DropZone } from '../Upload/DropZone';
import { BuildingFloorPicker } from '../Upload/BuildingFloorPicker';
import type { UploadedFile } from '../../types/wizard';
import styles from './StepUpload.module.css';

interface StepUploadProps {
  files: UploadedFile[];
  onFilesSelect: (files: File[]) => void;
  onRemove: (id: string) => void;
  isUploading: boolean;
  selectedBuildingId: number | null;
  selectedFloorId: number | null;
  planName: string;
  onPlanNameChange: (name: string) => void;
  onFloorChange: (data: { buildingId: number | null; floorId: number | null }) => void;
}

function useRotatedUrl(url: string | undefined): string | undefined {
  const [rotatedUrl, setRotatedUrl] = useState<string | undefined>(url);
  const prevUrlRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!url) { setRotatedUrl(undefined); return; }
    if (url === prevUrlRef.current) return;
    prevUrlRef.current = url;

    const img = new Image();
    img.onload = () => {
      if (img.naturalHeight > img.naturalWidth) {
        const c = document.createElement('canvas');
        c.width = img.naturalHeight;
        c.height = img.naturalWidth;
        const ctx = c.getContext('2d')!;
        ctx.translate(c.width / 2, c.height / 2);
        ctx.rotate(Math.PI / 2);
        ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2);
        setRotatedUrl(c.toDataURL());
      } else {
        setRotatedUrl(url);
      }
    };
    img.src = url;
  }, [url]);

  return rotatedUrl;
}

export const StepUpload: React.FC<StepUploadProps> = ({
  files,
  onFilesSelect,
  onRemove,
  isUploading,
  selectedBuildingId,
  selectedFloorId,
  planName,
  onPlanNameChange,
  onFloorChange,
}) => {
  const [activeIndex, setActiveIndex] = useState(0);

  const safeIndex = Math.min(activeIndex, Math.max(0, files.length - 1));
  const activeFile = files[safeIndex] ?? null;
  const rotatedPreviewUrl = useRotatedUrl(activeFile?.url);

  return (
    <div className={styles.step}>
      {/* Left panel */}
      <div className={styles.left}>
        <div className={styles.dropZoneWrap}>
          <DropZone onFilesSelect={onFilesSelect} isUploading={isUploading} />
        </div>

        {files.length > 1 && (
          <div className={styles.thumbnailStrip}>
            {files.map((f, i) => (
              <div
                key={f.id}
                className={`${styles.thumb} ${i === safeIndex ? styles.thumbActive : ''}`}
                onClick={() => setActiveIndex(i)}
              >
                <img src={f.url} alt={f.name} className={styles.thumbImg} />
                <p className={styles.thumbName}>{f.name}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Right panel */}
      <div className={styles.right}>
        <div className={styles.rightContent}>
          {activeFile ? (
            <>
              <div className={styles.previewCard}>
                <button
                  type="button"
                  className={styles.removeBtn}
                  onClick={() => onRemove(activeFile.id)}
                >
                  ×
                </button>
                <img src={rotatedPreviewUrl ?? activeFile.url} alt={activeFile.name} className={styles.previewImage} />
                <div className={styles.previewFooter}>
                  <span className={styles.fileName}>{activeFile.name}</span>
                  <span className={styles.statusReady}>Готово</span>
                </div>
              </div>

              <BuildingFloorPicker
                selectedBuildingId={selectedBuildingId}
                selectedFloorId={selectedFloorId}
                onChange={onFloorChange}
                planName={planName}
                onPlanNameChange={onPlanNameChange}
                disabled={isUploading}
              />

              
            </>
          ) : (
            <div className={styles.rightEmpty}>Загрузите файл</div>
          )}
        </div>
        <div className={styles.uploadCounter}>
          Загружено: {files.length} {files.length === 1 ? 'изображение' : files.length >= 2 && files.length <= 4 ? 'изображения' : 'изображений'}
        </div>
      </div>
    </div>
  );
};
