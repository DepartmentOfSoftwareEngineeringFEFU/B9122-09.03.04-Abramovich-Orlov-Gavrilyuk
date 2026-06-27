// Pure, render-free helpers for the control-point flows. Extracted from the
// hooks/canvas so they can be unit-tested in the node vitest env (no DOM). The
// hooks and ControlPointCanvas import these, so the tests cover the REAL
// production logic — not a parallel copy.

import { SECTION_COLOR_PALETTE } from '../components/FloorEditor/sectionColors';

export interface IdAssignment {
  id: string;
  counter: number;
}

/**
 * Mint the next monotonic control-point id and return the incremented counter.
 * Ids NEVER recycle: deleting a point does not roll the counter back, so this
 * only ever climbs (`cp-1`, `cp-2`, …) — re-adding after a delete yields a fresh
 * higher id, never a freed one (AC1).
 */
export const nextMonotonicId = (counter: number): IdAssignment => ({
  id: `cp-${counter}`,
  counter: counter + 1,
});

/**
 * Next sequence id for the floor-stitch flow (Step 6). Control points are numbered
 * 1, 2, 3… and the SAME number on the section (эталон) and the master (карта
 * отсеков) form one correspondence pair. The id itself is the backend-mandated
 * `cp-N` form (ControlPoint.id / MasterControlPoint.point_id are validated against
 * `^cp-\d+$`); only the bare number is shown in the UI (see {@link pointLabel}).
 * N is `max(existing) + 1` over the digits of the given ids, so a number is never
 * reused. An empty set yields "cp-1".
 */
export const nextNumberId = (ids: readonly string[]): string => {
  let max = 0;
  for (const id of ids) {
    const match = /(\d+)/.exec(id);
    if (match) {
      const n = parseInt(match[1], 10);
      if (n > max) max = n;
    }
  }
  return `cp-${max + 1}`;
};

/** Bare display number for a control-point id ("cp-7" → "7"; falls back to id). */
export const pointLabel = (id: string): string => {
  const match = /(\d+)/.exec(id);
  return match ? match[1] : id;
};

export interface IdedPoint {
  point_id: string;
  x: number;
  y: number;
}

/**
 * Master-bind reducer (AC2): write the coord to the ACTIVE id ONLY. If that id is
 * already placed its coord is OVERWRITTEN (never duplicated); a different id is
 * never nearest-neighbour matched to an existing point. Returns a new array.
 */
export const writeActivePoint = (
  points: IdedPoint[],
  activeId: string,
  x: number,
  y: number,
): IdedPoint[] => [
  ...points.filter((p) => p.point_id !== activeId),
  { point_id: activeId, x, y },
];

/**
 * Deterministic id → palette colour. The SAME id always maps to the SAME colour,
 * which is the anti-confusion guarantee: a control point is drawn in the same
 * colour on the section panel and on the master panel (AC2). Accepts the stable
 * `cp-N` id (or any string / number) and is total — a non-numeric string falls
 * back to a stable hash.
 */
export const colourForId = (id: string | number): string => {
  const palette = SECTION_COLOR_PALETTE;
  let n: number;
  if (typeof id === 'number') {
    n = Math.abs(Math.trunc(id));
  } else {
    const match = /(\d+)/.exec(id);
    if (match) {
      n = parseInt(match[1], 10);
    } else {
      n = 0;
      for (let i = 0; i < id.length; i += 1) {
        n = (n * 31 + id.charCodeAt(i)) >>> 0;
      }
    }
  }
  return palette[n % palette.length];
};
