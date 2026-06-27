import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { reconstructionApi } from '../api/apiService';
import MeshViewer from '../components/MeshViewer';
import styles from './ViewMeshPage.module.css';

interface MeshData {
  id: number;
  name: string | null;
  url: string | null;
  status: number;
  error_message?: string;
}

export const ViewMeshPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [meshData, setMeshData] = useState<MeshData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const fetch = async () => {
      try {
        const data = await reconstructionApi.getReconstructionById(parseInt(id, 10));
        setMeshData(data as MeshData);
      } catch {
        setError('Ошибка загрузки модели');
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, [id]);

  if (isLoading) return <div className={styles.status}>Загрузка 3D модели...</div>;
  if (error || !meshData) return <div className={styles.status}>{error ?? 'Модель не найдена'}</div>;

  return (
    <div className={styles.page}>
      <div className={styles.viewer}>
        {meshData.url ? (
          <MeshViewer
            url={meshData.url}
            format={meshData.url.endsWith('.glb') ? 'glb' : 'obj'}
          />
        ) : (
          <div className={styles.status}>
            {meshData.status === 4
              ? meshData.error_message ?? 'Ошибка построения'
              : `URL модели отсутствует (Статус: ${meshData.status})`}
          </div>
        )}
      </div>
    </div>
  );
};

export default ViewMeshPage;
