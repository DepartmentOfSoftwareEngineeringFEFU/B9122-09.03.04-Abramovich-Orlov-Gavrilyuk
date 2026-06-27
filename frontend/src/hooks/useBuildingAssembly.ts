// State + actions for the Building Assembly page (subfeature A, vertical floor
// stitching). One GET /buildings/{id}/assembly drives the floor chain + the
// selected-pair dual canvas; PUT stitch-points saves a pair; POST solve-stitch
// solves every adjacent pair and composes per-floor building transforms.
//
// The dual canvas pairs points by id `cp-N` on BOTH panels (same scheme as
// section stitching) via lib/controlPoints. All logic lives here; the page is
// presentational. No canvas maths (that is in controlPointCanvasCore) and no
// `any`.

import { useState, useCallback, useEffect, useRef } from 'react';
import { buildingAssemblyApi } from '../api/buildingAssemblyApi';
import { nextNumberId } from '../lib/controlPoints';
import type {
  AssemblyFloor,
  BuildingAssemblyResponse,
  ControlPoint,
  FloorStitchStatusValue,
  SaveStitchPointsRequest,
  SolveStitchResponse,
} from '../types/buildingAssembly';

/** Minimum correspondence pairs a similarity solve needs (matches the solver). */
export const MIN_STITCH_PAIRS = 3;

/** The adjacent floor pair currently shown on the dual canvas. */
export interface SelectedPair {
  /** Reference floor (the one BELOW) — its mask is the left panel backdrop. */
  lowerId: number;
  /** Moving floor (the one ABOVE) — its mask is the right panel backdrop. */
  upperId: number;
}

/** Per-pair completeness for the chain badges + the solve gate. */
export interface PairCompleteness {
  /** How many ids appear on BOTH the upper and the lower side. */
  paired: number;
  /** True when there are ≥ MIN_STITCH_PAIRS fully-paired correspondences. */
  complete: boolean;
}

// Pure helpers (unit-tested in node vitest env — no DOM)

/**
 * Pair completeness for one floor pair: how many control-point ids appear on
 * BOTH sides, and whether that reaches the solver's minimum (≥3). Ids present on
 * only one side do not count — a pair is one id matched across both panels.
 */
export const pairCompleteness = (
  points: readonly ControlPoint[],
  refPoints: readonly ControlPoint[],
): PairCompleteness => {
  const refIds = new Set(refPoints.map((p) => p.id));
  let paired = 0;
  const seen = new Set<string>();
  for (const p of points) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    if (refIds.has(p.id)) paired += 1;
  }
  return { paired, complete: paired >= MIN_STITCH_PAIRS };
};

/**
 * Build the PUT /stitch-points body: only ids present on BOTH sides are sent, so
 * an unmatched half (one panel placed, the other not yet) is never persisted —
 * mirrors the section-stitch save. `points` = upper/moving, `ref_points` = lower
 * reference; each side carries the SAME id for a correspondence.
 */
export const buildSavePayload = (
  upperPts: readonly ControlPoint[],
  lowerPts: readonly ControlPoint[],
): SaveStitchPointsRequest => {
  const lowerById = new Map(lowerPts.map((p) => [p.id, p]));
  const points: ControlPoint[] = [];
  const ref_points: ControlPoint[] = [];
  const used = new Set<string>();
  for (const up of upperPts) {
    if (used.has(up.id)) continue;
    const low = lowerById.get(up.id);
    if (!low) continue;
    used.add(up.id);
    points.push({ id: up.id, x: up.x, y: up.y });
    ref_points.push({ id: low.id, x: low.x, y: low.y });
  }
  return { points, ref_points };
};

/**
 * Overwrite (or add) the coord for one `cp-N` id, keyed by `id`. A re-place of
 * the same id replaces that id's coord — never duplicates, never nearest-matches
 * a different id (the anti-confusion guarantee shared with the section canvas).
 */
export const writeControlPoint = (
  points: readonly ControlPoint[],
  id: string,
  x: number,
  y: number,
): ControlPoint[] => [...points.filter((p) => p.id !== id), { id, x, y }];

