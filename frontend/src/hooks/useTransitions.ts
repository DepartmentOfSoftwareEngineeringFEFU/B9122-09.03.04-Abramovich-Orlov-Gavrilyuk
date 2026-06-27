import { useState, useEffect, useCallback } from 'react';
import { transitionsApi } from '../api/transitionsApi';
import { reconstructionApi, type ReconstructionListItem } from '../api/apiService';
import type { FloorTransition, TransitionEditorMode } from '../types/transitions';

interface UseTransitionsReturn {
  plans: ReconstructionListItem[];
  transitions: FloorTransition[];
  selectedPlanId: number | null;
  mode: TransitionEditorMode;
  isLoading: boolean;
  error: string | null;
  selectPlan: (planId: number) => void;
  startAddingTransition: (name: string, toReconstructionId: number) => void;
  handlePlanSubmit: (geometry: number[][]) => void;
  deleteTransition: (id: number) => Promise<void>;
  cancelMode: () => void;
}

export const useTransitions = (buildingId: string): UseTransitionsReturn => {
  const [plans, setPlans] = useState<ReconstructionListItem[]>([]);
  const [transitions, setTransitions] = useState<FloorTransition[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [mode, setMode] = useState<TransitionEditorMode>({ type: 'idle' });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!buildingId) return;
    setIsLoading(true);
    setError(null);

    Promise.all([
      reconstructionApi.getReconstructions(),
      transitionsApi.listFloorTransitions({ building_id: buildingId }),
    ])
      .then(([allPlans, loadedTransitions]) => {
        const filtered = allPlans.filter((p) => p.floor?.building_code === buildingId);
        setPlans(filtered);
        setTransitions(loadedTransitions);
        if (filtered.length > 0) {
          setSelectedPlanId(filtered[0].id);
        }
      })
      .catch((err: unknown) => {
        setError(String(err));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [buildingId]);

  const selectPlan = useCallback((planId: number) => {
    setSelectedPlanId(planId);
  }, []);

  const startAddingTransition = useCallback((name: string, toReconstructionId: number) => {
    setMode({ type: 'placing_from', name, to_reconstruction_id: toReconstructionId });
  }, []);

  const handlePlanSubmit = useCallback(
    (geometry: number[][]) => {
      // Calculate centroid
      const xs = geometry.map((p) => p[0]);
      const ys = geometry.map((p) => p[1]);
      const cx = xs.reduce((sum, v) => sum + v, 0) / (xs.length || 1);
      const cy = ys.reduce((sum, v) => sum + v, 0) / (ys.length || 1);

      if (mode.type === 'placing_from') {
        const toReconId = mode.to_reconstruction_id;
        setMode({
          type: 'placing_to',
          name: mode.name,
          from_reconstruction_id: selectedPlanId!,
          from_geometry: geometry,
          from_x: cx,
          from_y: cy,
        });
        setSelectedPlanId(toReconId);
      } else if (mode.type === 'placing_to' && selectedPlanId !== null) {
        const req = {
          name: mode.name,
          from_reconstruction_id: mode.from_reconstruction_id,
          from_geometry: mode.from_geometry,
          from_x: mode.from_x,
          from_y: mode.from_y,
          to_reconstruction_id: selectedPlanId,
          to_geometry: geometry,
          to_x: cx,
          to_y: cy,
        };
        transitionsApi
          .createFloorTransition(req)
          .then((newTransition) => {
            setTransitions((prev) => [...prev, newTransition]);
            setMode({ type: 'idle' });
          })
          .catch((err: unknown) => {
            setError(String(err));
            setMode({ type: 'idle' });
          });
      }
    },
    [mode, selectedPlanId],
  );

  const deleteTransition = useCallback(async (id: number) => {
    await transitionsApi.deleteFloorTransition(id);
    setTransitions((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const cancelMode = useCallback(() => {
    setMode({ type: 'idle' });
  }, []);

  return {
    plans,
    transitions,
    selectedPlanId,
    mode,
    isLoading,
    error,
    selectPlan,
    startAddingTransition,
    handlePlanSubmit,
    deleteTransition,
    cancelMode,
  };
};
