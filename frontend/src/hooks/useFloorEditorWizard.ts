// State machine for the multi-step floor editor wizard.

import { useState, useCallback } from 'react';
import { floorsApi, sectionsApi } from '../api/buildingsApi';
import { floorSchemaApi } from '../api/floorSchemaApi';
import { uploadApi } from '../api/apiService';
import { toastApi } from './useToast';
import type {
  CropBbox,
  SectionGeometry,
  ReconstructionBrief,
  ReplaceSectionsRequest,
} from '../types/hierarchy';

export type EditorMode = 'wizard' | 'overview' | 'table';
// Steps 6–10 (master control points, solve, connectors, nav-graph, preview) are
// APPENDED after the original 1–5 (upload→crop→walls→sections→bind). Appending
// keeps 1–5 numbering stable, so resetFloor's setCurrentStep(4) and the
// goToStep(1)/goToStep(3) calls in FloorEditorPage stay correct.
export type WizardStep = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;

export interface Point2D {
  x: number;
  y: number;
}

export interface SectionDraft {
  /** Present when the draft originated from a saved section */
  id?: number;
  number: number;
  geometry: SectionGeometry;
  section_type: number;
  reconstruction_id: number | null;
  /** User-chosen display color (hex). Falls back to palette-by-index when absent. */
  color?: string;
  /** Populated for UI display purposes only */
  reconstruction_brief?: ReconstructionBrief;
}

interface UseFloorEditorWizardReturn {
  mode: EditorMode;
  currentStep: WizardStep;
  floorId: number | null;
  schemaImageId: string | null;
  schemaImageUrl: string | null;
  cropBbox: CropBbox | null;
  wallPolygons: Point2D[][] | null;
  /** Blob URL of the user-edited mask from Step 3. Client-only; lives for
   * the duration of the session and overrides /mask-preview on Step 4. */
  editedMaskUrl: string | null;
  sectionDrafts: SectionDraft[];
  isDirty: boolean;
  isLoading: boolean;
  error: string | null;

  loadFor: (floorId: number) => Promise<void>;
  setMode: (mode: EditorMode) => void;
  goToStep: (step: WizardStep) => void;
  nextStep: () => void;
  prevStep: () => void;

  // Wizard data setters
  setSchemaImage: (fileId: string, url: string) => Promise<void>;
  setCropBbox: (bbox: CropBbox) => void;
  commitCropBbox: () => Promise<void>;
  triggerWallExtraction: () => Promise<void>;
  setWallPolygons: (polygons: Point2D[][]) => void;
  setEditedMaskUrl: (url: string | null) => void;
  commitEditedMask: (blob: Blob) => Promise<void>;
  commitWallPolygons: () => Promise<void>;

  // Section management
  addSectionDraft: (geometry: SectionGeometry, number: number, color?: string) => void;
  updateSectionDraft: (idx: number, partial: Partial<SectionDraft>) => void;
  deleteSectionDraft: (idx: number) => void;
  bindReconstruction: (sectionIdx: number, reconstructionId: number | null) => void;
  saveAll: () => Promise<void>;
  resetFloor: () => Promise<void>;
}

function normalizeToPoint2D(polygons: [number, number][][]): Point2D[][] {
  return polygons.map((poly) => poly.map(([x, y]) => ({ x, y })));
}

