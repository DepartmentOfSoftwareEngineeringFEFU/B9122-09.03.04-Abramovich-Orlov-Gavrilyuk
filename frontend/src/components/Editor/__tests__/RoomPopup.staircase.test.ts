import { describe, it, expect } from 'vitest';
import { resolveStairGates, resolveConfirmPayload } from '../roomPopup.helpers';

// vitest runs env: node with no @testing-library/react → test the pure helpers
// extracted from RoomPopup (the project's established escape hatch), not JSX.
describe('resolveStairGates', () => {
  it('test_stair_gates_default_on_toggle_off: defaults on; toggle flips one', () => {
    expect(resolveStairGates(true, true)).toEqual({
      connects_up: true,
      connects_down: true,
    });
    expect(resolveStairGates(false, true)).toEqual({
      connects_up: false,
      connects_down: true,
    });
    expect(resolveStairGates(true, false)).toEqual({
      connects_up: true,
      connects_down: false,
    });
  });

  it('staircase confirm payload carries the gates', () => {
    const payload = resolveConfirmPayload(
      'staircase',
      '',
      '',
      '',
      '',
      false,
      true,
    );
    expect(payload).not.toBeNull();
    expect(payload?.transition).toEqual({
      kind: 'stairs',
      connects_up: false,
      connects_down: true,
    });
  });

  it('staircase defaults to both gates on when toggles omitted', () => {
    const payload = resolveConfirmPayload('staircase', '');
    expect(payload?.transition).toEqual({
      kind: 'stairs',
      connects_up: true,
      connects_down: true,
    });
  });
});
