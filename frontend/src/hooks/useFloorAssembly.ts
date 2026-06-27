// State + actions for the four Floor-Editor assembly steps (–):
// bind master control points → solve transforms → draw connectors → build &
// confirm the stitched floor mesh.
//
// This is a NEW sibling of useFloorEditorWizard (it does NOT replace it). The
// wizard owns sections/crop/walls (steps 1–5); this hook owns the assembly that
// runs on top of saved sections (steps 6–9). A single read —
// getFloorAssembly(floorId) — drives all four steps; the per-step POST/PUT
// calls then mutate the held draft state without extra round-trips.
//
// Presentational components consume this; all logic lives here (no canvas maths
// — that stays in controlPointCanvasCore — and no `any`).

import { useState, useCallback, useEffect, useRef } from 'react';
import { floorAssemblyApi } from '../api/floorAssemblyApi';
import { floorsApi } from '../api/buildingsApi';
import { reconstructionApi } from '../api/apiService';
import { toastApi } from './useToast';
import { writeActivePoint } from '../lib/controlPoints';
import type {
  AssemblySection,
  BuildFloorPreviewResponse,
  Connector,
  ConnectorInput,
  ControlPoint,
  Cutout,
  CutoutInput,
  FloorAssemblyResponse,
  MasterControlPoint,
  SolveTransformsResponse,
} from '../types/floorAssembly';

/** A connector being drawn/edited on the master canvas (local draft). */
export interface ConnectorDraft {
  /** Server id when the draft originated from a saved connector; absent for new. */
  id?: number;
  points: [number, number][];
  /** Wall thickness in real metres — applied at build as thickness_m * ppm * k. */
  thickness_m: number;
}

/** A cutout zone being drawn/edited on the master canvas (local draft). */
export interface CutoutDraft {
  /** Server id (list index) when the draft originated from a saved cutout. */
  id?: number;
  points: [number, number][];
}

/**
 * Default connector thickness in metres. A touch thicker than the backend's
 * DEFAULT_CONNECTOR_THICKNESS_M fallback so corridor walls read clearly in 3D.
 */
export const DEFAULT_CONNECTOR_THICKNESS_M = 0.3;

export interface UseFloorAssemblyReturn {
  floorId: number | null;
  isLoading: boolean;
  error: string | null;

  // --- Single assembly read (drives all steps) ---
  assembly: FloorAssemblyResponse | null;
  masterSchemaUrl: string | null;
  /** Cropped floor-schema binary mask (blob) — the карта-отсеков backdrop. */
  masterMaskUrl: string | null;
  pixelsPerMeter: number | null;
  meshFileGlb: string | null;
  sections: AssemblySection[];
  load: (floorId: number) => Promise<void>;
  reload: () => Promise<void>;

  // ---: bind control points (section эталон ↔ master карта отсеков) ---
  activeSectionId: number | null;
  activePointId: string | null;
  /** Section-local points placed per section (эталон side, keyed by section id). */
  sectionPointsBySection: Record<number, ControlPoint[]>;
  /** Master points placed per section (карта-отсеков side, keyed by section id). */
  masterPointsBySection: Record<number, MasterControlPoint[]>;
  setActiveSection: (sectionId: number | null) => void;
  setActivePoint: (pointId: string | null) => void;
  /** Write a numbered point's coord on the section (эталон) side (overwrite). */
  setSectionPoint: (sectionId: number, pointId: string, x: number, y: number) => void;
  /** Write a numbered point's coord on the master (карта отсеков) side (overwrite). */
  setMasterPoint: (sectionId: number, pointId: string, x: number, y: number) => void;
  /** Remove a numbered point from BOTH sides (delete the whole correspondence). */
  removePoint: (sectionId: number, pointId: string) => void;
  /** Persist BOTH sides for the section: section-local CPs THEN master CPs (PUT). */
  saveControlPoints: (sectionId: number) => Promise<void>;

  // ---: solve transforms ---
  solveResult: SolveTransformsResponse | null;
  isSolving: boolean;
  solveTransforms: () => Promise<void>;

  // ---: connectors ---
  connectorDrafts: ConnectorDraft[];
  setConnectorDrafts: (drafts: ConnectorDraft[]) => void;
  replaceConnectors: () => Promise<void>;
  isSavingConnectors: boolean;

  // ---: cutouts ---
  cutoutDrafts: CutoutDraft[];
  setCutoutDrafts: (drafts: CutoutDraft[]) => void;
  replaceCutouts: () => Promise<void>;
  isSavingCutouts: boolean;