/**
 * The id a panel click writes to — mirrors the section-stitch canvas
 * (Step6BindControlPoints). When the canvas reports an active id (`idFromCanvas`
 * non-empty) that existing point is MOVED; otherwise the next sequential number
 * for THIS panel is minted, so repeated clicks on one panel place 1, 2, 3…
 * independently of the other panel. Placing the SAME number on the other panel
 * forms one correspondence pair (paired by id — NOT by click order across
 * panels), so эталон and этаж can be marked in any order. Pure → unit-tested.
 */
export const placementIdFor = (
  idFromCanvas: string,
  samePanelPoints: readonly ControlPoint[],
): string =>
  idFromCanvas !== ''
    ? idFromCanvas
    : nextNumberId(samePanelPoints.map((p) => p.id));

/**
 * Guided flow: the pair number to place next — the lowest existing pair that is
 * NOT yet on BOTH panels, or a freshly minted next number when every pair is
 * complete. Decides which `cp-N` the next canvas click writes to. Pure → tested.
 */
export const nextUnpairedId = (
  upper: readonly ControlPoint[],
  lower: readonly ControlPoint[],
): string => {
  const u = new Set(upper.map((p) => p.id));
  const l = new Set(lower.map((p) => p.id));
  const numOf = (id: string): number => parseInt(/(\d+)/.exec(id)?.[1] ?? '0', 10);
  let max = 0;
  for (const id of [...u, ...l]) max = Math.max(max, numOf(id));
  for (let n = 1; n <= max; n += 1) {
    const id = `cp-${n}`;
    if (!(u.has(id) && l.has(id))) return id;
  }
  return nextNumberId([...u, ...l]);
};

/**
 * Guided flow: which panel to click next for `id` — the lower (reference) floor
 * first, then the matching point on the upper floor; `null` once `id` is on both.
 * Pure → unit-tested.
 */
export const guidedSideFor = (
  id: string | null,
  upper: readonly ControlPoint[],
  lower: readonly ControlPoint[],
): 'lower' | 'upper' | null => {
  if (id === null) return null;
  const onLower = lower.some((p) => p.id === id);
  const onUpper = upper.some((p) => p.id === id);
  if (!onLower) return 'lower';
  if (!onUpper) return 'upper';
  return null;
};

/** Index a solve response by floor id → its resolved status. */
export const statusesByFloor = (
  result: SolveStitchResponse,
): Record<number, FloorStitchStatusValue> => {
  const map: Record<number, FloorStitchStatusValue> = {};
  for (const f of result.floors) map[f.floor_id] = f.status;
  return map;
};

/**
 * Whether a solve is worth running: at least one pair from the reference floor
 * upward is linkable (its saved upper + ref points both reach the minimum). The
 * reference floor itself has no pair below it, so it is skipped. Drives the Solve
 * button's enabled state (completeness gate).
 */
export const canSolve = (floors: readonly AssemblyFloor[]): boolean =>
  floors.some(
    (f) =>
      f.pair_status !== 'reference' &&
      f.points_count >= MIN_STITCH_PAIRS &&
      f.ref_points_count >= MIN_STITCH_PAIRS,
  );

// Hook

export interface UseBuildingAssemblyReturn {
  buildingId: number | null;
  isLoading: boolean;
  error: string | null;

  /** Floor chain (bottom-up by number), drives the left list + canvas. */
  floors: AssemblyFloor[];
  referenceFloorId: number | null;

  /** The adjacent pair currently shown on the dual canvas. */
  selectedPair: SelectedPair | null;
  /** Upper/moving-floor anchor points for the selected pair (this floor's mask). */
  upperPoints: ControlPoint[];
  /** Lower/reference-floor anchor points for the selected pair (floor-below mask). */
  lowerPoints: ControlPoint[];
  /** The numbered point being placed/moved (same id drives both panels). */
  activePointId: string | null;

  solving: boolean;
  savingPair: boolean;
  /** Latest solve result (per-floor status + transforms); null until solved. */
  result: SolveStitchResponse | null;
  /** True when ≥1 linkable pair exists from the reference up (solve gate). */
  solveEnabled: boolean;

