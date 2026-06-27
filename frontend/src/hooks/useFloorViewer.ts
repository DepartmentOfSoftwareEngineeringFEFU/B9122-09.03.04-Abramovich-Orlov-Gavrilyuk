import { useState, useCallback, useEffect, useMemo } from 'react';
import { buildingsApi } from '../api/buildingsApi';
import { navigationApi } from '../api/apiService';
import type { PublicBuilding } from '../types/hierarchy';
import type { PathSegment3D } from '../types/transitions';

// Format: building code (Latin/Cyrillic letters) + room number digits, e.g. "D304", "Д304"
const ROOM_REF_RE = /^[A-Za-zА-Яа-яЁё]+\d+$/;

// ---- Derived types for the catalog (denormalized) ----
export interface FloorPublic {
  id: number;
  number: number;
  schema_image_url: string | null;
  wall_polygons: [number, number][][] | null;
  sections: SectionPublic[];
}

export interface SectionPublic {
  id: number;
  number: number;
  geometry: { points: [number, number][] };
  reconstruction_id: number;
  mesh_url_glb: string;
  section_type: number;
}

export interface UseFloorViewerReturn {
  catalog: PublicBuilding[];
  isLoading: boolean;
  error: string | null;

  selectedBuildingId: number | null;
  selectedFloorId: number | null;
  selectedSectionId: number | null;

  visibleFloors: FloorPublic[];
  visibleSections: SectionPublic[];
  activeMeshUrl: string | null;

  selectBuilding: (id: number) => void;
  selectFloor: (id: number) => void;
  selectSection: (id: number) => void;

  // routing
  planRoute: (start: string, end: string) => Promise<void>;
  routeSegments: PathSegment3D[] | null;
  routeError: string | null;
  highlightedSectionIds: number[];
}

// Build a reverse index: reconstructionId → sectionId
function buildReconToSectionIndex(catalog: PublicBuilding[]): Map<number, number> {
  const index = new Map<number, number>();
  for (const building of catalog) {
    for (const floor of building.floors) {
      for (const section of floor.sections) {
        index.set(section.reconstruction_id, section.id);
      }
    }
  }
  return index;
}

