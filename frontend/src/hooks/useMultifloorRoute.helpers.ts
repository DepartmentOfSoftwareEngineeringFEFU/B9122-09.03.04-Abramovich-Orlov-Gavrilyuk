import type { MultifloorRouteRequest } from '../types/buildingNav';

export interface RouteFormState {
  fromFloorId: number | null;
  fromRoom: string;
  toFloorId: number | null;
  toRoom: string;
}

/**
 * Build the route request from the picker state, or null when incomplete
 * (caller blocks the run). Pure — no side effects (unit-testable).
 */
export function buildMultifloorRoutePayload(
  state: RouteFormState,
): MultifloorRouteRequest | null {
  const { fromFloorId, fromRoom, toFloorId, toRoom } = state;
  if (fromFloorId === null || toFloorId === null) return null;
  if (!fromRoom.trim() || !toRoom.trim()) return null;
  return {
    from_floor_id: fromFloorId,
    from_room: fromRoom.trim(),
    to_floor_id: toFloorId,
    to_room: toRoom.trim(),
  };
}

/** Extract a human error detail from an unknown thrown value (no `any`). */
export function extractApiDetail(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: { detail?: unknown } } }).response;
    const detail = resp?.data?.detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}
