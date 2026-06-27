import type { RoomLabel } from '../../types/reconstruction';
import styles from './RoomLabels.module.css';

interface RoomLabelsProps {
  labels: RoomLabel[];
}

export const RoomLabels: React.FC<RoomLabelsProps> = ({ labels }) => {
  if (labels.length === 0) return null;

  return (
    <div className={styles.overlay}>
      {labels.map((label) => (
        <div
          key={label.id}
          className={styles.label}
          style={{
            left: `${label.center_x * 100}%`,
            top: `${label.center_y * 100}%`,
            borderColor: label.color,
          }}
        >
          <span className={styles.dot} style={{ backgroundColor: label.color }} />
          {label.name || label.room_type}
        </div>
      ))}
    </div>
  );
};
