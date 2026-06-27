import React from 'react';
import { X } from 'lucide-react';
import type { UploadedFile } from '../../types/wizard';
import { FileCard } from './FileCard';
import { MetadataForm } from './MetadataForm';
import styles from './FileGrid.module.css';

interface FileGridProps {
  files: UploadedFile[];
  onRemove: (id: string) => void;
  singleFile?: boolean;
}

export const FileGrid: React.FC<FileGridProps> = ({ files, onRemove, singleFile = false }) => {
  if (files.length === 0) {
    return (
      <div className={styles.empty}>
        <div className={styles.emptyIcon}>
          <X size={32} />
        </div>
        <p className={styles.emptyText}>Нет загруженных планов</p>
      </div>
    );
  }

  if (singleFile && files.length === 1) {
    return (
      <div className={styles.single}>
        <img src={files[0].url} alt={files[0].name} className={styles.singlePreview} />
        <MetadataForm />
      </div>
    );
  }

  return (
    <div className={styles.grid}>
      {files.map((file) => (
        <FileCard key={file.id} file={file} onRemove={onRemove} />
      ))}
    </div>
  );
};
