import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import {
  fromRoomAnnotation,
  fromVectorRoom,
  normalizedToWorld,
  ROOM_COLORS,
} from '../types/roomDisplay';
import type { RoomAnnotation } from '../types/wizard';
import type { VectorRoomApi } from '../types/roomDisplay';

// Helpers

function makeAnnotation(overrides: Partial<RoomAnnotation> = {}): RoomAnnotation {
  return {
    id: 'r1',
    name: 'Room 1',
    room_type: 'room',
    x: 0.1,
    y: 0.2,
    width: 0.3,
    height: 0.4,
    ...overrides,
  };
}

function makeVectorRoom(overrides: Partial<VectorRoomApi> = {}): VectorRoomApi {
  return {
    id: 'vr1',
    name: 'VR 1',
    room_type: 'corridor',
    center: { x: 0.5, y: 0.6 },
    polygon: [
      { x: 0.1, y: 0.2 },
      { x: 0.7, y: 0.2 },
      { x: 0.7, y: 0.8 },
      { x: 0.1, y: 0.8 },
    ],
    area_normalized: 0.36,
    ...overrides,
  };
}

function makeBox(
  minX: number, minY: number, minZ: number,
  maxX: number, maxY: number, maxZ: number,
): THREE.Box3 {
  return new THREE.Box3(
    new THREE.Vector3(minX, minY, minZ),
    new THREE.Vector3(maxX, maxY, maxZ),
  );
}

// fromRoomAnnotation

describe('fromRoomAnnotation', () => {
  it('prefers explicit center when provided', () => {
    const r = makeAnnotation({ center: { x: 0.55, y: 0.65 } });
    const d = fromRoomAnnotation(r);
    expect(d.center_x).toBeCloseTo(0.55);
    expect(d.center_y).toBeCloseTo(0.65);
  });

  it('computes center from bbox when center is absent', () => {
    const r = makeAnnotation({ x: 0.1, y: 0.2, width: 0.3, height: 0.4 });
    const d = fromRoomAnnotation(r);
    expect(d.center_x).toBeCloseTo(0.1 + 0.3 / 2);
    expect(d.center_y).toBeCloseTo(0.2 + 0.4 / 2);
  });

  it('assigns correct color for known room_type (elevator)', () => {
    const r = makeAnnotation({ room_type: 'elevator' });
    const d = fromRoomAnnotation(r);
    expect(d.color).toBe(ROOM_COLORS.elevator);
    expect(d.color).toBe('#6A1B9A');
  });

  it('falls back to other color for unknown room_type', () => {
    const r = makeAnnotation({ room_type: 'warehouse' as RoomAnnotation['room_type'] });
    const d = fromRoomAnnotation(r);
    expect(d.color).toBe(ROOM_COLORS.other);
  });

  it('copies id, name, room_type, width_norm, height_norm', () => {
    const r = makeAnnotation({ id: 'x42', name: 'Lab', room_type: 'staircase', width: 0.25, height: 0.15 });
    const d = fromRoomAnnotation(r);
    expect(d.id).toBe('x42');
    expect(d.name).toBe('Lab');
    expect(d.room_type).toBe('staircase');
    expect(d.width_norm).toBeCloseTo(0.25);
    expect(d.height_norm).toBeCloseTo(0.15);
  });
});

// fromVectorRoom

describe('fromVectorRoom', () => {
  it('copies center coords directly', () => {
    const r = makeVectorRoom({ center: { x: 0.3, y: 0.7 } });
    const d = fromVectorRoom(r);
    expect(d.center_x).toBeCloseTo(0.3);
    expect(d.center_y).toBeCloseTo(0.7);
  });

  it('computes width and height from polygon bounding box', () => {
    const r = makeVectorRoom();
    // polygon: x in [0.1, 0.7], y in [0.2, 0.8]
    const d = fromVectorRoom(r);
    expect(d.width_norm).toBeCloseTo(0.7 - 0.1);
    expect(d.height_norm).toBeCloseTo(0.8 - 0.2);
  });

  it('returns zero size for empty polygon', () => {
    const r = makeVectorRoom({ polygon: [] });
    const d = fromVectorRoom(r);
    expect(d.width_norm).toBe(0);
    expect(d.height_norm).toBe(0);
  });
});

// normalizedToWorld

describe('normalizedToWorld', () => {
  it('lerps x over box x range', () => {
    const box = makeBox(0, 0, 0, 10, 3, 8);
    const [x] = normalizedToWorld(0.5, 0, box, 3);
    expect(x).toBeCloseTo(5);
  });

  it('lerps z over box z range', () => {
    const box = makeBox(0, 0, -8, 10, 3, 0);
    const [, , z] = normalizedToWorld(0, 0.5, box, 3);
    expect(z).toBeCloseTo(-4);
  });

  it('places y at mid wall height above box.min.y', () => {
    const box = makeBox(0, -0.1, 0, 10, 3, 8);
    const wallHeight = 3.0;
    const [, y] = normalizedToWorld(0, 0, box, wallHeight);
    expect(y).toBeCloseTo(-0.1 + wallHeight * 0.5);
  });
});
