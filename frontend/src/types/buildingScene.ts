// TypeScript contract for the stacked 3D building viewer (subfeature B).

// Metric, Three.js-ready transform applied frontend-side as group.scale /
// group.rotation.y / group.position (Y-up, X-Z ground). `ty` equals `elevation_m`.
export interface ScenePlacement {
  scale: number;
  rotation_y_rad: number;
  tx: number;
  ty: number;
  tz: number;
}

export interface SceneFloor {
  floor_id: number;
  number: number;
  elevation_m: number;
  has_mesh: boolean;
  // ready GLB URL, or null when the floor has no assembled mesh
  mesh_url: string | null;
  // null when the floor is unsolved/unlinked (skipped in the scene); the
  // reference floor always gets an identity placement
  placement: ScenePlacement | null;
}

export interface BuildingScene3DResponse {
  building_id: number;
  // lowest floor (the world-frame origin); null when the building has no floors
  reference_floor_id: number | null;
  // FLOOR_HEIGHT echoed so the frontend never hardcodes it
  floor_height_m: number;
  // ordered by `number` ASC
  floors: SceneFloor[];
}
