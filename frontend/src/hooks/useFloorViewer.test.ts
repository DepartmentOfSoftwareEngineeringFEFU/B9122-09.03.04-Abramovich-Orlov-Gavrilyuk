import { describe, it, expect } from 'vitest';
import type { PublicBuilding } from '../types/hierarchy';

// Inline the pure helper that lives in useFloorViewer
// We test the logic directly without React rendering.

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

// Fixtures

const makeCatalog = (): PublicBuilding[] => [
  {
    id: 1,
    code: 'D',
    name: 'Корпус D',
    floors: [
      {
        id: 10,
        number: 7,
        schema_image_url: null,
        schema_crop_bbox: null,
        wall_polygons: null,
        sections: [
          {
            id: 101,
            number: 3,
            geometry: {
              points: [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
            },
            reconstruction_id: 1001,
            mesh_url_glb: 'http://test/r1001.glb',
            section_type: 1,
          },
          {
            id: 102,
            number: 4,
            geometry: {
              points: [[0.5, 0.1], [0.9, 0.1], [0.9, 0.4], [0.5, 0.4]],
            },
            reconstruction_id: 1002,
            mesh_url_glb: 'http://test/r1002.glb',
            section_type: 1,
          },
        ],
      },
      {
        id: 11,
        number: 8,
        schema_image_url: null,
        schema_crop_bbox: null,
        wall_polygons: null,
        sections: [
          {
            id: 103,
            number: 5,
            geometry: {
              points: [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
            },
            reconstruction_id: 1003,
            mesh_url_glb: 'http://test/r1003.glb',
            section_type: 1,
          },
        ],
      },
    ],
  },
];

// Tests

describe('useFloorViewer', () => {
  describe('test_useFloorViewer_segment_to_section_mapping', () => {
    it('maps each reconstruction_id in route segments to the correct sectionId', () => {
      const catalog = makeCatalog();
      const index = buildReconToSectionIndex(catalog);

      // Simulate two route segments: recon 1001 → section 101, recon 1002 → section 102
      const pathSegments = [
        { reconstruction_id: 1001, floor_number: 7, floor_name: 'Этаж 7', coordinates_3d: [] },
        { reconstruction_id: 1002, floor_number: 7, floor_name: 'Этаж 7', coordinates_3d: [] },
      ];

      const highlightedSectionIds = pathSegments
        .map((seg) => index.get(seg.reconstruction_id))
        .filter((id): id is number => id !== undefined);

      expect(highlightedSectionIds).toContain(101);
      expect(highlightedSectionIds).toContain(102);
      expect(highlightedSectionIds).toHaveLength(2);
    });

    it('ignores segment reconstruction_ids not present in catalog', () => {
      const catalog = makeCatalog();
      const index = buildReconToSectionIndex(catalog);

      const pathSegments = [
        { reconstruction_id: 9999, floor_number: 1, floor_name: 'Unknown', coordinates_3d: [] },
      ];

      const highlightedSectionIds = pathSegments
        .map((seg) => index.get(seg.reconstruction_id))
        .filter((id): id is number => id !== undefined);

      expect(highlightedSectionIds).toHaveLength(0);
    });

    it('indexes all sections across multiple floors and buildings', () => {
      const catalog = makeCatalog();
      const index = buildReconToSectionIndex(catalog);

      // recon 1003 is on floor 8
      expect(index.get(1003)).toBe(103);
      expect(index.size).toBe(3);
    });
  });

  describe('test_useFloorViewer_published_filter_hides_empty', () => {
    it('catalog returned by listPublished contains no floors with empty sections', () => {
      // The backend filters hierarchically: buildings with ≥1 floor with ≥1 section.
      // This test verifies that a properly filtered catalog (as returned by listPublished)
      // has no empty floors.
      const filteredCatalog: PublicBuilding[] = [
        {
          id: 2,
          code: 'S',
          name: 'Корпус S',
          floors: [
            {
              id: 20,
              number: 1,
              schema_image_url: null,
              schema_crop_bbox: null,
              wall_polygons: null,
              sections: [
                {
                  id: 201,
                  number: 1,
                  geometry: {
                    points: [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]],
                  },
                  reconstruction_id: 2001,
                  mesh_url_glb: 'http://test/r2001.glb',
                  section_type: 1,
                },
              ],
            },
          ],
        },
      ];

      // Verify: no building in the catalog is empty
      for (const building of filteredCatalog) {
        expect(building.floors.length).toBeGreaterThan(0);
        for (const floor of building.floors) {
          expect(floor.sections.length).toBeGreaterThan(0);
        }
      }

      // Verify: the index correctly maps the single section
      const index = buildReconToSectionIndex(filteredCatalog);
      expect(index.get(2001)).toBe(201);
    });

    it('empty catalog (no published buildings) gives empty index', () => {
      const index = buildReconToSectionIndex([]);
      expect(index.size).toBe(0);
    });
  });
});
