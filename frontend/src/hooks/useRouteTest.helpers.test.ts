import { describe, it, expect } from 'vitest';
import {
  adjacentTransitions,
  buildRoomRegistry,
  composeSyntheticId,
  normalizePoint3D,
  normalizeSegmentCoords,
  parseSyntheticId,
  planRoute,
  registryToAnnotations,
  segmentYOffset,
  type ReconstructionVectorsBundle,
} from './useRouteTest.helpers';
import type { ReconstructionListItem } from '../api/apiService';
import type { VectorRoom } from '../types/reconstructionVectors';
import type { PathSegment3D, TransitionUsed3D } from '../types/transitions';

const recon = (
  patch: Partial<ReconstructionListItem> & {
    id: number;
    name: string;
    building_id?: string;
    floor_number?: number;
  },
): ReconstructionListItem => {
  const buildingCode = patch.building_id ?? 'A';
  const floorNumber = patch.floor_number ?? 1;
  return {
    status: 3,
    preview_url: null,
    floor: { id: floorNumber, number: floorNumber, building_code: buildingCode },
    section: null,
    updated_at: '2026-01-01',
    ...patch,
  };
};

const room = (id: string, name: string): VectorRoom => ({
  id,
  name,
  room_type: 'room',
  center: { x: 0.5, y: 0.5 },
  polygon: [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 0, y: 1 },
  ],
  area_normalized: 1,
});

describe('composeSyntheticId / parseSyntheticId', () => {
  it('round-trips numeric recon id and string room id', () => {
    const synthetic = composeSyntheticId(42, 'room-uuid-001');
    expect(synthetic).toBe('42__room-uuid-001');
    expect(parseSyntheticId(synthetic)).toEqual({
      reconId: 42,
      roomId: 'room-uuid-001',
    });
  });

  it('returns null for malformed input', () => {
    expect(parseSyntheticId('no-separator')).toBeNull();
    expect(parseSyntheticId('__only-room')).toBeNull();
    expect(parseSyntheticId('42__')).toBeNull();
    expect(parseSyntheticId('NaN__r')).toBeNull();
  });
});

describe('buildRoomRegistry', () => {
  it('returns empty for empty input', () => {
    expect(buildRoomRegistry([])).toEqual([]);
  });

  it('flattens rooms across reconstructions and tags each with floor/building', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: recon({ id: 1, name: 'A11_2', floor_number: 11 }),
        rooms: [room('r-1', '1110'), room('r-2', '1106')],
      },
      {
        reconstruction: recon({ id: 2, name: 'TEST-13-02', floor_number: 11 }),
        rooms: [room('r-1', '1110')], // duplicate name+id from a copied plan
      },
    ];

    const registry = buildRoomRegistry(bundles);
    expect(registry).toHaveLength(3);

    const labels = registry.map((e) => e.displayLabel);
    // Both "1110" entries must be visually distinguishable.
    expect(labels.filter((l) => l.endsWith('__1110'))).toHaveLength(2);
    expect(new Set(labels).size).toBe(3);

    // Synthetic ids globally unique even when realRoomId clashes.
    const syntheticIds = registry.map((e) => e.syntheticId);
    expect(new Set(syntheticIds).size).toBe(3);
  });

  it('sorts rooms by name (natural), then floor, then reconstruction', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: recon({ id: 1, name: 'A', floor_number: 2 }),
        rooms: [room('a', '101'), room('b', '20'), room('c', '3')],
      },
    ];
    const reg = buildRoomRegistry(bundles);
    expect(reg.map((r) => r.rawName)).toEqual(['3', '20', '101']);
  });

  it('falls back to "[room_type]" when name is empty', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: recon({ id: 1, name: 'A', floor_number: 1 }),
        rooms: [{ ...room('r', ''), room_type: 'corridor' }],
      },
    ];
    const reg = buildRoomRegistry(bundles);
    expect(reg[0].rawName).toBe('[corridor]');
    expect(reg[0].displayLabel).toContain('[corridor]');
  });

  it('test_useRouteTest_displayLabel_uses_hierarchy: label is BuildingCode-FloorNum-SectionNum__RoomName', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: {
          ...recon({ id: 1, name: 'S1', floor_number: 3, building_id: 'B' }),
          section: { id: 5, number: 2 },
        },
        rooms: [room('r-301', '301')],
      },
    ];
    const registry = buildRoomRegistry(bundles);
    expect(registry).toHaveLength(1);
    expect(registry[0].displayLabel).toBe('B-3-2__301');
  });

  it('test_useRouteTest_filters_reconstructions_without_floor: unbound reconstructions excluded', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: recon({ id: 1, name: 'Bound', floor_number: 1 }),
        rooms: [room('r-1', '101')],
      },
      {
        reconstruction: {
          id: 2,
          name: 'Unbound',
          status: 3,
          preview_url: null,
          floor: null,
          section: null,
          updated_at: '2026-01-01',
        },
        rooms: [room('r-2', '202')],
      },
    ];
    const registry = buildRoomRegistry(bundles);
    // Only rooms from the floor-bound reconstruction should appear.
    expect(registry).toHaveLength(1);
    expect(registry[0].reconstructionId).toBe(1);
  });
});

