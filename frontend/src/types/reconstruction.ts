export interface RoomLabel {
  id: string;
  name: string;
  room_type: 'classroom' | 'corridor' | 'staircase' | 'toilet' | 'other';
  center_x: number;
  center_y: number;
  color: string;
}

export interface ReconstructionDetail {
  id: number;
  name: string | null;
  status: number;
  url: string | null;
  error_message: string | null;
  room_labels: RoomLabel[];
}
