import { describe, it, expect } from 'vitest';
import {
  buildMultifloorRoutePayload,
  extractApiDetail,
} from '../useMultifloorRoute.helpers';

describe('buildMultifloorRoutePayload', () => {
  it('test_build_route_payload_shape: maps complete state, trims rooms', () => {
    const payload = buildMultifloorRoutePayload({
      fromFloorId: 10,
      fromRoom: '  A  ',
      toFloorId: 20,
      toRoom: 'B',
    });
    expect(payload).toEqual({
      from_floor_id: 10,
      from_room: 'A',
      to_floor_id: 20,
      to_room: 'B',
    });
  });

  it('returns null when a floor or room is missing', () => {
    expect(
      buildMultifloorRoutePayload({
        fromFloorId: null,
        fromRoom: 'A',
        toFloorId: 20,
        toRoom: 'B',
      }),
    ).toBeNull();
    expect(
      buildMultifloorRoutePayload({
        fromFloorId: 10,
        fromRoom: '   ',
        toFloorId: 20,
        toRoom: 'B',
      }),
    ).toBeNull();
  });
});

describe('extractApiDetail', () => {
  it('reads response.data.detail when present, else the fallback', () => {
    expect(
      extractApiDetail({ response: { data: { detail: 'нет графа' } } }, 'fb'),
    ).toBe('нет графа');
    expect(extractApiDetail(new Error('x'), 'fallback')).toBe('fallback');
  });
});
