import type { RoomAnnotation, TransitionSpec } from '../../types/wizard';

export interface BuildRoomAnnotationArgs {
  id: string;
  name: string;
  roomType: RoomAnnotation['room_type'];
  x: number;
  y: number;
  width: number;
  height: number;
  transition?: TransitionSpec;
}

/**
 * Build a RoomAnnotation from a drawn rectangle plus an optional transition
 * spec. Elevator floor-link fields (floor_from/floor_to/floors_excluded) are
 * spread in only for `kind === 'elevator'`; stair directional gates
 * (connects_up/connects_down, multifloor-routing D) only for `kind === 'stairs'`;
 * plain rooms carry none. Pure — no fabric, no side effects (unit-testable).
 */
export function buildRoomAnnotation(args: BuildRoomAnnotationArgs): RoomAnnotation {
  const { id, name, roomType, x, y, width, height, transition } = args;
  const annotation: RoomAnnotation = {
    id,
    name,
    room_type: roomType,
    x,
    y,
    width,
    height,
  };
  if (transition?.kind === 'elevator') {
    annotation.floor_from = transition.floor_from;
    annotation.floor_to = transition.floor_to;
    annotation.floors_excluded = transition.floors_excluded;
  }
  if (transition?.kind === 'stairs') {
    annotation.connects_up = transition.connects_up;
    annotation.connects_down = transition.connects_down;
  }
  return annotation;
}