  load: (buildingId: number) => Promise<void>;
  selectPair: (upperFloorId: number) => void;
  /** Add a fresh numbered correspondence and make it active (both panels). */
  addPoint: () => void;
  setActivePoint: (pointId: string | null) => void;
  /** Place/overwrite the active id on the UPPER (this-floor) panel. */
  setUpperPoint: (pointId: string, x: number, y: number) => void;
  /** Place/overwrite the active id on the LOWER (reference) panel. */
  setLowerPoint: (pointId: string, x: number, y: number) => void;
  /**
   * Guided placement: write the CURRENT pair (activePointId) on `side`, then
   * advance to the next pair once the click completes a fresh correspondence.
   */
  placeGuided: (side: 'lower' | 'upper', x: number, y: number) => void;
  /** Which panel the guided flow expects next ('lower' | 'upper' | null). */
  guidedSide: 'lower' | 'upper' | null;
  /** Remove a numbered correspondence from BOTH panels. */
  removePoint: (pointId: string) => void;
  /** Persist the selected pair (PUT on the upper floor). */
  savePair: () => Promise<void>;
  /** Solve every adjacent pair and compose building transforms. */
  solve: () => Promise<void>;
}

/** Find the adjacent reference (the floor directly below `upperId` by number). */
const findLowerFloor = (
  floors: readonly AssemblyFloor[],
  upperId: number,
): AssemblyFloor | null => {
  const upper = floors.find((f) => f.id === upperId);
  if (!upper) return null;
  let best: AssemblyFloor | null = null;
  for (const f of floors) {
    if (f.number >= upper.number) continue;
    if (best === null || f.number > best.number) best = f;
  }
  return best;
};

const controlPointsFor = (
  byFloor: Record<number, ControlPoint[]>,
  floorId: number | undefined,
): ControlPoint[] => (floorId !== undefined ? (byFloor[floorId] ?? []) : []);

