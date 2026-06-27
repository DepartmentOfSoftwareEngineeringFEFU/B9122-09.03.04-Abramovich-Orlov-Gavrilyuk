import { useState, useEffect, useCallback } from 'react';
import { buildingsApi } from '../api/buildingsApi';
import type { Building, BuildingDetail } from '../types/hierarchy';

interface UseBuildingsReturn {
  buildings: Building[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  createBuilding: (req: { code: string; name: string; address?: string }) => Promise<Building>;
  updateBuilding: (id: number, req: { name?: string; address?: string }) => Promise<Building>;
  deleteBuilding: (id: number) => Promise<void>;
  getBuildingDetail: (id: number) => Promise<BuildingDetail>;
}

export const useBuildings = (): UseBuildingsReturn => {
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBuildings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await buildingsApi.list();
      setBuildings(data);
    } catch {
      setError('Ошибка загрузки корпусов');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchBuildings();
  }, [fetchBuildings]);

  const createBuilding = useCallback(
    async (req: { code: string; name: string; address?: string }): Promise<Building> => {
      const building = await buildingsApi.create(req);
      setBuildings((prev) => [...prev, building]);
      return building;
    },
    [],
  );

  const updateBuilding = useCallback(
    async (id: number, req: { name?: string; address?: string }): Promise<Building> => {
      const updated = await buildingsApi.update(id, req);
      setBuildings((prev) => prev.map((b) => (b.id === id ? updated : b)));
      return updated;
    },
    [],
  );

  const deleteBuilding = useCallback(async (id: number): Promise<void> => {
    await buildingsApi.delete(id);
    setBuildings((prev) => prev.filter((b) => b.id !== id));
  }, []);

  const getBuildingDetail = useCallback(
    async (id: number): Promise<BuildingDetail> => buildingsApi.getById(id),
    [],
  );

  return {
    buildings,
    isLoading,
    error,
    refetch: fetchBuildings,
    createBuilding,
    updateBuilding,
    deleteBuilding,
    getBuildingDetail,
  };
};
