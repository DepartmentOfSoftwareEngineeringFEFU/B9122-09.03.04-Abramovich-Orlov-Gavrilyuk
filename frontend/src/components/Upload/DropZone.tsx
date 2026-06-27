import React, { useRef } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '../UI/Button';
import styles from './DropZone.module.css';

interface DropZoneProps {
  onFilesSelect: (files: File[]) => void;
  isUploading: boolean;
  accept?: string;
}

export const DropZone: React.FC<DropZoneProps> = ({
  onFilesSelect,
  isUploading,
  accept = 'image/*',
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) onFilesSelect(files);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFilesSelect(files);
    e.target.value = '';
  };

  return (
    <div className={styles.zone} onDragOver={handleDragOver} onDrop={handleDrop}>
      <Upload size={48} className={styles.icon} />
      <p className={styles.text}>Перетащите для загрузки</p>
      <Button
        variant="primary"
        onClick={() => inputRef.current?.click()}
        disabled={isUploading}
      >
        {isUploading ? 'Загрузка...' : 'Выбрать файлы'}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        className={styles.hidden}
        onChange={handleChange}
      />
    </div>
  );
};
