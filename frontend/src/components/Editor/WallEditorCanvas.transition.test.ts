import { describe, it, expect } from 'vitest';
import { buildRoomAnnotation } from './buildRoomAnnotation';

describe('buildRoomAnnotation', () => {
  it('pushes elevator floor fields into annotation', () => {
    const annotation = buildRoomAnnotation({
      id: 'elev_1',
      name: 'Лифт',
      roomType: 'elevator',
      x: 0.4,
      y: 0.4,
      width: 0.1,
      height: 0.1,
      transition: {
        kind: 'elevator',
        floor_from: 1,
        floor_to: 10,
        floors_excluded: [5],
      },
    });

    expect(annotation.room_type).toBe('elevator');
    expect(annotation.floor_from).toBe(1);
    expect(annotation.floor_to).toBe(10);
    expect(annotation.floors_excluded).toEqual([5]);
  });

  it('omits floor fields for stairs', () => {
    const annotation = buildRoomAnnotation({
      id: 'stair_1',
      name: 'Лестница',
      roomType: 'staircase',
      x: 0.1,
      y: 0.1,
      width: 0.1,
      height: 0.1,
      transition: { kind: 'stairs' },
    });

    expect(annotation.room_type).toBe('staircase');
    expect(annotation.floor_from).toBeUndefined();
    expect(annotation.floor_to).toBeUndefined();
    expect(annotation.floors_excluded).toBeUndefined();
  });

  it('omits floor fields for a plain room (no transition)', () => {
    const annotation = buildRoomAnnotation({
      id: 'room_1',
      name: '301',
      roomType: 'room',
      x: 0.2,
      y: 0.2,
      width: 0.1,
      height: 0.1,
    });

    expect(annotation.name).toBe('301');
    expect(annotation.floor_from).toBeUndefined();
    expect(annotation.floors_excluded).toBeUndefined();
  });
});