  // ---: build preview → confirm ---
  buildResult: BuildFloorPreviewResponse | null;
  previewGlbUrl: string | null;
  isBuilding: boolean;
  isConfirming: boolean;
  buildFloorMesh: () => Promise<void>;
  confirmFloorMesh: () => Promise<void>;
}

/** Map server connectors → local drafts; default thickness when server is null. */
export const connectorsToDrafts = (connectors: Connector[]): ConnectorDraft[] =>
  connectors.map((c) => ({
    id: c.id,
    points: c.points,
    thickness_m: c.thickness_m ?? DEFAULT_CONNECTOR_THICKNESS_M,
  }));

/** Map local drafts → replace-all API inputs, carrying thickness_m through. */
export const draftsToInputs = (drafts: ConnectorDraft[]): ConnectorInput[] =>
  drafts.map((d) => ({
    points: d.points,
    thickness_m: d.thickness_m,
  }));

/** Map server cutouts → local drafts (id + points only). */
export const cutoutsToDrafts = (cutouts: Cutout[]): CutoutDraft[] =>
  cutouts.map((c) => ({ id: c.id, points: c.points }));

/** Map local cutout drafts → replace-all API inputs. */
export const draftsToCutoutInputs = (drafts: CutoutDraft[]): CutoutInput[] =>
  drafts.map((d) => ({ points: d.points }));

const masterPointsFromSections = (
  sections: AssemblySection[],
): Record<number, MasterControlPoint[]> => {
  const map: Record<number, MasterControlPoint[]> = {};
  for (const s of sections) {
    map[s.section_id] = s.master_control_points.map((p) => ({ ...p }));
  }
  return map;
};

const sectionPointsFromSections = (
  sections: AssemblySection[],
): Record<number, ControlPoint[]> => {
  const map: Record<number, ControlPoint[]> = {};
  for (const s of sections) {
    map[s.section_id] = s.section_control_points.map((p) => ({ ...p }));
  }
  return map;
};

