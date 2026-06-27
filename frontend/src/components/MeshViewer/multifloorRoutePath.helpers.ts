import type { FloorPathSegment3D, TransitionUsed3D } from '../../types/buildingNav';

/** Strip the nav node prefix so a transition node id matches `Room3DApi.id`
 * (which is the bare `room_id`, e.g. `room_<uuid>` → `<uuid>`). */
function bareRoomId(nodeId: string): string {
  return nodeId.replace(/^room_/, '');
}

/**
 * Map each stair/lift room that the route uses to the floor a traveller should
 * head to via it — or `null` when it's only an arrival point on the route.
 *
 * Keyed by `Room3DApi.id` (bare room id) so the viewer can, for any floor, find
 * the active shaft icons: a DEPARTURE (the `from` end of a hop) is labelled with
 * the destination floor's number («11 этаж»); an ARRIVAL (the `to` end) is active
 * but unlabelled. A shaft used as both (a mid-route landing) keeps the departure
 * label. `Map.has(id)` ⇒ active (orange); `Map.get(id)` ⇒ label number | null.
 */
export function activeStairLabels(
  transitions: TransitionUsed3D[],
  floorNumberById: Map<number, number>,
): Map<string, number | null> {
  const out = new Map<string, number | null>();
  for (const t of transitions) {
    if (t.to_node) {
      const arrId = bareRoomId(t.to_node);
      if (!out.has(arrId)) out.set(arrId, null); // arrival: active, no label
    }
    if (t.from_node) {
      // Departure: label with the destination floor's number (departure wins).
      out.set(bareRoomId(t.from_node), floorNumberById.get(t.to_floor_id) ?? null);
    }
  }
  return out;
}

/**
 * Concatenate the per-floor 3D segments into one continuous list of points
 * (building-frame world coords, already metric). Used for a single-line render
 * + as the tested core of MultifloorRoutePath. Pure — no THREE, no side effects.
 */
export function buildMultifloorPolyline(
  segments: FloorPathSegment3D[],
): number[][] {
  const out: number[][] = [];
  for (const seg of segments) {
    for (const pt of seg.coordinates_3d) {
      out.push(pt);
    }
  }
  return out;
}

/** Lift a point's Y so the route floats just above the floor mesh. */
export function liftPoint(pt: number[], lift: number): [number, number, number] {
  return [pt[0] ?? 0, (pt[1] ?? 0) + lift, pt[2] ?? 0];
}

/**
 * Highest floor_number among the route segments — the floor drawn "on top" in the
 * stacked viewer. Returns null for an empty segment list.
 */
export function topRouteFloorNumber(
  segments: FloorPathSegment3D[],
): number | null {
  let top: number | null = null;
  for (const seg of segments) {
    if (top === null || seg.floor_number > top) top = seg.floor_number;
  }
  return top;
}

/**
 * Whether a segment on `floorNumber` must be depth-tested (occluded by the meshes
 * of floors stacked above it). Only the topmost route floor renders
 * unconditionally on top; every lower floor's segment is hidden behind the floors
 * above it — so with several floors shown you only see the route on the floor that
 * is actually visible, instead of a lower floor's line bleeding through. A single
 * visible floor is its own top → never occluded (current always-on-top behaviour).
 */
export function segmentOccluded(
  floorNumber: number,
  topFloorNumber: number | null,
): boolean {
  return topFloorNumber !== null && floorNumber < topFloorNumber;
}