export const useFloorViewer = (): UseFloorViewerReturn => {
  const [catalog, setCatalog] = useState<PublicBuilding[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(null);
  const [selectedFloorId, setSelectedFloorId] = useState<number | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState<number | null>(null);

  const [routeSegments, setRouteSegments] = useState<PathSegment3D[] | null>(null);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [highlightedSectionIds, setHighlightedSectionIds] = useState<number[]>([]);

  // Load catalog on mount
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    buildingsApi.listPublished()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data);
          // Auto-select first building
          if (data.length > 0) {
            const firstBuilding = data[0];
            const firstFloor = firstBuilding.floors[0] ?? null;
            const firstSection = firstFloor?.sections[0] ?? null;
            setSelectedBuildingId(firstBuilding.id);
            setSelectedFloorId(firstFloor?.id ?? null);
            setSelectedSectionId(firstSection?.id ?? null);
          }
        }
      })
      .catch(() => {
        if (!cancelled) setError('Ошибка загрузки каталога');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  // Derived: floors of the selected building
  const visibleFloors = useMemo((): FloorPublic[] => {
    if (selectedBuildingId === null) return [];
    const building = catalog.find((b) => b.id === selectedBuildingId);
    if (!building) return [];
    return building.floors as FloorPublic[];
  }, [catalog, selectedBuildingId]);

  // Derived: sections of the selected floor
  const visibleSections = useMemo((): SectionPublic[] => {
    if (selectedFloorId === null) return [];
    const floor = visibleFloors.find((f) => f.id === selectedFloorId);
    if (!floor) return [];
    return floor.sections;
  }, [visibleFloors, selectedFloorId]);

  // Derived: mesh URL for the active section
  const activeMeshUrl = useMemo((): string | null => {
    if (selectedSectionId === null) return null;
    const section = visibleSections.find((s) => s.id === selectedSectionId);
    return section?.mesh_url_glb ?? null;
  }, [visibleSections, selectedSectionId]);

  // Reverse index for routing
  const reconToSectionIndex = useMemo(
    () => buildReconToSectionIndex(catalog),
    [catalog],
  );

  const selectBuilding = useCallback(
    (id: number) => {
      setSelectedBuildingId(id);
      setRouteSegments(null);
      setHighlightedSectionIds([]);

      const building = catalog.find((b) => b.id === id);
      const firstFloor = building?.floors[0] ?? null;
      const firstSection = firstFloor?.sections[0] ?? null;
      setSelectedFloorId(firstFloor?.id ?? null);
      setSelectedSectionId(firstSection?.id ?? null);
    },
    [catalog],
  );

  const selectFloor = useCallback(
    (id: number) => {
      setSelectedFloorId(id);
      setRouteSegments(null);
      setHighlightedSectionIds([]);

      const building = catalog.find((b) => b.id === selectedBuildingId);
      const floor = building?.floors.find((f) => f.id === id);
      if (!floor) {
        setSelectedSectionId(null);
        return;
      }

      // fallback: keep the same section number if possible; otherwise first
      const currentSectionNumber = visibleSections.find(
        (s) => s.id === selectedSectionId,
      )?.number ?? null;

      const sameNumberSection =
        currentSectionNumber !== null
          ? floor.sections.find((s) => s.number === currentSectionNumber) ?? null
          : null;

      const fallbackSection = floor.sections[0] ?? null;
      const target = sameNumberSection ?? fallbackSection;
      setSelectedSectionId(target?.id ?? null);
    },
    [catalog, selectedBuildingId, selectedSectionId, visibleSections],
  );

  const selectSection = useCallback((id: number) => {
    setSelectedSectionId(id);
  }, []);

  const planRoute = useCallback(
    async (start: string, end: string): Promise<void> => {
      setRouteError(null);
      setRouteSegments(null);
      setHighlightedSectionIds([]);

      const startTrim = start.trim();
      const endTrim = end.trim();

      if (!ROOM_REF_RE.test(startTrim) || !ROOM_REF_RE.test(endTrim)) {
        setRouteError('Формат: код корпуса + номер комнаты, например D304');
        return;
      }

      // Find building for start
      // "D304" → building code "D", room id "304"
      // We find the building code by looking through the catalog for a matching section
      const findReconAndRoomByLabel = (
        label: string,
      ): { buildingId: number; buildingCode: string; reconId: number; roomId: string } | null => {
        // Try to extract building code prefix then room number
        // Label can be "D304" where "D" is building code and "304" is room id
        // or simply a room id with no building prefix
        for (const building of catalog) {
          if (label.toLowerCase().startsWith(building.code.toLowerCase())) {
            const roomPart = label.slice(building.code.length);
            for (const floor of building.floors) {
              for (const section of floor.sections) {
                return {
                  buildingId: building.id,
                  buildingCode: building.code,
                  reconId: section.reconstruction_id,
                  roomId: roomPart,
                };
              }
            }
          }
        }
        return null;
      };

      const fromInfo = findReconAndRoomByLabel(startTrim);
      const toInfo = findReconAndRoomByLabel(endTrim);

      if (!fromInfo || !toInfo) {
        setRouteError('Не удалось определить комнаты. Формат: "<Корпус><Комната>" (например D304)');
        return;
      }

      if (fromInfo.buildingCode !== toInfo.buildingCode) {
        setRouteError('Начало и конец маршрута должны быть в одном корпусе');
        return;
      }

      try {
        const result = await navigationApi.multifloorRoute({
          building_id: fromInfo.buildingCode,
          from_reconstruction_id: fromInfo.reconId,
          from_room_id: fromInfo.roomId,
          to_reconstruction_id: toInfo.reconId,
          to_room_id: toInfo.roomId,
        });

        if (result.status === 'success') {
          setRouteSegments(result.path_segments);

          // Map reconstruction_id → section_id for each segment
          const sectionIds = result.path_segments
            .map((seg) => reconToSectionIndex.get(seg.reconstruction_id))
            .filter((id): id is number => id !== undefined);
          setHighlightedSectionIds(sectionIds);
        } else {
          setRouteError(result.message ?? 'Маршрут не найден');
        }
      } catch {
        setRouteError('Ошибка при построении маршрута');
      }
    },
    [catalog, reconToSectionIndex],
  );

  return {
    catalog,
    isLoading,
    error,
    selectedBuildingId,
    selectedFloorId,
    selectedSectionId,
    visibleFloors,
    visibleSections,
    activeMeshUrl,
    selectBuilding,
    selectFloor,
    selectSection,
    planRoute,
    routeSegments,
    routeError,
    highlightedSectionIds,
  };
};