export const useBuildingAssembly = (): UseBuildingAssemblyReturn => {
  const [buildingId, setBuildingId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [assembly, setAssembly] = useState<BuildingAssemblyResponse | null>(null);
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null);
  const [activePointId, setActivePointId] = useState<string | null>(null);

  // Anchor points keyed by floor id. The upper floor stores its own moving
  // points; the lower (reference) floor stores the matching ref points under the
  // SAME id. Keying by floor id lets a floor that is "upper" for one pair reuse
  // its points when later viewed as the "lower" of the pair above.
  const [pointsByFloor, setPointsByFloor] = useState<Record<number, ControlPoint[]>>({});

  const [solving, setSolving] = useState(false);
  const [savingPair, setSavingPair] = useState(false);
  const [result, setResult] = useState<SolveStitchResponse | null>(null);

  // Latest floors snapshot for stable callbacks that must read it without
  // re-binding on every state change.
  const floorsRef = useRef<AssemblyFloor[]>([]);
  const floors = assembly?.floors ?? [];
  floorsRef.current = floors;

  // Latest points snapshot so selectPair can seed the guided active pair without
  // re-binding on every placement.
  const pointsByFloorRef = useRef<Record<number, ControlPoint[]>>({});
  pointsByFloorRef.current = pointsByFloor;

  const load = useCallback(async (id: number): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await buildingAssemblyApi.getAssembly(id);
      setBuildingId(id);
      setAssembly(data);
      // Seed the canvas from the SAVED anchor coords so they persist across
      // reloads (no re-placing each session). Each upper floor stores its own
      // `points` + the matching `ref_points` on the floor below; we key by floor
      // id (ref first, then a floor's OWN points win — the through-building-anchor
      // model, same caveat as live editing for >2 floors).
      const seeded: Record<number, ControlPoint[]> = {};
      for (const f of data.floors) {
        if (f.ref_points && f.ref_points.length > 0) {
          const lower = findLowerFloor(data.floors, f.id);
          if (lower) seeded[lower.id] = f.ref_points.map((p) => ({ ...p }));
        }
      }
      for (const f of data.floors) {
        if (f.points && f.points.length > 0) {
          seeded[f.id] = f.points.map((p) => ({ ...p }));
        }
      }
      setPointsByFloor(seeded);
      setResult(null);
      setActivePointId(null);
      // Default the selected pair to the lowest NON-reference floor, if any, and
      // point the guided flow at its first incomplete pair.
      const ordered = [...data.floors].sort((a, b) => a.number - b.number);
      const firstUpper = ordered.find((f) => f.pair_status !== 'reference');
      const lower = firstUpper ? findLowerFloor(data.floors, firstUpper.id) : null;
      if (firstUpper && lower) {
        setSelectedPair({ lowerId: lower.id, upperId: firstUpper.id });
        setActivePointId(
          nextUnpairedId(seeded[firstUpper.id] ?? [], seeded[lower.id] ?? []),
        );
      } else {
        setSelectedPair(null);
      }
    } catch {
      setError('Ошибка загрузки сборки здания');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const selectPair = useCallback((upperFloorId: number) => {
    const lower = findLowerFloor(floorsRef.current, upperFloorId);
    if (!lower) {
      setSelectedPair(null);
      setActivePointId(null);
      return;
    }
    setSelectedPair({ lowerId: lower.id, upperId: upperFloorId });
    const pts = pointsByFloorRef.current;
    // Start guidance at the first incomplete pair of the newly-selected floors.
    setActivePointId(nextUnpairedId(pts[upperFloorId] ?? [], pts[lower.id] ?? []));
  }, []);

  const upperPoints = controlPointsFor(pointsByFloor, selectedPair?.upperId);
  const lowerPoints = controlPointsFor(pointsByFloor, selectedPair?.lowerId);

  const addPoint = useCallback(() => {
    if (!selectedPair) return;
    const existing = [
      ...(pointsByFloor[selectedPair.upperId] ?? []),
      ...(pointsByFloor[selectedPair.lowerId] ?? []),
    ].map((p) => p.id);
    const id = nextNumberId(existing);
    setActivePointId(id);
  }, [selectedPair, pointsByFloor]);

  const setActivePoint = useCallback((pointId: string | null) => {
    setActivePointId(pointId);
  }, []);

  const setUpperPoint = useCallback(
    (pointId: string, x: number, y: number) => {
      if (!selectedPair) return;
      setPointsByFloor((prev) => ({
        ...prev,
        [selectedPair.upperId]: writeControlPoint(
          prev[selectedPair.upperId] ?? [],
          pointId,
          x,
          y,
        ),
      }));
    },
    [selectedPair],
  );

  const setLowerPoint = useCallback(
    (pointId: string, x: number, y: number) => {
      if (!selectedPair) return;
      setPointsByFloor((prev) => ({
        ...prev,
        [selectedPair.lowerId]: writeControlPoint(
          prev[selectedPair.lowerId] ?? [],
          pointId,
          x,
          y,
        ),
      }));
    },
    [selectedPair],
  );

  // Guided placement: write the current pair (activePointId) on the clicked side
  // and advance to the next pair only when THIS click completes a fresh
  // correspondence. Re-placing an already-complete point keeps it active so the
  // flow never jumps away unexpectedly.
  const placeGuided = useCallback(
    (side: 'lower' | 'upper', x: number, y: number): void => {
      if (!selectedPair) return;
      const id = activePointId ?? nextUnpairedId(upperPoints, lowerPoints);
      const newLower =
        side === 'lower' ? writeControlPoint(lowerPoints, id, x, y) : lowerPoints;
      const newUpper =
        side === 'upper' ? writeControlPoint(upperPoints, id, x, y) : upperPoints;
      const wasComplete =
        lowerPoints.some((p) => p.id === id) && upperPoints.some((p) => p.id === id);
      setPointsByFloor((prev) => ({
        ...prev,
        [selectedPair.lowerId]: newLower,
        [selectedPair.upperId]: newUpper,
      }));
      const nowComplete =
        newLower.some((p) => p.id === id) && newUpper.some((p) => p.id === id);
      setActivePointId(
        nowComplete && !wasComplete ? nextUnpairedId(newUpper, newLower) : id,
      );
    },
    [selectedPair, activePointId, upperPoints, lowerPoints],
  );

  const removePoint = useCallback(
    (pointId: string) => {
      if (!selectedPair) return;
      setPointsByFloor((prev) => ({
        ...prev,
        [selectedPair.upperId]: (prev[selectedPair.upperId] ?? []).filter(
          (p) => p.id !== pointId,
        ),
        [selectedPair.lowerId]: (prev[selectedPair.lowerId] ?? []).filter(
          (p) => p.id !== pointId,
        ),
      }));
      setActivePointId((cur) => (cur === pointId ? null : cur));
    },
    [selectedPair],
  );

  const savePair = useCallback(async (): Promise<void> => {
    if (selectedPair === null) return;
    const payload = buildSavePayload(
      pointsByFloor[selectedPair.upperId] ?? [],
      pointsByFloor[selectedPair.lowerId] ?? [],
    );
    setSavingPair(true);
    setError(null);
    try {
      const res = await buildingAssemblyApi.putStitchPoints(selectedPair.upperId, payload);
      // Reflect the saved counts into the assembly so the chain badges + solve
      // gate update without a full reload.
      setAssembly((prev) =>
        prev === null
          ? prev
          : {
              ...prev,
              floors: prev.floors.map((f) =>
                f.id === res.floor_id
                  ? {
                      ...f,
                      points_count: res.points_count,
                      ref_points_count: res.ref_points_count,
                      pair_status: res.points_count >= MIN_STITCH_PAIRS
                        ? 'unsolved'
                        : 'needs_points',
                    }
                  : f,
              ),
            },
      );
    } catch {
      setError('Ошибка сохранения опорных точек пары');
    } finally {
      setSavingPair(false);
    }
  }, [selectedPair, pointsByFloor]);

  const solve = useCallback(async (): Promise<void> => {
    if (buildingId === null) return;
    setSolving(true);
    setError(null);
    try {
      const res = await buildingAssemblyApi.postSolveStitch(buildingId);
      setResult(res);
      // Fold the per-floor solve status + transform back into the chain.
      setAssembly((prev) =>
        prev === null
          ? prev
          : {
              ...prev,
              reference_floor_id: res.reference_floor_id,
              floors: prev.floors.map((f) => {
                const solved = res.floors.find((s) => s.floor_id === f.id);
                if (!solved) return f;
                const pairStatus: AssemblyFloor['pair_status'] =
                  solved.status === 'reference'
                    ? 'reference'
                    : solved.status === 'ok'
                      ? 'ok'
                      : solved.status === 'no_mask'
                        ? 'no_mask'
                        : 'needs_points';
                return {
                  ...f,
                  building_transform: solved.building_transform,
                  pair_status: pairStatus,
                };
              }),
            },
      );
    } catch {
      setError('Ошибка расчёта сборки здания');
    } finally {
      setSolving(false);
    }
  }, [buildingId]);

  // Keep the active id pointing at a still-present correspondence after removal.
  useEffect(() => {
    if (activePointId === null) return;
    const stillThere =
      upperPoints.some((p) => p.id === activePointId) ||
      lowerPoints.some((p) => p.id === activePointId);
    if (!stillThere) setActivePointId(null);
  }, [activePointId, upperPoints, lowerPoints]);

  return {
    buildingId,
    isLoading,
    error,
    floors,
    referenceFloorId: assembly?.reference_floor_id ?? null,
    selectedPair,
    upperPoints,
    lowerPoints,
    activePointId,
    solving,
    savingPair,
    result,
    solveEnabled: canSolve(floors),
    load,
    selectPair,
    addPoint,
    setActivePoint,
    setUpperPoint,
    setLowerPoint,
    placeGuided,
    guidedSide: guidedSideFor(activePointId, upperPoints, lowerPoints),
    removePoint,
    savePair,
    solve,
  };
};
