import styles from './ViewerControls.module.css';

interface ViewerControlsProps {
  glbUrl: string | null;
  viewMode: 'top' | '3d';
  onViewModeChange: (mode: 'top' | '3d') => void;
  showRooms?: boolean;
  onToggleRooms?: () => void;
  hasRooms?: boolean;
}

export const ViewerControls: React.FC<ViewerControlsProps> = ({
  glbUrl,
  viewMode,
  onViewModeChange,
  showRooms: _showRooms = false,
  onToggleRooms: _onToggleRooms,
  hasRooms: _hasRooms = false,
}) => {
  const handleDownload = () => {
    if (glbUrl) {
      window.open(glbUrl);
    }
  };

  return (
    <div className={styles.controls}>
      <div className={styles.viewToggle}>
        <button
          className={`${styles.toggleBtn} ${viewMode === 'top' ? styles.active : ''}`}
          onClick={() => onViewModeChange('top')}
          type="button"
        >
          Сверху
        </button>
        <button
          className={`${styles.toggleBtn} ${viewMode === '3d' ? styles.active : ''}`}
          onClick={() => onViewModeChange('3d')}
          type="button"
        >
          3D
        </button>
      </div>

      <button
        className={styles.downloadBtn}
        onClick={handleDownload}
        disabled={!glbUrl}
        type="button"
      >
        Скачать GLB
      </button>
    </div>
  );
};
