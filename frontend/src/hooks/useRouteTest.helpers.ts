/**
 * Pure helpers for useRouteTest. Extracted to keep them testable
 * (no React, no axios — only data shaping).
 */

import type { ReconstructionListItem } from '../api/apiService';
import type { VectorRoom } from '../types/reconstructionVectors';
import type { RoomAnnotation } from '../types/wizard';
import type { PathSegment3D, TransitionUsed3D } from '../types/transitions';

/** A single room as it appears in the global registry. */
export interface RoomEntry {
  /** Synthetic globally-unique id ("<reconId>__<roomId>"). */
  syntheticId: string;
  /** Original UUID from VectorRoom — what backend expects. */
  realRoomId: string;
  /** Original room name ("1110") or fallback. */
  rawName: string;
  /** Human-readable label with floor/building disambiguation. */
  displayLabel: string;
  reconstructionId: number;
  reconstructionName: string;
  buildingId: string | null;
  floorNumber: number | null;
  roomType: VectorRoom['room_type'];
}

export interface ReconstructionVectorsBundle {
  reconstruction: ReconstructionListItem;
  rooms: VectorRoom[];
}

/** Compose synthetic ID. */
export const composeSyntheticId = (reconId: number, roomId: string): string =>
  `${reconId}__${roomId}`;

/** Parse synthetic ID. Returns null if malformed. */
export const parseSyntheticId = (
  synthetic: string,
): { reconId: number; roomId: string } | null => {
  const idx = synthetic.indexOf('__');
  if (idx <= 0) return null;
  const reconId = Number(synthetic.slice(0, idx));
  const roomId = synthetic.slice(idx + 2);
  if (!Number.isFinite(reconId) || !roomId) return null;
  return { reconId, roomId };
};

/**
 * Build a flat global registry of rooms across multiple reconstructions.
 *
 * Reconstructions without a floor binding (floor === null) are excluded.
 *
 * Display labels use the full hierarchy for disambiguation:
 *   "<BuildingCode>-<FloorNumber>-<SectionNumber>__<RoomName>"
 *   e.g. "A-11-2__1110"
 *   Falls back to "?-?-?__<RoomName>" when fields are missing.
 *
 * Sort order: by name (natural), then by floor number, then by reconstruction name.
 */
export const buildRoomRegistry = (
  bundles: ReconstructionVectorsBundle[],
): RoomEntry[] => {
  const out: RoomEntry[] = [];
  for (const b of bundles) {
    const r = b.reconstruction;
    // Exclude reconstructions not bound to a floor.
    if (r.floor === null) continue;
    const floorNumber = r.floor.number;
    const buildingCode = r.floor.building_code;
    const sectionNumber = r.section?.number ?? null;
    for (const room of b.rooms) {
      const rawName = (room.name && room.name.trim()) || `[${room.room_type}]`;
      const bPart = buildingCode ?? '?';
      const fPart = String(floorNumber);
      const sPart = sectionNumber != null ? String(sectionNumber) : '?';
      const displayLabel = `${bPart}-${fPart}-${sPart}__${rawName}`;
      out.push({
        syntheticId: composeSyntheticId(r.id, room.id),
        realRoomId: room.id,
        rawName,
        displayLabel,
        reconstructionId: r.id,
        reconstructionName: r.name,
        buildingId: buildingCode,
        floorNumber,
        roomType: room.room_type,
      });
    }
  }
  out.sort((a, b) => {
    const byName = a.rawName.localeCompare(b.rawName, 'ru', { numeric: true });
    if (byName !== 0) return byName;
    const byFloor = (a.floorNumber ?? 0) - (b.floorNumber ?? 0);
    if (byFloor !== 0) return byFloor;
    return a.reconstructionName.localeCompare(b.reconstructionName, 'ru');
  });
  return out;
};

/** Map RoomEntry list to RoomAnnotation list (shape RouteBottomBar expects). */
export const registryToAnnotations = (
  registry: RoomEntry[],
): RoomAnnotation[] =>
  registry.map((e) => ({
    id: e.syntheticId,
    name: e.displayLabel,
    room_type:
      e.roomType === 'staircase' ||
      e.roomType === 'elevator' ||
      e.roomType === 'corridor'
        ? e.roomType
        : 'room',
    x: 0,
    y: 0,
    width: 0,
    height: 0,
  }));

