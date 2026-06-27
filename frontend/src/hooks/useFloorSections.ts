import { useState, useCallback } from 'react';
import { sectionsApi } from '../api/buildingsApi';
import type { Section, ReplaceSectionsRequest } from '../types/hierarchy';

interface UseFloorSectionsReturn {
  sections: Section[];
  isLoading: boolean;
  error: string | null;
  loadForFloor: (floorId: number) => Promise<void>;
  replaceSections: (floorId: number, req: ReplaceSectionsRequest) => Promise<Section[]>;
  deleteSection: (sectionId: number) => Promise<void>;
}

export const useFloorSections = (): UseFloorSectionsReturn => {
  const [sections, setSections] = useState<Section[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadForFloor = useCallback(async (floorId: number): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await sectionsApi.listByFloor(floorId);
      setSections(data);
    } catch {
      setError('Ошибка загрузки секций');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const replaceSections = useCallback(
    async (floorId: number, req: ReplaceSectionsRequest): Promise<Section[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const updated = await sectionsApi.replace(floorId, req);
        setSections(updated);
        return updated;
      } catch {
        setError('Ошибка сохранения секций');
        throw new Error('Ошибка сохранения секций');
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const deleteSection = useCallback(async (sectionId: number): Promise<void> => {
    await sectionsApi.delete(sectionId);
    setSections((prev) => prev.filter((s) => s.id !== sectionId));
  }, []);

  return {
    sections,
    isLoading,
    error,
    loadForFloor,
    replaceSections,
    deleteSection,
  };
};
