import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { StitchingState, LayerData, StitchingRequest, VectorModel, Wall, Room, Door } from '../types/stitching';
import type { ReconstructionResponse } from '../api/apiService';
import { reconstructionApi } from '../api/apiService';

interface UseStitchingReturn {
  state: StitchingState;
  loadReconstructions: (buildingId: string, floorNumber: number) => Promise<void>;
  selectPlans: (ids: string[], buildingId: string, floorNumber: number) => Promise<void>;
  nextStep: () => void;
  prevStep: () => void;
  updateLayer: (layerId: string, updates: Partial<LayerData>) => void;
  setActiveTool: (tool: 'move' | 'rotate' | 'rect_crop' | 'polygon_clip') => void;
  setSelectedLayerId: (id: string | null) => void;
  reorderLayers: (layerId: string, direction: 'up' | 'down') => void;
  restoreCanvasFromSnapshot: (snapshot: unknown) => void;
  submitStitching: (name: string) => Promise<void>;
}

export const useStitching = (): UseStitchingReturn => {
  const navigate = useNavigate();
  const [state, setState] = useState<StitchingState>({
    step: 1,
    selectedReconstructionIds: [],
    buildingId: '',
    floorNumber: 1,
    layers: [],
    activeTool: 'move',
    selectedLayerId: null,
    isLoading: false,
    error: null,
  });

  const loadReconstructions = useCallback(async (buildingId: string, floorNumber: number) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      await reconstructionApi.getReadyReconstructions(buildingId, floorNumber);
      setState((prev) => ({ ...prev, isLoading: false }));
    } catch (error) {
      setState((prev) => ({ ...prev, isLoading: false, error: String(error) }));
      throw error;
    }
  }, []);

  const selectPlans = useCallback(async (ids: string[], buildingId: string, floorNumber: number) => {
    setState((prev) => ({
      ...prev,
      selectedReconstructionIds: ids,
      buildingId,
      floorNumber,
      isLoading: true,
      error: null,
    }));

    try {
      // Fetch full reconstruction data for each selected ID
      const reconstructions = await Promise.all(
        ids.map(async (id) => {
          const numId = Number(id);
          const rec = await reconstructionApi.getReconstructionById(numId);
          try {
            const vectors = await reconstructionApi.getReconstructionVectors(numId);
            return { ...rec, vector_model: vectors };
          } catch (error) {
            console.error(`Failed to load vectors for reconstruction ${id}:`, error);
            return { ...rec, vector_model: { walls: [], rooms: [], doors: [] } };
          }
        })
      ) as Array<ReconstructionResponse & { vector_model: { rotation_angle?: number; walls: Wall[]; rooms: Room[]; doors: Door[] } }>;

      // Convert to LayerData format
      const colors = ['#FF4500', '#00CED1', '#FFD700', '#FF69B4', '#32CD32'];
      const layers: LayerData[] = reconstructions.map((rec, index) => {
        const vectorData = (rec.vector_model || { walls: [], rooms: [], doors: [] }) as VectorModel & {
          image_size_cropped?: [number, number];
          image_size_original?: [number, number];
        };

        let w = 1000;
        let h = 1000;
        if (vectorData.image_size_cropped && vectorData.image_size_cropped[0] > 0) {
          w = vectorData.image_size_cropped[0];
          h = vectorData.image_size_cropped[1];
        } else if (vectorData.image_size_original && vectorData.image_size_original[0] > 0) {
          w = vectorData.image_size_original[0];
          h = vectorData.image_size_original[1];
        }

        return {
          reconstructionId: String(rec.id),
          name: rec.name || `План ${index + 1}`,
          originalImageUrl: rec.original_image_url || '',
          previewUrl: rec.preview_url || '',
          vectorModel: vectorData,
          transform: {
            translate_x: index * 50,
            translate_y: index * 50,
            scale_x: 1,
            scale_y: 1,
            rotation_deg: 0, // Prevent double rotation, vector is relative to already rotated mask
          },
          clipPolygons: [],
          rectCrop: null,
          imageWidth: w,
          imageHeight: h,
          zIndex: index,
          color: colors[index % colors.length],
          maskOpacity: 0.4,
          showMask: true,
        };
      });

      setState((prev) => ({
        ...prev,
        layers,
        isLoading: false,
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: String(error),
      }));
      throw error;
    }
  }, []);

  const nextStep = useCallback(() => {
    setState((prev) => ({ ...prev, step: 2 as 1 | 2 }));
  }, []);

  const prevStep = useCallback(() => {
    setState((prev) => ({ ...prev, step: 1 as 1 | 2 }));
  }, []);

  const updateLayer = useCallback((layerId: string, updates: Partial<LayerData>) => {
    setState((prev) => ({
      ...prev,
      layers: prev.layers.map((layer) =>
        layer.reconstructionId === layerId ? { ...layer, ...updates } : layer
      ),
    }));
  }, []);

  const setActiveTool = useCallback((tool: 'move' | 'rotate' | 'rect_crop' | 'polygon_clip') => {
    setState((prev) => ({ ...prev, activeTool: tool }));
  }, []);

  const setSelectedLayerId = useCallback((id: string | null) => {
    setState((prev) => ({ ...prev, selectedLayerId: id }));
  }, []);

  const reorderLayers = useCallback((layerId: string, direction: 'up' | 'down') => {
    setState((prev) => {
      const layerIndex = prev.layers.findIndex((l) => l.reconstructionId === layerId);
      if (layerIndex === -1) return prev;

      // In LayerPanel, index 0 is top. 'up' means index - 1 (higher visually).
      const newIndex = direction === 'up' ? layerIndex - 1 : layerIndex + 1;
      if (newIndex < 0 || newIndex >= prev.layers.length) return prev;

      const newLayers = [...prev.layers];
      [newLayers[layerIndex], newLayers[newIndex]] = [newLayers[newIndex], newLayers[layerIndex]];

      // Reassign zIndex to strictly match array order!
      // Render components should use array order directly, but since canvas uses zIndex:
      return {
        ...prev,
        layers: newLayers.map((layer, idx) => ({ ...layer, zIndex: idx })),
      };
    });
  }, []);

  const restoreCanvasFromSnapshot = useCallback((_snapshot: unknown) => {
    return;
  }, []);

  const submitStitching = useCallback(async (name: string) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const request: StitchingRequest = {
        name,
        building_id: state.buildingId,
        floor_number: state.floorNumber,
        source_plans: state.layers.map((layer) => ({
          reconstruction_id: layer.reconstructionId,
          transform: layer.transform,
          clip_polygons: layer.clipPolygons,
          rect_crop: layer.rectCrop,
          image_width_px: layer.imageWidth,
          image_height_px: layer.imageHeight,
          z_index: layer.zIndex,
        })),
      };

      const response = await reconstructionApi.postStitching(request);

      navigate(`/admin/edit/${response.id}`);
    } catch (error) {
      setState((prev) => ({ ...prev, isLoading: false, error: String(error) }));
      throw error;
    }
  }, [state, navigate]);

  return {
    state,
    loadReconstructions,
    selectPlans,
    nextStep,
    prevStep,
    updateLayer,
    setActiveTool,
    setSelectedLayerId,
    reorderLayers,
    restoreCanvasFromSnapshot,
    submitStitching,
  };
};
