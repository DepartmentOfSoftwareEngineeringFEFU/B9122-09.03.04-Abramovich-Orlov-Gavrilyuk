import { describe, it, expect } from 'vitest';
import {
  applyLinkOverride,
  pendingAction,
  linkKey,
} from '../useTransitionLinks.helpers';
import type { TransitionLink } from '../../types/buildingNav';

const LINK: TransitionLink = {
  lower_floor_id: 10,
  lower_floor_number: 1,
  lower_node: 'room_s1',
  upper_floor_id: 20,
  upper_floor_number: 2,
  upper_node: 'room_s2',
  type: 'staircase',
  source: 'auto',
  enabled: true,
  distance_m: 0.4,
};

describe('applyLinkOverride', () => {
  it('test_link_override_toggle: disable adds, re-disable removes', () => {
    const once = applyLinkOverride([], LINK, 'disable');
    expect(once).toHaveLength(1);
    expect(once[0].action).toBe('disable');
    expect(pendingAction(once, LINK)).toBe('disable');

    const twice = applyLinkOverride(once, LINK, 'disable');
    expect(twice).toHaveLength(0);
    expect(pendingAction(twice, LINK)).toBeNull();
  });

  it('switching action replaces the override (no duplicate)', () => {
    const disabled = applyLinkOverride([], LINK, 'disable');
    const forced = applyLinkOverride(disabled, LINK, 'force');
    expect(forced).toHaveLength(1);
    expect(forced[0].action).toBe('force');
  });

  it('the override carries only the four endpoint fields + action', () => {
    const [ovr] = applyLinkOverride([], LINK, 'disable');
    expect(ovr).toEqual({
      lower_floor_id: 10,
      lower_node: 'room_s1',
      upper_floor_id: 20,
      upper_node: 'room_s2',
      action: 'disable',
    });
    expect(linkKey(ovr)).toBe(linkKey(LINK));
  });
});
