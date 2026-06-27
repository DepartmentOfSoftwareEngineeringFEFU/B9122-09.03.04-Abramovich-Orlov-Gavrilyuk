import { useState, useCallback } from 'react';
import { floorsApi } from '../api/buildingsApi';
import type { Floor, FloorWithSchema } from '../types/hierarchy';

interface UseFloorsReturn {
  floors: Floor[];
  isLoading: boolean;
  error: string | null;
  loadForBuilding: (buildingId: number) => Promise<void>;
  getFloorDetail: (floorId: number) => Promise<FloorWithSchema>;
  createFloor: (buildingId: number, number: number) => Promise<Floor>;
  deleteFloor: (floorId: number) => Promise<void>;
}

export const useFloors = (): UseFloorsReturn => {
  const [floors, setFloors] = useState<Floor[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadForBuilding = useCallback(async (buildingId: number): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await floorsApi.listByBuilding(buildingId);
      setFloors(data);
    } catch {
      setError('Ошибка загрузки этажей');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const getFloorDetail = useCallback(
    async (floorId: number): Promise<FloorWithSchema> => floorsApi.getById(floorId),
    [],
  );

  const createFloor = useCallback(
    async (buildingId: number, number: number): Promise<Floor> => {
      const floor = await floorsApi.create(buildingId, { number });
      setFloors((prev) => [...prev, floor].sort((a, b) => a.number - b.number));
      return floor;
    },
    [],
  );

  const deleteFloor = useCallback(async (floorId: number): Promise<void> => {
    await floorsApi.delete(floorId);
    setFloors((prev) => prev.filter((f) => f.id !== floorId));
  }, []);

  return {
    floors,
    isLoading,
    error,
    loadForBuilding,
    getFloorDetail,
    createFloor,
    deleteFloor,
  };
};
