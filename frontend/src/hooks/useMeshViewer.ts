import { useEffect, useState } from 'react';
import { reconstructionApi } from '../api/apiService';
import type { ReconstructionDetail } from '../types/reconstruction';

interface UseMeshViewerReturn {
  meshData: ReconstructionDetail | null;
  isLoading: boolean;
  error: string | null;
}

export const useMeshViewer = (id: string): UseMeshViewerReturn => {
  const [meshData, setMeshData] = useState<ReconstructionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await reconstructionApi.getReconstructionById(parseInt(id, 10));
        if (!cancelled) {
          setMeshData(data as unknown as ReconstructionDetail);
        }
      } catch {
        if (!cancelled) {
          setError('Ошибка загрузки модели');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [id]);

  return { meshData, isLoading, error };
};
