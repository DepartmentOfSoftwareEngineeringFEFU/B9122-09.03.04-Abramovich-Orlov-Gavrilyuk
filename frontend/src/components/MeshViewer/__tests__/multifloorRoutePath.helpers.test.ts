import { describe, it, expect } from 'vitest';
import {
  activeStairLabels,
  buildMultifloorPolyline,
  liftPoint,
  segmentOccluded,
  topRouteFloorNumber,
} from '../multifloorRoutePath.helpers';
import type { FloorPathSegment3D, TransitionUsed3D } from '../../../types/buildingNav';

const seg = (floor_number: number): FloorPathSegment3D => ({
  floor_id: floor_number,
  floor_number,
  coordinates_3d: [[0, 0, 0], [1, 0, 0]],
});

const hop = (
  fromFloorId: number,
  fromNode: string,
  toFloorId: number,
  toNode: string,
): TransitionUsed3D => ({
  type: 'staircase',
  from_3d: [0, 0, 0],
  to_3d: [0, 0, 0],
  from_floor_id: fromFloorId,
  to_floor_id: toFloorId,
  from_node: fromNode,
  to_node: toNode,
});

describe('buildMultifloorPolyline', () => {
  it('test_polyline_joins_segments: concatenates per-floor 3D segments', () => {
    const segments: FloorPathSegment3D[] = [
      { floor_id: 10, floor_number: 1, coordinates_3d: [[0, 0, 0], [1, 0, 0]] },
      { floor_id: 20, floor_number: 2, coordinates_3d: [[1, 3, 0], [2, 3, 0], [3, 3, 0]] },
    ];
    const poly = buildMultifloorPolyline(segments);
    expect(poly).toHaveLength(5);
    expect(poly[0]).toEqual([0, 0, 0]);
    expect(poly[4]).toEqual([3, 3, 0]);
  });

  it('returns an empty list for no segments', () => {
    expect(buildMultifloorPolyline([])).toEqual([]);
  });
});

describe('liftPoint', () => {
  it('raises only the Y component by the lift amount', () => {
    expect(liftPoint([1, 2, 3], 0.15)).toEqual([1, 2.15, 3]);
  });
});

describe('topRouteFloorNumber', () => {
  it('returns the highest floor_number among segments', () => {
    expect(topRouteFloorNumber([seg(10), seg(11)])).toBe(11);
  });

  it('returns the single floor when only one segment', () => {
    expect(topRouteFloorNumber([seg(10)])).toBe(10);
  });

  it('returns null for no segments', () => {
    expect(topRouteFloorNumber([])).toBeNull();
  });
});

describe('activeStairLabels', () => {
  const numbers = new Map<number, number>([[2, 10], [1, 11]]);

  it('labels a departure shaft with the destination floor; arrival stays unlabelled', () => {
    // Up-and-over: floor 10 → 11 → 10 (room ids carry the nav "room_" prefix).
    const tr = [
      hop(2, 'room_R', 1, 'room_Ru'), // depart floor 10 → arrive floor 11
      hop(1, 'room_Lu', 2, 'room_L'), // depart floor 11 → arrive floor 10
    ];
    const labels = activeStairLabels(tr, numbers);
    expect(labels.get('R')).toBe(11); // departs floor 10 → «11 этаж»
    expect(labels.get('L')).toBeNull(); // arrival on floor 10 → active, no label
    expect(labels.get('Lu')).toBe(10); // departs floor 11 → «10 этаж»
    expect(labels.get('Ru')).toBeNull(); // arrival on floor 11
    expect(labels.has('other')).toBe(false); // unused shafts are inactive
  });

  it('keeps the departure label for a mid-route shaft used as both arrival and departure', () => {
    const numbers3 = new Map<number, number>([[1, 1], [2, 2], [3, 3]]);
    const tr = [hop(1, 'room_A', 2, 'room_B'), hop(2, 'room_B', 3, 'room_C')];
    const labels = activeStairLabels(tr, numbers3);
    expect(labels.get('B')).toBe(3); // arrival of hop1 + departure of hop2 → departure wins
  });

  it('returns an empty map for no transitions', () => {
    expect(activeStairLabels([], numbers).size).toBe(0);
  });
});

describe('segmentOccluded', () => {
  it('occludes a lower floor so it does not bleed through the floor above', () => {
    expect(segmentOccluded(10, 11)).toBe(true);
  });

  it('never occludes the topmost shown floor (stays always-on-top)', () => {
    expect(segmentOccluded(11, 11)).toBe(false);
  });

  it('never occludes when there is no top floor (empty route)', () => {
    expect(segmentOccluded(10, null)).toBe(false);
  });
});
