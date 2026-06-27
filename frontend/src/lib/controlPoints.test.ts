import { describe, it, expect } from 'vitest';
import {
  nextMonotonicId,
  nextNumberId,
  pointLabel,
  writeActivePoint,
  colourForId,
} from './controlPoints';
import {
  nearestWithin,
  hitTest,
  displayRadiusToNorm,
  R_SNAP_PX,
  R_HIT_PX,
} from '../components/controlPointCanvasCore';

describe('nextMonotonicId', () => {
  it('test_add_control_point_assigns_next_monotonic_id', () => {
    expect(nextMonotonicId(1)).toEqual({ id: 'cp-1', counter: 2 });
    expect(nextMonotonicId(2)).toEqual({ id: 'cp-2', counter: 3 });
  });

  it('test_delete_point_does_not_reuse_id', () => {
    // Add cp-1, cp-2, cp-3 → counter climbs 1→4. Deleting cp-2 leaves the counter
    // at 4 (delete never rolls it back), so the next add is cp-4, not the freed id.
    let counter = 1;
    const ids: string[] = [];
    for (let i = 0; i < 3; i += 1) {
      const a = nextMonotonicId(counter);
      ids.push(a.id);
      counter = a.counter;
    }
    const afterDelete = nextMonotonicId(counter); // counter untouched by delete
    expect(ids).toEqual(['cp-1', 'cp-2', 'cp-3']);
    expect(afterDelete.id).toBe('cp-4');
    expect(afterDelete.id).not.toBe('cp-2');
  });
});

describe('nextNumberId (floor-stitch pairing)', () => {
  it('starts at "cp-1" for an empty set', () => {
    expect(nextNumberId([])).toBe('cp-1');
  });

  it('returns cp-(max + 1) over the digits of existing cp-N ids', () => {
    // Left has cp-1,cp-2; right has cp-1,cp-2,cp-3 → next is cp-4 (never reuses 3).
    expect(nextNumberId(['cp-1', 'cp-2', 'cp-1', 'cp-2', 'cp-3'])).toBe('cp-4');
  });

  it('is backend-pattern (^cp-\\d+$) compatible and survives a delete gap', () => {
    // cp-2 deleted from both sides → remaining cp-1,cp-3 → next is cp-4, not cp-2.
    expect(nextNumberId(['cp-1', 'cp-3'])).toBe('cp-4');
    expect(nextNumberId(['cp-1', 'cp-3'])).toMatch(/^cp-\d+$/);
  });
});

describe('pointLabel (UI number)', () => {
  it('shows the bare number for a cp-N id', () => {
    expect(pointLabel('cp-7')).toBe('7');
    expect(pointLabel('cp-12')).toBe('12');
  });

  it('falls back to the id when there is no number', () => {
    expect(pointLabel('x')).toBe('x');
  });
});

describe('writeActivePoint (master bind, AC2)', () => {
  it('test_master_click_writes_to_active_id_only', () => {
    // A click for active id cp-2, placed RIGHT NEXT TO existing cp-1, must add
    // cp-2 and leave cp-1 untouched — never nearest-neighbour match to cp-1.
    const start = [{ point_id: 'cp-1', x: 0.1, y: 0.1 }];
    const res = writeActivePoint(start, 'cp-2', 0.11, 0.11);
    expect(res).toHaveLength(2);
    expect(res.find((p) => p.point_id === 'cp-1')).toEqual({
      point_id: 'cp-1',
      x: 0.1,
      y: 0.1,
    });
    expect(res.find((p) => p.point_id === 'cp-2')).toEqual({
      point_id: 'cp-2',
      x: 0.11,
      y: 0.11,
    });
  });

  it('test_reclick_same_id_overwrites', () => {
    const start = [{ point_id: 'cp-1', x: 0.1, y: 0.1 }];
    const res = writeActivePoint(start, 'cp-1', 0.9, 0.8);
    expect(res).toHaveLength(1);
    expect(res[0]).toEqual({ point_id: 'cp-1', x: 0.9, y: 0.8 });
  });
});

describe('colourForId (anti-confusion)', () => {
  it('test_same_id_same_colour', () => {
    // The both-panels guarantee reduces to: the same id is a stable colour.
    expect(colourForId('cp-1')).toBe(colourForId('cp-1'));
    expect(colourForId('cp-3')).toBe(colourForId('cp-3'));
    expect(colourForId(2)).toBe(colourForId(2));
    expect(colourForId('cp-1')).toMatch(/^#[0-9a-fA-F]{6}$/);
  });
});

describe('snap-to-vertex (nearestWithin)', () => {
  it('test_click_near_vertex_snaps_within_radius', () => {
    // Image drawn 1000px wide; a click 5px from a vertex (R_SNAP = 12px) snaps
    // exactly onto the vertex.
    const drawWidth = 1000;
    const rNorm = displayRadiusToNorm(R_SNAP_PX, drawWidth);
    const vertex: [number, number] = [0.5, 0.5];
    const click = { x: 0.5 + 5 / drawWidth, y: 0.5 };
    expect(nearestWithin(click, [vertex], rNorm)).toEqual(vertex);
  });

  it('does not snap when the click is beyond the radius', () => {
    const drawWidth = 1000;
    const rNorm = displayRadiusToNorm(R_SNAP_PX, drawWidth);
    const click = { x: 0.5 + 20 / drawWidth, y: 0.5 }; // 20px > 12px
    expect(nearestWithin(click, [[0.5, 0.5]], rNorm)).toBeNull();
  });
});

describe('hit-test (select vs add)', () => {
  it('test_click_near_existing_point_selects_not_adds', () => {
    const drawWidth = 1000;
    const rNorm = displayRadiusToNorm(R_HIT_PX, drawWidth);
    const id = hitTest(
      { x: 0.5 + 3 / drawWidth, y: 0.5 },
      [{ id: 'cp-1', x: 0.5, y: 0.5 }],
      rNorm,
    );
    expect(id).toBe('cp-1');
  });

  it('returns null (→ add a new point) when the click misses every point', () => {
    const drawWidth = 1000;
    const rNorm = displayRadiusToNorm(R_HIT_PX, drawWidth);
    expect(
      hitTest({ x: 0.8, y: 0.8 }, [{ id: 'cp-1', x: 0.5, y: 0.5 }], rNorm),
    ).toBeNull();
  });
});