export const useFloorAssembly = (): UseFloorAssemblyReturn => {
  const [floorId, setFloorId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [assembly, setAssembly] = useState<FloorAssemblyResponse | null>(null);
  const [meshFileGlb, setMeshFileGlb] = useState<string | null>(null);
  const [pixelsPerMeter, setPixelsPerMeter] = useState<number | null>(null);

  // Master backdrop = the cropped floor-schema BINARY MASK (black walls), exactly
  // what the overview shows — fetched as a blob via the mask-preview endpoint. Held
  // in a ref too so the previous blob can be revoked on reload/unmount.
  const [masterMaskUrl, setMasterMaskUrl] = useState<string | null>(null);
  const masterMaskUrlRef = useRef<string | null>(null);
  const setMasterMask = useCallback((url: string | null) => {
    const prev = masterMaskUrlRef.current;
    if (prev && prev.startsWith('blob:') && prev !== url) {
      try {
        URL.revokeObjectURL(prev);
      } catch {
        /* ignore */
      }
    }
    masterMaskUrlRef.current = url;
    setMasterMaskUrl(url);
  }, []);

  const [activeSectionId, setActiveSectionId] = useState<number | null>(null);
  const [activePointId, setActivePointId] = useState<string | null>(null);
  const [sectionPointsBySection, setSectionPointsBySection] = useState<
    Record<number, ControlPoint[]>
  >({});
  const [masterPointsBySection, setMasterPointsBySection] = useState<
    Record<number, MasterControlPoint[]>
  >({});

  const [solveResult, setSolveResult] = useState<SolveTransformsResponse | null>(null);
  const [isSolving, setIsSolving] = useState(false);

  const [connectorDrafts, setConnectorDrafts] = useState<ConnectorDraft[]>([]);
  const [isSavingConnectors, setIsSavingConnectors] = useState(false);

  const [cutoutDrafts, setCutoutDrafts] = useState<CutoutDraft[]>([]);
  const [isSavingCutouts, setIsSavingCutouts] = useState(false);

  const [buildResult, setBuildResult] = useState<BuildFloorPreviewResponse | null>(null);
  const [isBuilding, setIsBuilding] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const load = useCallback(async (id: number): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      // Load the assembly + the floor (for its saved mask) in parallel. The floor
      // fetch is non-fatal — a failure just falls back to regenerating the mask.
      const [data, floor] = await Promise.all([
        floorAssemblyApi.getFloorAssembly(id),
        floorsApi.getById(id).catch(() => null),
      ]);
      setFloorId(id);
      setAssembly(data);
      setMeshFileGlb(data.mesh_file_glb);
      setPixelsPerMeter(data.pixels_per_meter);

      // Backdrop = the карта отсеков. Prefer the operator's persisted Step-3 edit
      // (floor.mask_file_url) so they bind to their cleaned mask; else regenerate
      // it from the original schema via previewMask. Both live in the SAME
      // cropped+rotated master frame, so master points round-trip with the
      // solver/builder either way.
      const ms = data.master_schema;
      if (floor?.mask_file_url) {
        setMasterMask(floor.mask_file_url);
      } else if (ms.image_id) {
        const crop = ms.crop_bbox
          ? {
              x: ms.crop_bbox.x,
              y: ms.crop_bbox.y,
              width: ms.crop_bbox.width,
              height: ms.crop_bbox.height,
            }
          : null;
        try {
          const url = await reconstructionApi.previewMask(
            ms.image_id,
            crop,
            ms.crop_bbox?.rotation ?? 0,
          );
          setMasterMask(url);
        } catch {
          setMasterMask(null);
        }
      } else {
        setMasterMask(null);
      }
      setSectionPointsBySection(sectionPointsFromSections(data.sections));
      setMasterPointsBySection(masterPointsFromSections(data.sections));
      setConnectorDrafts(connectorsToDrafts(data.connectors));
      setCutoutDrafts(cutoutsToDrafts(data.cutouts ?? []));
      // Reset transient per-build state — those come from POSTs, never the read.
      setSolveResult(null);
      setBuildResult(null);
      // Default the active section to the first bound section, if any.
      const firstBound = data.sections.find((s) => s.reconstruction_id !== null);
      setActiveSectionId(firstBound ? firstBound.section_id : null);
      setActivePointId(null);
    } catch {
      setError('Ошибка загрузки данных сборки этажа');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reload = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    await load(floorId);
  }, [floorId, load]);

  const setActiveSection = useCallback((sectionId: number | null) => {
    setActiveSectionId(sectionId);
    setActivePointId(null);
  }, []);

  const setActivePoint = useCallback((pointId: string | null) => {
    setActivePointId(pointId);
  }, []);

  // Write a numbered point's coord on the section (эталон) side. Re-calling the
  // same id overwrites that id's coord (never duplicates).
  const setSectionPoint = useCallback(
    (sectionId: number, pointId: string, x: number, y: number) => {
      setSectionPointsBySection((prev) => {
        const current = prev[sectionId] ?? [];
        return {
          ...prev,
          [sectionId]: [
            ...current.filter((p) => p.id !== pointId),
            { id: pointId, x, y },
          ],
        };
      });
    },
    [],
  );

  // Write a numbered point's coord on the master (карта отсеков) side. Overwrite
  // by id — never nearest-neighbour matched (writeActivePoint, AC2).
  const setMasterPoint = useCallback(
    (sectionId: number, pointId: string, x: number, y: number) => {
      setMasterPointsBySection((prev) => ({
        ...prev,
        [sectionId]: writeActivePoint(prev[sectionId] ?? [], pointId, x, y),
      }));
    },
    [],
  );

  // Delete a numbered point from BOTH sides — a point is one correspondence pair,
  // so removing it clears the эталон AND the карта-отсеков coordinate together.
  const removePoint = useCallback((sectionId: number, pointId: string) => {
    setSectionPointsBySection((prev) => ({
      ...prev,
      [sectionId]: (prev[sectionId] ?? []).filter((p) => p.id !== pointId),
    }));
    setMasterPointsBySection((prev) => ({
      ...prev,
      [sectionId]: (prev[sectionId] ?? []).filter((p) => p.point_id !== pointId),
    }));
    setActivePointId((cur) => (cur === pointId ? null : cur));
  }, []);

  // Persist both sides for one section. Section-local CPs go FIRST (they define the
  // valid id set); the master save then validates every point_id against them, so
  // only master points that already have an эталон counterpart are persisted —
  // incomplete pairs simply wait for their other half.
  const saveControlPoints = useCallback(
    async (sectionId: number): Promise<void> => {
      if (floorId === null) return;
      const section =
        assembly?.sections.find((s) => s.section_id === sectionId) ?? null;
      if (!section || section.reconstruction_id === null) {
        toastApi.error('Отсек не привязан к плану');
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const sectionPts = sectionPointsBySection[sectionId] ?? [];
        const masterPts = masterPointsBySection[sectionId] ?? [];

        // 1) Section эталон → reconstruction.control_points.
        const recRes = await floorAssemblyApi.saveReconstructionControlPoints(
          section.reconstruction_id,
          sectionPts,
        );
        setSectionPointsBySection((prev) => ({
          ...prev,
          [sectionId]: recRes.points,
        }));

        // 2) Master карта отсеков → section.control_points (only complete pairs).
        const savedIds = new Set(recRes.points.map((p) => p.id));
        const masterToSave = masterPts.filter((p) => savedIds.has(p.point_id));
        const mRes = await floorAssemblyApi.saveMasterControlPoints(
          floorId,
          sectionId,
          masterToSave,
        );
        setMasterPointsBySection((prev) => ({ ...prev, [sectionId]: mRes.points }));
        toastApi.success('Опорные точки сохранены');
      } catch {
        toastApi.error('Ошибка сохранения опорных точек');
      } finally {
        setIsLoading(false);
      }
    },
    [floorId, assembly, sectionPointsBySection, masterPointsBySection],
  );

  const solveTransforms = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    setIsSolving(true);
    setError(null);
    try {
      const res = await floorAssemblyApi.solveTransforms(floorId);
      setSolveResult(res);
      setPixelsPerMeter(res.pixels_per_meter);
      const okCount = res.sections.filter((s) => s.status === 'ok').length;
      toastApi.success(`Преобразования рассчитаны (${okCount} OK)`);
    } catch {
      toastApi.error('Ошибка расчёта преобразований');
    } finally {
      setIsSolving(false);
    }
  }, [floorId]);

  const replaceConnectors = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    setIsSavingConnectors(true);
    setError(null);
    try {
      const res = await floorAssemblyApi.replaceConnectors(
        floorId,
        draftsToInputs(connectorDrafts),
      );
      setConnectorDrafts(connectorsToDrafts(res.connectors));
      toastApi.success('Переходы сохранены');
    } catch {
      toastApi.error('Ошибка сохранения переходов');
    } finally {
      setIsSavingConnectors(false);
    }
  }, [floorId, connectorDrafts]);

  const replaceCutouts = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    setIsSavingCutouts(true);
    setError(null);
    try {
      const res = await floorAssemblyApi.replaceCutouts(
        floorId,
        draftsToCutoutInputs(cutoutDrafts),
      );
      setCutoutDrafts(cutoutsToDrafts(res.cutouts));
      toastApi.success('Вырезы сохранены');
    } catch {
      toastApi.error('Ошибка сохранения вырезов');
    } finally {
      setIsSavingCutouts(false);
    }
  }, [floorId, cutoutDrafts]);

  const buildFloorMesh = useCallback(async (): Promise<void> => {
    if (floorId === null) return;
    setIsBuilding(true);
    setError(null);
    try {
      const res = await floorAssemblyApi.buildFloorMesh(floorId);
      setBuildResult(res);
      toastApi.success('Превью этажа построено');
    } catch {
      toastApi.error('Ошибка построения превью этажа');
    } finally {
      setIsBuilding(false);
    }
  }, [floorId]);

  const confirmFloorMesh = useCallback(async (): Promise<void> => {
    if (floorId === null || buildResult === null) return;
    setIsConfirming(true);
    setError(null);
    try {
      const res = await floorAssemblyApi.confirmFloorMesh(
        floorId,
        buildResult.glb_file_id,
      );
      setMeshFileGlb(res.mesh_file_glb);
      toastApi.success('Этаж сохранён');
    } catch {
      toastApi.error('Ошибка сохранения этажа');
    } finally {
      setIsConfirming(false);
    }
  }, [floorId, buildResult]);

  // Revoke the master-mask blob on unmount (section/preview URLs are server URLs,
  // not blob:, so they need no cleanup).
  useEffect(() => {
    return () => {
      const url = masterMaskUrlRef.current;
      if (url && url.startsWith('blob:')) {
        try {
          URL.revokeObjectURL(url);
        } catch {
          /* ignore */
        }
      }
    };
  }, []);

  return {
    floorId,
    isLoading,
    error,
    assembly,
    masterSchemaUrl: assembly?.master_schema.url ?? null,
    masterMaskUrl,
    pixelsPerMeter,
    meshFileGlb,
    sections: assembly?.sections ?? [],
    load,
    reload,
    activeSectionId,
    activePointId,
    sectionPointsBySection,
    masterPointsBySection,
    setActiveSection,
    setActivePoint,
    setSectionPoint,
    setMasterPoint,
    removePoint,
    saveControlPoints,
    solveResult,
    isSolving,
    solveTransforms,
    connectorDrafts,
    setConnectorDrafts,
    replaceConnectors,
    isSavingConnectors,
    cutoutDrafts,
    setCutoutDrafts,
    replaceCutouts,
    isSavingCutouts,
    buildResult,
    previewGlbUrl: buildResult?.glb_url ?? null,
    isBuilding,
    isConfirming,
    buildFloorMesh,
    confirmFloorMesh,
  };
};
