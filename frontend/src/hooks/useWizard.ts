import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { reconstructionApi, uploadApi } from '../api/apiService';
import { floorAssemblyApi } from '../api/floorAssemblyApi';
import { nextMonotonicId } from '../lib/controlPoints';
import type { WizardState, CropRect, RoomAnnotation, DoorAnnotation } from '../types/wizard';

interface UseWizardReturn {
  state: WizardState;
  nextStep: () => void;
  prevStep: () => void;
  setPlanFile: (id: string, url: string) => void;
  setPlanName: (name: string) => void;
  calculateMask: () => Promise<void>;
  setMaskFile: (id: string) => void;
  saveMaskAndAnnotations: (blob: Blob, rooms: RoomAnnotation[], doors: DoorAnnotation[], canvasState?: unknown) => Promise<string | null>;
  buildNavGraph: (maskId: string, rooms: RoomAnnotation[], doors: DoorAnnotation[]) => Promise<void>;
  buildMesh: (editedMaskId?: string) => Promise<void>;
  save: (name: string) => Promise<void>;
  setFloor: (buildingId: number | null, floorId: number | null) => Promise<void>;
  setCropRect: (rect: CropRect | null) => void;
  setRotation: (deg: 0 | 90 | 180 | 270) => void;
  setBlockSize: (v: number) => void;
  setThresholdC: (v: number) => void;
  addControlPoint: (x: number, y: number) => void;
  moveControlPoint: (id: string, x: number, y: number) => void;
  deleteControlPoint: (id: string) => void;
  canProceedFromUpload: boolean;
  selectedBuildingId: number | null;
  selectedFloorId: number | null;
}

const initialState: WizardState = {
  step: 1,
  planFileId: null,
  planUrl: null,
  planName: '',
  maskFileId: null,
  editedMaskFileId: null,
  canvasState: null,
  reconstructionId: null,
  meshUrl: null,
  cropRect: null,
  rotation: 0,
  blockSize: 15,
  thresholdC: 10,
  rooms: [],
  doors: [],
  controlPoints: [],
  nextControlPointId: 1,
  navGraphId: null,
  isLoading: false,
  error: null,
};

interface FloorSelection {
  buildingId: number | null;
  floorId: number | null;
}

