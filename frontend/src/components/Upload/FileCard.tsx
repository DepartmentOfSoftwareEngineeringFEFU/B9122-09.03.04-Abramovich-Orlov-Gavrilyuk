import React from 'react';
import { X } from 'lucide-react';
import type { UploadedFile } from '../../types/wizard';
import styles from './FileCard.module.css';

interface FileCardProps {
  file: UploadedFile;
  onRemove: (id: string) => void;
}

export const FileCard: React.FC<FileCardProps> = ({ file, onRemove }) => {
  return (
    <div className={styles.card}>
      <div className={styles.preview}>
        <img src={file.url} alt={file.name} className={styles.img} />
        <button
          type="button"
          className={styles.removeBtn}
          onClick={() => onRemove(file.id)}
          title="Удалить"
        >
          <X size={16} />
        </button>
      </div>
      <p className={styles.name}>{file.name}</p>
    </div>
  );
};
