import type { TransitionLink, TransitionOverride } from '../types/buildingNav';

/** Stable identity key for a link / override (lower → upper endpoints). */
export function linkKey(o: {
  lower_floor_id: number;
  lower_node: string;
  upper_floor_id: number;
  upper_node: string;
}): string {
  return `${o.lower_floor_id}:${o.lower_node}->${o.upper_floor_id}:${o.upper_node}`;
}

/**
 * Toggle one override on/off in the pending set. Applying the SAME action to a
 * link that already carries it removes the override (un-override → back to auto);
 * otherwise it replaces any existing override for that link with the new action.
 * Full-replace semantics — the returned array is the complete override set.
 * Pure — no side effects (unit-testable).
 */
export function applyLinkOverride(
  overrides: TransitionOverride[],
  link: TransitionLink,
  action: 'disable' | 'force',
): TransitionOverride[] {
  const key = linkKey(link);
  const existing = overrides.find((o) => linkKey(o) === key);
  const without = overrides.filter((o) => linkKey(o) !== key);
  if (existing && existing.action === action) {
    return without;
  }
  return [
    ...without,
    {
      lower_floor_id: link.lower_floor_id,
      lower_node: link.lower_node,
      upper_floor_id: link.upper_floor_id,
      upper_node: link.upper_node,
      action,
    },
  ];
}

/** The override pending for a link, if any (drives the toggle's checked state). */
export function pendingAction(
  overrides: TransitionOverride[],
  link: TransitionLink,
): 'disable' | 'force' | null {
  const found = overrides.find((o) => linkKey(o) === linkKey(link));
  return found ? found.action : null;
}
