import { describe, it, expect } from 'vitest';
import {
  resolveConfirmPayload,
  validateElevator,
  parseExcludedFloors,
} from './roomPopup.helpers';

// The popup renders per room type and emits (name, transition?) on confirm.
// The vitest env here is `node` (no jsdom render / no @testing-library), so the
// per-type body + validation logic is exercised through the pure helpers that
// the component delegates to.

describe('RoomPopup logic', () => {
  it('renders elevator floor inputs', () => {
    // Elevator branch consumes from/to/excluded inputs and validates them.
    const v = validateElevator('1', '10', '5');
    expect(v.valid).toBe(true);
    expect(v.from).toBe(1);
    expect(v.to).toBe(10);
    expect(v.excluded).toEqual([5]);
    expect(parseExcludedFloors('5, 7 9')).toEqual([5, 7, 9]);
  });

  it('staircase shows adjacency note, gates default on', () => {
    // No floor inputs are read for stairs; confirm emits a stairs transition
    // carrying the directional gates (default both on, multifloor-routing D).
    const payload = resolveConfirmPayload('staircase', '', '', '');
    expect(payload).not.toBeNull();
    expect(payload?.name).toBe('Лестница');
    expect(payload?.transition).toEqual({
      kind: 'stairs',
      connects_up: true,
      connects_down: true,
    });
  });

  it('room shows name input', () => {
    // Room uses the typed name; blank name blocks confirm.
    const named = resolveConfirmPayload('room', '301', '', '');
    expect(named).toEqual({ name: '301' });
    expect(named?.transition).toBeUndefined();
    expect(resolveConfirmPayload('room', '   ', '', '')).toBeNull();
  });

  it('blocks confirm when from > to', () => {
    const v = validateElevator('8', '3', '');
    expect(v.valid).toBe(false);
    expect(v.hint).toBe('С ≤ По');
    expect(resolveConfirmPayload('elevator', '', '8', '3', '')).toBeNull();
  });

  it('confirm emits transition payload', () => {
    const payload = resolveConfirmPayload('elevator', '', '1', '10', '5');
    expect(payload).toEqual({
      name: 'Лифт',
      transition: {
        kind: 'elevator',
        floor_from: 1,
        floor_to: 10,
        floors_excluded: [5],
      },
    });
  });

  it('blocks confirm when excluded floor is outside the range', () => {
    const v = validateElevator('1', '5', '9');
    expect(v.valid).toBe(false);
    expect(resolveConfirmPayload('elevator', '', '1', '5', '9')).toBeNull();
  });
});