describe('registryToAnnotations', () => {
  it('maps each entry to RoomAnnotation with synthetic id and display name', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: recon({ id: 7, name: 'X', floor_number: 1 }),
        rooms: [room('rA', '101')],
      },
    ];
    const registry = buildRoomRegistry(bundles);
    const annotations = registryToAnnotations(registry);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].id).toBe('7__rA');
    expect(annotations[0].name).toBe(registry[0].displayLabel);
    expect(annotations[0].room_type).toBe('room');
  });

  it('preserves staircase / elevator / corridor types', () => {
    const bundles: ReconstructionVectorsBundle[] = [
      {
        reconstruction: recon({ id: 1, name: 'X', floor_number: 1 }),
        rooms: [
          { ...room('s', 'L1'), room_type: 'staircase' },
          { ...room('e', 'E1'), room_type: 'elevator' },
          { ...room('c', 'C1'), room_type: 'corridor' },
        ],
      },
    ];
    const annotations = registryToAnnotations(buildRoomRegistry(bundles));
    // New label format: "<BuildingCode>-<FloorNum>-<SectionNum>__<RoomName>"
    // Extract room name as the part after the last '__'.
    const byName = Object.fromEntries(
      annotations.map((a) => [a.name.split('__').pop() ?? a.name, a.room_type]),
    );
    expect(byName['L1']).toBe('staircase');
    expect(byName['E1']).toBe('elevator');
    expect(byName['C1']).toBe('corridor');
  });
});

describe('planRoute', () => {
  const bundles: ReconstructionVectorsBundle[] = [
    {
      reconstruction: recon({ id: 1, name: 'F1', floor_number: 1, building_id: 'A' }),
      rooms: [room('r-101', '101'), room('r-102', '102')],
    },
    {
      reconstruction: recon({ id: 2, name: 'F2', floor_number: 2, building_id: 'A' }),
      rooms: [room('r-201', '201')],
    },
    {
      reconstruction: recon({ id: 3, name: 'OtherBldg', floor_number: 1, building_id: 'B' }),
      rooms: [room('r-301', '301')],
    },
  ];
  const registry = buildRoomRegistry(bundles);
  const idOf = (synthName: string) =>
    registry.find((r) => r.rawName === synthName)!.syntheticId;

  it('detects single-floor request when both rooms share reconstruction', () => {
    const plan = planRoute(registry, idOf('101'), idOf('102'));
    expect(plan.valid).toBe(true);
    expect(plan.singleFloor).toBe(true);
    expect(plan.fromEntry?.realRoomId).toBe('r-101');
    expect(plan.toEntry?.realRoomId).toBe('r-102');
  });

  it('detects multi-floor request when reconstructions differ but building matches', () => {
    const plan = planRoute(registry, idOf('101'), idOf('201'));
    expect(plan.valid).toBe(true);
    expect(plan.singleFloor).toBe(false);
  });

  it('rejects pair when buildings differ', () => {
    const plan = planRoute(registry, idOf('101'), idOf('301'));
    expect(plan.valid).toBe(false);
    expect(plan.reason).toMatch(/разных зданиях/i);
  });

  it('rejects identical synthetic ids', () => {
    const plan = planRoute(registry, idOf('101'), idOf('101'));
    expect(plan.valid).toBe(false);
    expect(plan.singleFloor).toBe(true);
    expect(plan.reason).toMatch(/совпадают/i);
  });

  it('rejects unknown ids', () => {
    const plan = planRoute(registry, '999__missing', idOf('101'));
    expect(plan.valid).toBe(false);
    expect(plan.fromEntry).toBeNull();
    expect(plan.toEntry).not.toBeNull();
  });
});

