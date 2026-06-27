export interface ReconstructionCard {
  id: number;
  name: string;
  url: string | null;
  preview_url: string | null;
  original_image_url: string | null;
  status: number;
  rotation_angle: number;
}

export interface BuildingReconstructionGroup {
  buildingId: string;
  reconstructions: ReconstructionCard[];
}

export interface BuildingTransitionsSummary {
  buildingId: string;
  floors: Array<{
    id: number;
    number: number;
    reconstructions: ReconstructionCard[];
  }>;
}
