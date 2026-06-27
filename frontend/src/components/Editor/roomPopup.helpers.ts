import type { TransitionSpec } from '../../types/wizard';

export type PopupRoomType = 'room' | 'staircase' | 'elevator' | 'corridor';

export const TYPE_LABELS: Record<PopupRoomType, string> = {
  room: 'Кабинет',
  staircase: 'Лестница',
  elevator: 'Лифт',
  corridor: 'Коридор',
};

/** Parse a comma/space-separated string into a list of integers. */
export function parseExcludedFloors(raw: string): number[] {
  return raw
    .split(/[\s,]+/)
    .map((token) => token.trim())
    .filter((token) => token.length > 0)
    .map((token) => Number(token))
    .filter((value) => Number.isInteger(value));
}

export interface ElevatorValidation {
  valid: boolean;
  from: number;
  to: number;
  excluded: number[];
  hint: string | null;
}

/**
 * Validate the elevator popup inputs (raw strings from the form fields).
 * `from`/`to` must be integers >= 1 with from <= to; every excluded floor must
 * fall inside [from, to]. Returns parsed values plus an inline hint on failure.
 * Pure — no DOM, no side effects.
 */
export function validateElevator(
  floorFrom: string,
  floorTo: string,
  excludedRaw: string,
): ElevatorValidation {
  const from = Number(floorFrom);
  const to = Number(floorTo);
  const excluded = parseExcludedFloors(excludedRaw);

  const fromValid = floorFrom.trim() !== '' && Number.isInteger(from) && from >= 1;
  const toValid = floorTo.trim() !== '' && Number.isInteger(to) && to >= 1;
  const rangeValid = fromValid && toValid && from <= to;
  const excludedValid =
    rangeValid && excluded.every((value) => value >= from && value <= to);
  const valid = rangeValid && excludedValid;

  let hint: string | null = null;
  if (fromValid && toValid && from > to) {
    hint = 'С ≤ По';
  } else if (rangeValid && !excludedValid) {
    hint = `Исключённые этажи должны быть в диапазоне ${from}–${to}`;
  }

  return { valid, from, to, excluded, hint };
}

export interface StairGates {
  connects_up: boolean;
  connects_down: boolean;
}

/**
 * Resolve the stair directional gates from the two toggle states
 * (multifloor-routing, D). Both default ON — a plain staircase connects the
 * floor above and below. Turning one off marks a stair that tops/bottoms out.
 * Pure — no DOM, no side effects.
 */
export function resolveStairGates(
  connectsUp: boolean,
  connectsDown: boolean,
): StairGates {
  return { connects_up: connectsUp, connects_down: connectsDown };
}

export interface ConfirmPayload {
  name: string;
  transition?: TransitionSpec;
}

/**
 * Resolve the (name, transition?) payload emitted on popup confirm for a given
 * room type. Returns null when the input is invalid (caller should block
 * confirm). Pure — no DOM, no side effects.
 */
export function resolveConfirmPayload(
  roomType: PopupRoomType,
  nameInput: string,
  floorFrom = '',
  floorTo = '',
  excludedRaw = '',
  connectsUp = true,
  connectsDown = true,
): ConfirmPayload | null {
  if (roomType === 'elevator') {
    const v = validateElevator(floorFrom, floorTo, excludedRaw);
    if (!v.valid) return null;
    return {
      name: TYPE_LABELS.elevator,
      transition: {
        kind: 'elevator',
        floor_from: v.from,
        floor_to: v.to,
        floors_excluded: v.excluded,
      },
    };
  }
  if (roomType === 'staircase') {
    return {
      name: TYPE_LABELS.staircase,
      transition: { kind: 'stairs', ...resolveStairGates(connectsUp, connectsDown) },
    };
  }
  if (roomType === 'room') {
    const name = nameInput.trim();
    if (!name) return null;
    return { name };
  }
  // corridor: fixed label, no transition
  return { name: TYPE_LABELS[roomType] };
}