export interface RoutePlan {
  /** Whether both rooms come from the same reconstruction (single-floor). */
  singleFloor: boolean;
  /** Whether the request is valid (rooms exist + same building if multifloor). */
  valid: boolean;
  /** If invalid — human-readable reason. */
  reason?: string;
  fromEntry: RoomEntry | null;
  toEntry: RoomEntry | null;
}

/** Decide what kind of routing call is needed for a pair of synthetic ids. */
export const planRoute = (
  registry: RoomEntry[],
  fromSynthetic: string,
  toSynthetic: string,
): RoutePlan => {
  const byId = new Map(registry.map((e) => [e.syntheticId, e]));
  const fromEntry = byId.get(fromSynthetic) ?? null;
  const toEntry = byId.get(toSynthetic) ?? null;

  if (!fromEntry || !toEntry) {
    return {
      singleFloor: false,
      valid: false,
      reason: 'Комната не найдена в реестре',
      fromEntry,
      toEntry,
    };
  }
  if (fromEntry.syntheticId === toEntry.syntheticId) {
    return {
      singleFloor: true,
      valid: false,
      reason: 'Стартовая и конечная комнаты совпадают',
      fromEntry,
      toEntry,
    };
  }
  const sameRecon = fromEntry.reconstructionId === toEntry.reconstructionId;
  if (sameRecon) {
    return { singleFloor: true, valid: true, fromEntry, toEntry };
  }
  if (
    !fromEntry.buildingId ||
    !toEntry.buildingId ||
    fromEntry.buildingId !== toEntry.buildingId
  ) {
    return {
      singleFloor: false,
      valid: false,
      reason: 'Комнаты находятся в разных зданиях',
      fromEntry,
      toEntry,
    };
  }
  return { singleFloor: false, valid: true, fromEntry, toEntry };
};

// Per-floor route view helpers

/**
 * Y of the floor "ground" in the multi-floor 3D coordinate system,
 * derived from the minimum Y of the segment's path coordinates.
 * Used to translate path coords back onto a stand-alone single-floor mesh.
 */
export const segmentYOffset = (segment: PathSegment3D): number => {
  if (!segment.coordinates_3d || segment.coordinates_3d.length === 0) return 0;
  let min = Number.POSITIVE_INFINITY;
  for (const p of segment.coordinates_3d) {
    const y = p[1] ?? 0;
    if (y < min) min = y;
  }
  return Number.isFinite(min) ? min : 0;
};

/** Subtract yOffset from every point of a segment's path. */
export const normalizeSegmentCoords = (
  segment: PathSegment3D,
  yOffset: number,
): number[][] =>
  segment.coordinates_3d.map(([x, y, z]) => [
    x,
    (y ?? 0) - yOffset,
    z ?? 0,
  ]);

/** Subtract yOffset from a single 3D point. */
export const normalizePoint3D = (
  p: number[],
  yOffset: number,
): [number, number, number] => [p[0] ?? 0, (p[1] ?? 0) - yOffset, p[2] ?? 0];

/**
 * Convention: transitions_used[i] connects path_segments[i] → path_segments[i+1].
 *   - On segment i, "outgoing" (forward to floor i+1) is transitions_used[i].
 *   - On segment i, "incoming" (came from floor i-1) is transitions_used[i-1].
 */
export const adjacentTransitions = (
  segmentIndex: number,
  pathSegments: PathSegment3D[],
  transitionsUsed: TransitionUsed3D[],
): { incoming: TransitionUsed3D | null; outgoing: TransitionUsed3D | null } => {
  if (segmentIndex < 0 || segmentIndex >= pathSegments.length) {
    return { incoming: null, outgoing: null };
  }
  const incoming = segmentIndex > 0 ? transitionsUsed[segmentIndex - 1] ?? null : null;
  const outgoing =
    segmentIndex < pathSegments.length - 1
      ? transitionsUsed[segmentIndex] ?? null
      : null;
  return { incoming, outgoing };
};