export const useWizard = (): UseWizardReturn => {
  const [state, setState] = useState<WizardState>(initialState);
  const [floorSelection, setFloorSelection] = useState<FloorSelection>({ buildingId: null, floorId: null });
  const navigate = useNavigate();

  const nextStep = useCallback(() => {
    setState((s) => ({ ...s, step: Math.min(s.step + 1, 5) as WizardState['step'] }));
  }, []);

  const prevStep = useCallback(() => {
    setState((s) => ({ ...s, step: Math.max(s.step - 1, 1) as WizardState['step'] }));
  }, []);

  const setPlanName = useCallback((name: string) => {
    setState((s) => ({ ...s, planName: name }));
  }, []);

  const setPlanFile = useCallback((id: string, url: string) => {
    setState((s) => ({ ...s, planFileId: id, planUrl: url }));
  }, []);

  const setCropRect = useCallback((rect: CropRect | null) => {
    setState((s) => ({ ...s, cropRect: rect }));
  }, []);

  const setRotation = useCallback((deg: 0 | 90 | 180 | 270) => {
    setState((s) => ({ ...s, rotation: deg }));
  }, []);

  const setBlockSize = useCallback((v: number) => {
    setState((s) => ({ ...s, blockSize: v }));
  }, []);

  const setThresholdC = useCallback((v: number) => {
    setState((s) => ({ ...s, thresholdC: v }));
  }, []);

  const addControlPoint = useCallback((x: number, y: number) => {
    setState((s) => {
      // Monotonic id from the counter — NEVER reuse a slot freed by delete.
      const { id, counter } = nextMonotonicId(s.nextControlPointId);
      return {
        ...s,
        controlPoints: [...s.controlPoints, { id, x, y }],
        nextControlPointId: counter,
      };
    });
  }, []);

  const moveControlPoint = useCallback((id: string, x: number, y: number) => {
    setState((s) => ({
      ...s,
      controlPoints: s.controlPoints.map((p) => (p.id === id ? { ...p, x, y } : p)),
    }));
  }, []);

  const deleteControlPoint = useCallback((id: string) => {
    // id is NOT reissued — nextControlPointId stays as-is so future adds keep climbing.
    setState((s) => ({
      ...s,
      controlPoints: s.controlPoints.filter((p) => p.id !== id),
    }));
  }, []);

  const setMaskFile = useCallback((id: string) => {
    setState((s) => ({ ...s, maskFileId: id }));
  }, []);

  const saveMaskAndAnnotations = useCallback(async (blob: Blob, rooms: RoomAnnotation[], doors: DoorAnnotation[], canvasState?: unknown): Promise<string | null> => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const file = new File([blob], 'mask.png', { type: 'image/png' });
      const data = await uploadApi.uploadUserMask(file);
      const editedId = String(data.id ?? data.file_id ?? '');
      setState((s) => ({ ...s, editedMaskFileId: editedId, rooms, doors, canvasState: canvasState ?? null, isLoading: false }));
      return editedId;
    } catch {
      setState((s) => ({ ...s, isLoading: false, error: 'Ошибка сохранения маски' }));
      return null;
    }
  }, []);

  const buildNavGraph = useCallback(async (maskId: string, rooms: RoomAnnotation[], doors: DoorAnnotation[]) => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      await reconstructionApi.buildNavGraph(maskId, rooms, doors);
      setState((s) => ({
        ...s,
        navGraphId: maskId,
        isLoading: false,
        step: 4,
      }));
    } catch {
      setState((s) => ({ ...s, isLoading: false, error: 'Ошибка построения графа' }));
    }
  }, []);

  const calculateMask = useCallback(async () => {
    if (!state.planFileId) return;
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const data = await reconstructionApi.calculateMask(
        state.planFileId,
        state.cropRect ?? undefined,
        state.rotation,
        state.blockSize,
        state.thresholdC,
      );
      const raw = data as unknown as Record<string, unknown>;
      const fileId = raw.file_id ?? raw.id ?? raw.mask_file_id ?? '';
      setState((s) => ({ ...s, maskFileId: String(fileId), isLoading: false }));
    } catch {
      setState((s) => ({ ...s, isLoading: false, error: 'Ошибка вычисления маски' }));
    }
  }, [state.planFileId, state.cropRect, state.rotation, state.blockSize, state.thresholdC]);

  const buildMesh = useCallback(async (editedMaskId?: string) => {
    const maskId = editedMaskId || state.editedMaskFileId || state.maskFileId;
    if (!state.planFileId || !maskId) return;
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const data = await reconstructionApi.calculateMesh(
        state.planFileId,
        maskId,
        state.rotation,
        state.cropRect,
        state.rooms,
        state.doors
      );
      const reconstructionId = data.id as number;
      // Bind to the selected floor right after creation so the uploaded plan lands
      // on the floor even if the 3D build fails or the operator exits before the
      // final save (early binding). Non-fatal — re-confirmed at save.
      if (floorSelection.floorId !== null) {
        try {
          await reconstructionApi.patchReconstructionFloor(
            reconstructionId,
            floorSelection.floorId,
          );
        } catch {
          /* non-fatal: floor binding is retried at save() */
        }
      }
      // Deferred persistence: there is no reconstructionId until build runs, so
      // section-local control points are held in state.controlPoints and flushed
      // here, right after the build creates the reconstruction. Non-fatal — a CP
      // save error must not roll back a successful 3D build.
      if (state.controlPoints.length > 0) {
        try {
          await floorAssemblyApi.saveReconstructionControlPoints(
            reconstructionId,
            state.controlPoints,
          );
        } catch {
          // Swallowed: the operator can re-save points later from the editor.
        }
      }
      const detail = await reconstructionApi.getReconstructionById(reconstructionId);
      setState((s) => ({
        ...s,
        reconstructionId,
        meshUrl: detail.url as string | null,
        isLoading: false,
        step: 5,
      }));
    } catch {
      setState((s) => ({ ...s, isLoading: false, error: 'Ошибка построения 3D-модели' }));
    }
  }, [state.planFileId, state.editedMaskFileId, state.maskFileId, state.controlPoints, floorSelection.floorId]);

  const setFloor = useCallback(
    async (buildingId: number | null, floorId: number | null): Promise<void> => {
      setFloorSelection({ buildingId, floorId });
      // Early binding: if reconstruction already created, PATCH immediately
      if (floorId !== null && state.reconstructionId !== null) {
        try {
          await reconstructionApi.patchReconstructionFloor(state.reconstructionId, floorId);
        } catch {
          // Non-fatal: binding will be retried on save
        }
      }
    },
    [state.reconstructionId],
  );

  const save = useCallback(
    async (name: string) => {
      if (!state.reconstructionId) return;
      const floorId = floorSelection.floorId;
      if (floorId === null) return;
      setState((s) => ({ ...s, isLoading: true, error: null }));
      try {
        await reconstructionApi.saveReconstruction(state.reconstructionId, name, floorId);
        navigate('/admin/buildings');
      } catch {
        setState((s) => ({ ...s, isLoading: false, error: 'Ошибка сохранения' }));
      }
    },
    [state.reconstructionId, floorSelection.floorId, navigate],
  );

  const canProceedFromUpload = floorSelection.floorId !== null;

  return {
    state,
    nextStep,
    prevStep,
    setPlanFile,
    setPlanName,
    calculateMask,
    setMaskFile,
    saveMaskAndAnnotations,
    buildNavGraph,
    buildMesh,
    save,
    setFloor,
    setCropRect,
    setRotation,
    setBlockSize,
    setThresholdC,
    addControlPoint,
    moveControlPoint,
    deleteControlPoint,
    canProceedFromUpload,
    selectedBuildingId: floorSelection.buildingId,
    selectedFloorId: floorSelection.floorId,
  };
};
