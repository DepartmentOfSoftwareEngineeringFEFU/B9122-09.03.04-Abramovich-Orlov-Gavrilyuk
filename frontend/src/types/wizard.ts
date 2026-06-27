import type { ControlPoint } from './floorAssembly';

export interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type WizardStep = 1 | 2 | 3 | 4 | 5 | 6;

export interface RoomAnnotation {
  id: string;
  name: string;
  room_type: 'room' | 'staircase' | 'elevator' | 'corridor';
  x: number;
  y: number;
  width: number;
  height: number; // normalized [0,1]
  polygon?: {x: number, y: number}[];
  center?: {x: number, y: number};
  area_normalized?: number;
  // Inter-floor link data for elevators (floor-transition-tools).
  floor_from?: number;
  floor_to?: number;
  floors_excluded?: number[];
  // Stair directional gates (multifloor-routing, D). Default true on the backend.
  connects_up?: boolean;
  connects_down?: boolean;
}

// Floor-link payload emitted by RoomPopup on confirm for stairs/elevator.
export interface TransitionSpec {
  kind: 'stairs' | 'elevator';
  floor_from?: number;
  floor_to?: number;
  floors_excluded?: number[];
  // Stair gates (D) — present only for kind === 'stairs'.
  connects_up?: boolean;
  connects_down?: boolean;
}

export interface DoorAnnotation {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number; // normalized [0,1]
  room_id?: string | null;
}

export interface UploadedFile {
  id: string;
  url: string;
  name: string;
}

export interface WizardState {
  step: WizardStep;
  planFileId: string | null;
  planUrl: string | null;
  planName: string;
  maskFileId: string | null;
  editedMaskFileId: string | null;
  canvasState: any | null;
  reconstructionId: number | null;
  meshUrl: string | null;
  cropRect: CropRect | null;
  rotation: 0 | 90 | 180 | 270;
  blockSize: number;
  thresholdC: number;
  rooms: RoomAnnotation[];
  doors: DoorAnnotation[];
  controlPoints: ControlPoint[];
  nextControlPointId: number;
  navGraphId: string | null;
  isLoading: boolean;
  error: string | null;
}