describe('segmentYOffset / normalizeSegmentCoords / normalizePoint3D', () => {
  const seg = (coords: number[][]): PathSegment3D => ({
    reconstruction_id: 1,
    floor_number: 1,
    floor_name: 'F1',
    coordinates_3d: coords,
  });

  it('returns 0 for empty segment', () => {
    expect(segmentYOffset(seg([]))).toBe(0);
  });

  it('returns minimum Y across segment points', () => {
    expect(
      segmentYOffset(seg([[0, 5, 0], [1, 3.2, 1], [2, 7, 2]])),
    ).toBeCloseTo(3.2);
  });

  it('treats missing Y as 0', () => {
    // A point with only [x] is degenerate but should not crash.
    expect(segmentYOffset(seg([[0, 0, 0], [1]]))).toBe(0);
  });

  it('normalizeSegmentCoords subtracts offset from Y of each point', () => {
    const out = normalizeSegmentCoords(seg([[0, 10, 0], [1, 12, 2]]), 10);
    expect(out).toEqual([
      [0, 0, 0],
      [1, 2, 2],
    ]);
  });

  it('normalizePoint3D handles short arrays gracefully', () => {
    expect(normalizePoint3D([1, 5, 2], 5)).toEqual([1, 0, 2]);
    expect(normalizePoint3D([1], 0)).toEqual([1, 0, 0]);
  });
});

describe('adjacentTransitions', () => {
  const segments: PathSegment3D[] = [
    { reconstruction_id: 1, floor_number: 1, floor_name: 'F1', coordinates_3d: [] },
    { reconstruction_id: 2, floor_number: 2, floor_name: 'F2', coordinates_3d: [] },
    { reconstruction_id: 3, floor_number: 3, floor_name: 'F3', coordinates_3d: [] },
  ];
  const transitions: TransitionUsed3D[] = [
    { name: 'T1->2', from_3d: [0, 1, 0], to_3d: [0, 2, 0] },
    { name: 'T2->3', from_3d: [0, 2, 0], to_3d: [0, 3, 0] },
  ];

  it('first segment: only outgoing transition', () => {
    const adj = adjacentTransitions(0, segments, transitions);
    expect(adj.incoming).toBeNull();
    expect(adj.outgoing?.name).toBe('T1->2');
  });

  it('middle segment: both transitions', () => {
    const adj = adjacentTransitions(1, segments, transitions);
    expect(adj.incoming?.name).toBe('T1->2');
    expect(adj.outgoing?.name).toBe('T2->3');
  });

  it('last segment: only incoming transition', () => {
    const adj = adjacentTransitions(2, segments, transitions);
    expect(adj.incoming?.name).toBe('T2->3');
    expect(adj.outgoing).toBeNull();
  });

  it('out-of-range index: nulls', () => {
    expect(adjacentTransitions(-1, segments, transitions)).toEqual({
      incoming: null,
      outgoing: null,
    });
    expect(adjacentTransitions(99, segments, transitions)).toEqual({
      incoming: null,
      outgoing: null,
    });
  });

  it('single-segment route: no transitions either way', () => {
    const single = [segments[0]];
    expect(adjacentTransitions(0, single, [])).toEqual({
      incoming: null,
      outgoing: null,
    });
  });
});
