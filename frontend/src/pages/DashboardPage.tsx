import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Layout } from 'lucide-react';
import { reconstructionApi, type ReconstructionListItem } from '../api/apiService';
import { buildingsApi } from '../api/buildingsApi';
import styles from './DashboardPage.module.css';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [reconstructions, setReconstructions] = useState<ReconstructionListItem[]>([]);
  const [hasBuildings, setHasBuildings] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [data, buildings] = await Promise.all([
          reconstructionApi.getReconstructions(),
          buildingsApi.list(),
        ]);
        setReconstructions(data);
        setHasBuildings(buildings.length > 0);
      } catch {
        setError('Ошибка загрузки списка');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const handleDelete = async (id: number) => {
    try {
      await reconstructionApi.deleteReconstruction(id);
      setReconstructions((prev) => prev.filter((r) => r.id !== id));
    } catch {
      setError('Ошибка удаления');
    } finally {
      setConfirmDeleteId(null);
    }
  };

  if (isLoading) {
    return <div className={styles.loading}>SYS.LOADING...</div>;
  }

  if (reconstructions.length === 0) {
    return (
      <div className={styles.empty}>
        <div className={styles.emptyPattern} />
        <div className={styles.emptyBox}>
          <div className={styles.emptyIcon}>
            <Layout size={80} strokeWidth={1} />
          </div>
          <h3 className={styles.emptyTitle}>Рабочая область пуста</h3>
          <div className={styles.emptyDivider} />
          <p className={styles.emptyMsg}>SYS.MSG: Требуется загрузка исходных данных для начала работы</p>
          {error && <p className={styles.error}>{error}</p>}
          <button
            className={styles.startBtn}
            onClick={() => navigate('/admin/buildings')}
          >
            {hasBuildings ? 'Начать работу' : 'Создать корпус'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.grid}>
        {reconstructions.map((r) => (
          <div
            key={r.id}
            className={styles.card}
            onClick={() => navigate(`/admin/edit/${r.id}`)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && navigate(`/admin/edit/${r.id}`)}
          >
            <div className={styles.preview}>
              {r.preview_url ? (
                <img
                  src={r.preview_url}
                  alt={r.name}
                  className={styles.previewImg}
                />
              ) : (
                <div className={styles.previewPlaceholder} />
              )}
              <button
                type="button"
                className={styles.deleteBtn}
                onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(r.id); }}
                title="Удалить"
              >
                <X size={14} />
              </button>
            </div>
            <p className={styles.cardName}>{r.name}</p>
          </div>
        ))}
      </div>

      {confirmDeleteId !== null && (
        <div className={styles.overlay} onClick={() => setConfirmDeleteId(null)}>
          <div className={styles.confirmDialog} onClick={(e) => e.stopPropagation()}>
            <p className={styles.confirmText}>Вы действительно хотите удалить план?</p>
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.confirmYes}
                onClick={() => handleDelete(confirmDeleteId)}
              >
                Да
              </button>
              <button
                type="button"
                className={styles.confirmNo}
                onClick={() => setConfirmDeleteId(null)}
              >
                Нет
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