export const useFloorEditorWizard = (): UseFloorEditorWizardReturn => {
  const [mode, setModeState] = useState<EditorMode>('wizard');
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [floorId, setFloorId] = useState<number | null>(null);
  const [schemaImageId, setSchemaImageId] = useState<string | null>(null);
  const [schemaImageUrl, setSchemaImageUrl] = useState<string | null>(null);
  const [cropBbox, setCropBboxState] = useState<CropBbox | null>(null);
  const [wallPolygons, setWallPolygonsState] = useState<Point2D[][] | null>(null);
  const [editedMaskUrl, setEditedMaskUrlState] = useState<string | null>(null);

  const setEditedMaskUrl = useCallback((url: string | null) => {
    setEditedMaskUrlState((prev) => {
      // Revoke previous blob URL to avoid leaks
      if (prev && prev.startsWith('blob:') && prev !== url) {
        try { URL.revokeObjectURL(prev); } catch { /* ignore */ }
      }
      return url;
    });
  }, []);
  const [sectionDrafts, setSectionDrafts] = useState<SectionDraft[]>([]);
  const [isDirty, setIsDirty] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFor = useCallback(async (id: number): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const [floor, sections] = await Promise.all([
        floorsApi.getById(id),
        sectionsApi.listByFloor(id),
      ]);

      setFloorId(id);
      setSchemaImageId(floor.schema_image_id);
      setSchemaImageUrl(floor.schema_image_url);
      setCropBboxState(floor.schema_crop_bbox);
      setWallPolygonsState(
        floor.wall_polygons ? normalizeToPoint2D(floor.wall_polygons) : null,
      );
      // Restore the persisted Step-3 wall-mask edit. It's a server URL served
      // same-origin via the dev proxy; setEditedMaskUrl only revokes blob: URLs,
      // so passing a server URL (or null) is safe.
      setEditedMaskUrl(floor.mask_file_url);

      const drafts: SectionDraft[] = sections.map((s) => ({
        id: s.id,
        number: s.number,
        geometry: s.geometry,
        section_type: s.section_type,
        reconstruction_id: s.reconstruction?.id ?? null,
        reconstruction_brief: s.reconstruction ?? undefined,
      }));
      setSectionDrafts(drafts);
      setIsDirty(false);

      // Always start the wizard at step 1 (upload) so the admin sees the full
      // sequence: upload → crop → walls → sections. If saved data exists, each
      // step shows it as preview and "Далее" skips re-processing.
      // If sections are already saved, show overview by default — admin can hit
      // "Редактировать" to re-enter wizard from step 1.
      if (sections.length > 0) {
        setModeState('overview');
      } else {
        setModeState('wizard');
        setCurrentStep(1);
      }
    } catch {
      setError('Ошибка загрузки этажа');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setMode = useCallback((m: EditorMode) => {
    setModeState(m);
  }, []);

  const goToStep = useCallback((step: WizardStep) => {
    setCurrentStep(step);
    setModeState('wizard');
  }, []);

  const nextStep = useCallback(() => {
    setCurrentStep((s) => (Math.min(s + 1, 10) as WizardStep));
  }, []);

  const prevStep = useCallback(() => {
    setCurrentStep((s) => (Math.max(s - 1, 1) as WizardStep));
  }, []);

  const setSchemaImage = useCallback(
    async (fileId: string, url: string): Promise<void> => {
      if (floorId === null) return;
      setIsLoading(true);
      setError(null);
      try {
        await floorSchemaApi.uploadSchema(floorId, {
          schema_image_id: fileId,
          schema_crop_bbox: null,
        });
        setSchemaImageId(fileId);
        setSchemaImageUrl(url);
        setCropBboxState(null);
      } catch {
        setError('Ошибка загрузки схемы');
        throw new Error('Ошибка загрузки схемы');
      } finally {
        setIsLoading(false);
      }
    },
    [floorId],
  );

  const setCropBbox = useCallback((bbox: CropBbox) => {
    setCropBboxState(bbox);
    setIsDirty(true);
  }, []);

  const commitCropBbox = useCallback(async (): Promise<void> => {
    if (floorId === null || schemaImageId === null) return;
    setIsLoading(true);
    setError(null);
    try {
      await floorSchemaApi.uploadSchema(floorId, {
        schema_image_id: schemaImageId,
        schema_crop_bbox: cropBbox,
      });
      setIsDirty(false);
    } catch {
      setError('Ошибка сохранения кропа');
      throw new Error('Ошибка сохранения кропа');
    } finally {
      setIsLoading(false);
    }
  }, [floorId, schemaImageId, cropBbox]);

  const triggerWallExtraction = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await floorSchemaApi.extractWalls(floorId);
      setWallPolygonsState(normalizeToPoint2D(result.wall_polygons));
    } catch {
      setError('Ошибка извлечения стен');
      throw new Error('Ошибка извлечения стен');
    } finally {
      setIsLoading(false);
    }
  }, [floorId]);

  const setWallPolygons = useCallback((polygons: Point2D[][]) => {
    setWallPolygonsState(polygons);
    setIsDirty(true);
  }, []);

  const commitWallPolygons = useCallback(async (): Promise<void> => {
    if (floorId === null || wallPolygons === null) return;
    setIsLoading(true);
    setError(null);
    try {
      const raw: [number, number][][] = wallPolygons.map((poly) =>
        poly.map((pt) => [pt.x, pt.y] as [number, number]),
      );
      await floorSchemaApi.updateWalls(floorId, raw);
      setIsDirty(false);
    } catch {
      setError('Ошибка сохранения стен');
      throw new Error('Ошибка сохранения стен');
    } finally {
      setIsLoading(false);
    }
  }, [floorId, wallPolygons]);

  const commitEditedMask = useCallback(async (blob: Blob): Promise<void> => {
    // Show the edit instantly this session (blob URL).
    const url = URL.createObjectURL(blob);
    setEditedMaskUrl(url);
    // Persist so the edit survives reload. Display-only — a failure here must
    // not block the wizard (the edit still shows for this session).
    if (floorId === null) return;
    try {
      const file = new File([blob], `floor-${floorId}-mask.png`, {
        type: 'image/png',
      });
      const data = await uploadApi.uploadUserMask(file);
      const fileId = String(
        (data as { id?: string; file_id?: string }).id
          ?? (data as { id?: string; file_id?: string }).file_id
          ?? '',
      );
      if (fileId) await floorSchemaApi.updateMask(floorId, fileId);
    } catch {
      toastApi.error('Не удалось сохранить правки стен');
    }
  }, [floorId, setEditedMaskUrl]);

  const resetFloor = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    setIsLoading(true);
    setError(null);
    try {
      // Full wipe: remove the sections AND clear the whole floor schema (image,
      // crop, walls, mask) so the operator can load a brand-new карта отсеков from
      // scratch. Then drop back to step 1 (upload). Sections live in their own
      // table, so they're cleared via the sections replace-all; the schema fields
      // via DELETE /floors/{id}/schema.
      await sectionsApi.replace(floorId, { sections: [] });
      await floorSchemaApi.resetSchema(floorId);
      setSectionDrafts([]);
      setSchemaImageId(null);
      setSchemaImageUrl(null);
      setCropBboxState(null);
      setWallPolygonsState(null);
      setEditedMaskUrl(null);
      setIsDirty(false);
      setCurrentStep(1);
      setModeState('wizard');
      toastApi.success('Карта отсеков удалена — загрузите новую');
    } catch {
      // Show as toast, not full-page error — user can retry without losing state.
      toastApi.error('Ошибка удаления карты отсеков');
    } finally {
      setIsLoading(false);
    }
  }, [floorId, setEditedMaskUrl]);

  const addSectionDraft = useCallback(
    (geometry: SectionGeometry, number: number, color?: string) => {
      setSectionDrafts((prev) => [
        ...prev,
        { number, geometry, section_type: 1, reconstruction_id: null, color },
      ]);
      setIsDirty(true);
    },
    [],
  );

  const updateSectionDraft = useCallback(
    (idx: number, partial: Partial<SectionDraft>) => {
      setSectionDrafts((prev) =>
        prev.map((d, i) => (i === idx ? { ...d, ...partial } : d)),
      );
      setIsDirty(true);
    },
    [],
  );

  const deleteSectionDraft = useCallback((idx: number) => {
    setSectionDrafts((prev) => prev.filter((_, i) => i !== idx));
    setIsDirty(true);
  }, []);

  const bindReconstruction = useCallback(
    (sectionIdx: number, reconstructionId: number | null) => {
      setSectionDrafts((prev) =>
        prev.map((d, i) =>
          i === sectionIdx ? { ...d, reconstruction_id: reconstructionId } : d,
        ),
      );
      setIsDirty(true);
    },
    [],
  );

  const saveAll = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    // Validation: every section needs a bound plan. Surface as a toast — this is
    // a user-correctable input issue, not a fatal page error, so don't set the
    // global `error` (which would replace the whole page with the retry fallback).
    const unassigned = sectionDrafts.some((d) => d.reconstruction_id === null);
    if (unassigned) {
      toastApi.error('Не все отсеки имеют назначенный план');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const req: ReplaceSectionsRequest = {
        sections: sectionDrafts.map((d) => ({
          number: d.number,
          geometry: d.geometry,
          section_type: d.section_type,
          reconstruction_id: d.reconstruction_id,
        })),
      };
      const saved = await sectionsApi.replace(floorId, req);
      const updatedDrafts: SectionDraft[] = saved.map((s) => ({
        id: s.id,
        number: s.number,
        geometry: s.geometry,
        section_type: s.section_type,
        reconstruction_id: s.reconstruction?.id ?? null,
        reconstruction_brief: s.reconstruction ?? undefined,
      }));
      setSectionDrafts(updatedDrafts);
      setIsDirty(false);
      setModeState('overview');
      toastApi.success('Отсеки сохранены');
    } catch (err: any) {
      const msg = err?.message || 'Ошибка сохранения секций';
      toastApi.error(msg);
    } finally {
      setIsLoading(false);
    }
  }, [floorId, sectionDrafts]);

  return {
    mode,
    currentStep,
    floorId,
    schemaImageId,
    schemaImageUrl,
    cropBbox,
    wallPolygons,
    editedMaskUrl,
    sectionDrafts,
    isDirty,
    isLoading,
    error,
    loadFor,
    setMode,
    goToStep,
    nextStep,
    prevStep,
    setSchemaImage,
    setCropBbox,
    commitCropBbox,
    triggerWallExtraction,
    setWallPolygons,
    setEditedMaskUrl,
    commitEditedMask,
    commitWallPolygons,
    addSectionDraft,
    updateSectionDraft,
    deleteSectionDraft,
    bindReconstruction,
    saveAll,
    resetFloor,
  };
};
