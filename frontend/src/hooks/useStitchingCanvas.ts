import { useRef, useEffect, useCallback } from 'react';
import { fabric } from 'fabric';
import type { LayerData, ClipPolygon, StitchingSnapshot } from '../types/stitching';

interface UseStitchingCanvasProps {
  containerRef: React.RefObject<HTMLDivElement>;
  layers: LayerData[];
  activeTool: 'move' | 'rotate' | 'rect_crop' | 'polygon_clip';
  selectedLayerId: string | null;
  onLayerUpdate: (layerId: string, updates: Partial<LayerData>) => void;
  onSnapshotPush: (snapshot: StitchingSnapshot) => void;
}

interface UseStitchingCanvasReturn {
  canvasRef: React.MutableRefObject<fabric.Canvas | null>;
  loadPlanToCanvas: (layer: LayerData) => void;
  removePlanFromCanvas: (layerId: string) => void;
  applyPolygonClip: (layerId: string, polygon: ClipPolygon) => void;
  applyRectCrop: (layerId: string, rect: { x: number; y: number; width: number; height: number }) => void;
  exportState: () => StitchingSnapshot;
  restoreSnapshot: (snapshot: StitchingSnapshot) => void;
}

export const useStitchingCanvas = ({
  containerRef,
  layers,
  activeTool,
  selectedLayerId,
  onLayerUpdate,
  onSnapshotPush,
}: UseStitchingCanvasProps): UseStitchingCanvasReturn => {
  const canvasRef = useRef<fabric.Canvas | null>(null);
  const layerObjectsRef = useRef<Map<string, fabric.Group>>(new Map());
  const loadingRefs = useRef<Set<string>>(new Set());
  const cropRectRef = useRef<fabric.Rect | null>(null);
  const polygonPointsRef = useRef<fabric.IPoint[]>([]);
  const polygonDotsRef = useRef<fabric.Circle[]>([]);

  // Initialize canvas
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const canvasElement = container.querySelector('canvas');
    if (!canvasElement) return;

    const canvas = new fabric.Canvas(canvasElement, {
      selection: false,
      preserveObjectStacking: true,
      backgroundColor: 'transparent', // Let parent container show grid
    });

    const updateGridCSS = () => {
      const vpt = canvas.viewportTransform;
      if (!vpt) return;
      const zoom = vpt[0];
      const panX = vpt[4];
      const panY = vpt[5];
      
      const size = 50 * zoom;
      container.style.backgroundColor = '#111';
      container.style.backgroundImage = `
        linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px)
      `;
      container.style.backgroundSize = `${size}px ${size}px`;
      container.style.backgroundPosition = `${panX}px ${panY}px`;
    };

    const updateSize = () => {
      canvas.setWidth(container.clientWidth);
      canvas.setHeight(container.clientHeight);
      canvas.renderAll();
      updateGridCSS();
    };

    updateSize();
    canvasRef.current = canvas;

    // We attach it to canvas to easily call it on pan/zoom
    (canvas as any).updateGridCSS = updateGridCSS;

    const resizeObserver = new ResizeObserver(updateSize);
    resizeObserver.observe(container);

    // Cleanup
    return () => {
      resizeObserver.disconnect();
      canvas.dispose();
      canvasRef.current = null;
      layerObjectsRef.current.clear();
      loadingRefs.current.clear();
    };
  }, [containerRef]);

  // Load plan to canvas
  const loadPlanToCanvas = useCallback((layer: LayerData) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const existingGroup = layerObjectsRef.current.get(layer.reconstructionId);
    if (existingGroup) {
      existingGroup.set({
        left: layer.transform.translate_x,
        top: layer.transform.translate_y,
        scaleX: layer.transform.scale_x,
        scaleY: layer.transform.scale_y,
        angle: layer.transform.rotation_deg,
      });
      existingGroup.setCoords();
      canvas.renderAll();
      return;
    }

    if (!layer.originalImageUrl && !layer.previewUrl || loadingRefs.current.has(layer.reconstructionId)) {
      return;
    }

    loadingRefs.current.add(layer.reconstructionId);

    const loadImg = (url: string | null | undefined): Promise<fabric.Image | null> => {
      return new Promise((resolve) => {
        if (!url) resolve(null);
        else fabric.Image.fromURL(url, (img) => resolve(img), { crossOrigin: 'anonymous' });
      });
    };

    const vm = layer.vectorModel as any;

    // Load both images
    Promise.all([
      loadImg(layer.previewUrl),
      prepareCroppedPlanImage(layer.originalImageUrl, vm.rotation_angle, vm.crop_rect).then(croppedUrl => loadImg(croppedUrl)),
    ]).then(([maskImg, planImg]) => {
      loadingRefs.current.delete(layer.reconstructionId);

      const currentCanvas = canvasRef.current;
      if (!currentCanvas || currentCanvas !== canvas) return;

      if (layerObjectsRef.current.has(layer.reconstructionId)) return;
      if (!maskImg || !maskImg.width || !maskImg.height) return;

      // Group elements array
      const elements: fabric.Object[] = [];

      // 1. Base mask (black)
      maskImg.set({ opacity: 1, visible: layer.showMask }); // Always 100% opacity if shown
      elements.push(maskImg);

      // 2. Original plan overlay
      if (planImg) {
        planImg.set({ opacity: layer.showMask ? layer.maskOpacity : 0, visible: layer.showMask });
        elements.push(planImg);
      }

      // 3. Vector mask objects (rooms, doors)
      const maskObjects = createMaskObjects(layer.vectorModel, layer.color, layer.showMask ? 1 : 0, layer.showMask, maskImg.width, maskImg.height);
      elements.push(...maskObjects);

      // Create group
      const group = new fabric.Group(elements, {
        left: layer.transform.translate_x,
        top: layer.transform.translate_y,
        scaleX: layer.transform.scale_x,
        scaleY: layer.transform.scale_y,
        angle: layer.transform.rotation_deg,
        cornerStyle: 'circle',
        cornerSize: 8,
        borderColor: layer.color,
        borderDashArray: [5, 3],
        selectable: true,
        evented: true,
      });

      // Store reference
      layerObjectsRef.current.set(layer.reconstructionId, group);

      // Add to canvas
      canvas.add(group);
      canvas.renderAll();
    });
  }, []);

  // Handle object modifications
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleModified = (e: fabric.IEvent) => {
      const obj = e.target as fabric.Group;
      if (!obj) return;

      // Find layer by object
      const layerId = findLayerIdByObject(obj, layerObjectsRef.current);
      if (!layerId) return;

      // Update layer transform
      onLayerUpdate(layerId, {
        transform: {
          translate_x: obj.left || 0,
          translate_y: obj.top || 0,
          scale_x: obj.scaleX || 1,
          scale_y: obj.scaleY || 1,
          rotation_deg: obj.angle || 0,
        },
      });

      // Push snapshot
      onSnapshotPush(exportState());
    };

    canvas.on('object:modified', handleModified);

    return () => {
      canvas.off('object:modified', handleModified);
    };
  }, [onLayerUpdate, onSnapshotPush, layers]);

  // Apply polygon clip
  const applyPolygonClip = useCallback((layerId: string, polygon: ClipPolygon) => {
    const group = layerObjectsRef.current.get(layerId);
    if (!group) return;

    // Convert [number, number][] to {x, y}[]
    const points = polygon.points.map(([x, y]) => ({ x, y }));

    const clipPath = new fabric.Polygon(points, {
      absolutePositioned: true,
      inverted: true,
    });

    group.clipPath = clipPath;
    canvasRef.current?.renderAll();

    // Update layer state
    const layer = layers.find(l => l.reconstructionId === layerId);
    if (layer) {
      onLayerUpdate(layerId, {
        clipPolygons: [...layer.clipPolygons, polygon],
      });
      onSnapshotPush(exportState());
    }
  }, [layers, onLayerUpdate, onSnapshotPush]);

  // Apply rect crop
  const applyRectCrop = useCallback((layerId: string, rect: { x: number; y: number; width: number; height: number }) => {
    const group = layerObjectsRef.current.get(layerId);
    if (!group) return;

    const clipPath = new fabric.Rect({
      left: rect.x,
      top: rect.y,
      width: rect.width,
      height: rect.height,
      absolutePositioned: true,
    });

    group.clipPath = clipPath;
    canvasRef.current?.renderAll();

    // Update layer state
    onLayerUpdate(layerId, {
      rectCrop: rect,
    });
    onSnapshotPush(exportState());
  }, [onLayerUpdate, onSnapshotPush]);

  // Export state
  const exportState = useCallback((): StitchingSnapshot => {
    const layerSnapshots = layers.map((layer) => ({
      reconstructionId: layer.reconstructionId,
      transform: layer.transform,
      clipPolygons: layer.clipPolygons,
      rectCrop: layer.rectCrop,
      zIndex: layer.zIndex,
    }));

    return { layers: layerSnapshots };
  }, [layers]);

  // Restore snapshot
  const restoreSnapshot = useCallback((snapshot: StitchingSnapshot) => {
    // Update all layer transforms from snapshot
    snapshot.layers.forEach((layerSnapshot) => {
      const group = layerObjectsRef.current.get(layerSnapshot.reconstructionId);
      if (!group) return;

      group.set({
        left: layerSnapshot.transform.translate_x,
        top: layerSnapshot.transform.translate_y,
        scaleX: layerSnapshot.transform.scale_x,
        scaleY: layerSnapshot.transform.scale_y,
        angle: layerSnapshot.transform.rotation_deg,
      });

      group.setCoords();
    });

    canvasRef.current?.renderAll();
    if ((canvasRef.current as any)?.updateGridCSS) {
      (canvasRef.current as any).updateGridCSS();
    }
  }, []);

  // activeTool & Pan/Zoom logic
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Clean up any previous crop/polygon guides
    if (cropRectRef.current) {
      canvas.remove(cropRectRef.current);
      cropRectRef.current = null;
    }
    polygonDotsRef.current.forEach(d => canvas.remove(d));
    polygonDotsRef.current = [];
    polygonPointsRef.current = [];

    // Set object properties based on active tool
    const isMoveTool = activeTool === 'move';
    const isRotateTool = activeTool === 'rotate';

    canvas.forEachObject((obj) => {
      if ((obj as any)._isCropGuide || (obj as any)._isPolyDot) return;
      obj.set({
        selectable: isMoveTool || isRotateTool,
        evented: isMoveTool || isRotateTool,
        lockRotation: !isRotateTool,
        lockMovementX: isRotateTool,
        lockMovementY: isRotateTool,
        lockScalingX: true,
        lockScalingY: true,
        hasControls: isRotateTool,
      });
    });

    // Update cursor
    if (activeTool === 'move') {
      canvas.defaultCursor = 'grab';
      canvas.hoverCursor = 'grab';
    } else if (activeTool === 'rotate') {
      canvas.defaultCursor = 'crosshair';
      canvas.hoverCursor = 'crosshair';
    } else {
      canvas.defaultCursor = 'crosshair';
      canvas.hoverCursor = 'crosshair';
    }

    let isPanning = false;
    let lastPosX = 0;
    let lastPosY = 0;
    let spacePressed = false;

    // rect_crop state
    let isCropping = false;
    let cropStartX = 0;
    let cropStartY = 0;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !spacePressed) {
        spacePressed = true;
        canvas.defaultCursor = 'grab';
        canvas.forEachObject(obj => obj.set({ evented: false }));
        canvas.requestRenderAll();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        spacePressed = false;
        isPanning = false;
        
        if (activeTool === 'move') canvas.defaultCursor = 'grab';
        else canvas.defaultCursor = 'crosshair';
        
        const isMove = activeTool === 'move';
        const isRot = activeTool === 'rotate';
        canvas.forEachObject(obj => {
          if ((obj as any)._isCropGuide || (obj as any)._isPolyDot) return;
          obj.set({ evented: isMove || isRot });
        });
        canvas.requestRenderAll();
      }
    };

    const handleMouseDown = (opt: fabric.IEvent) => {
      const e = opt.e as MouseEvent;
      const isMiddleMouse = e && (e.button === 1 || e.buttons === 4);

      // Panning (space or middle mouse)
      if ((spacePressed || isMiddleMouse) && e) {
        if (isMiddleMouse) {
          e.preventDefault();
          canvas.forEachObject((obj) => obj.set({ evented: false }));
        }
        isPanning = true;
        lastPosX = e.clientX;
        lastPosY = e.clientY;
        canvas.defaultCursor = 'grabbing';
        return;
      }

      // Rect crop tool
      if (activeTool === 'rect_crop' && e && e.button === 0) {
        if (!selectedLayerId) return;
        const pointer = canvas.getPointer(e);
        cropStartX = pointer.x;
        cropStartY = pointer.y;
        isCropping = true;

        // Create visual guide rectangle
        const rect = new fabric.Rect({
          left: cropStartX,
          top: cropStartY,
          width: 0,
          height: 0,
          fill: 'rgba(255, 87, 34, 0.15)',
          stroke: '#FF5722',
          strokeWidth: 2,
          strokeDashArray: [6, 3],
          selectable: false,
          evented: false,
        });
        (rect as any)._isCropGuide = true;
        cropRectRef.current = rect;
        canvas.add(rect);
        return;
      }

      // Polygon clip tool — add point on left click
      if (activeTool === 'polygon_clip' && e && e.button === 0) {
        if (!selectedLayerId) return;
        const pointer = canvas.getPointer(e);
        polygonPointsRef.current.push({ x: pointer.x, y: pointer.y });

        // Draw a dot marker
        const dot = new fabric.Circle({
          left: pointer.x,
          top: pointer.y,
          radius: 4,
          fill: '#FF5722',
          originX: 'center',
          originY: 'center',
          selectable: false,
          evented: false,
        });
        (dot as any)._isPolyDot = true;
        polygonDotsRef.current.push(dot);
        canvas.add(dot);
        canvas.requestRenderAll();
        return;
      }
    };

    const handleMouseMove = (opt: fabric.IEvent) => {
      const e = opt.e as MouseEvent;
      if (isPanning && e) {
        const vpt = canvas.viewportTransform!;
        vpt[4] += e.clientX - lastPosX;
        vpt[5] += e.clientY - lastPosY;
        lastPosX = e.clientX;
        lastPosY = e.clientY;
        canvas.requestRenderAll();
        return;
      }

      // Rect crop drag
      if (isCropping && cropRectRef.current && e) {
        const pointer = canvas.getPointer(e);
        const left = Math.min(cropStartX, pointer.x);
        const top = Math.min(cropStartY, pointer.y);
        const width = Math.abs(pointer.x - cropStartX);
        const height = Math.abs(pointer.y - cropStartY);
        cropRectRef.current.set({ left, top, width, height });
        canvas.requestRenderAll();
      }
    };

    const handleMouseUp = (_opt: fabric.IEvent) => {
      if (isPanning) {
        isPanning = false;
        if (spacePressed) {
          canvas.defaultCursor = 'grab';
        } else {
          const isMove = activeTool === 'move';
          const isRot = activeTool === 'rotate';
          canvas.defaultCursor = isMove ? 'grab' : 'crosshair';
          canvas.forEachObject((obj) => {
            if ((obj as any)._isCropGuide || (obj as any)._isPolyDot) return;
            obj.set({ evented: isMove || isRot });
          });
        }
        canvas.requestRenderAll();
        return;
      }

      // Finish rect crop
      if (isCropping && cropRectRef.current && selectedLayerId) {
        isCropping = false;
        const rect = cropRectRef.current;
        const w = rect.width || 0;
        const h = rect.height || 0;

        if (w > 5 && h > 5) {
          applyRectCrop(selectedLayerId, {
            x: rect.left || 0,
            y: rect.top || 0,
            width: w,
            height: h,
          });
        }

        canvas.remove(rect);
        cropRectRef.current = null;
        canvas.requestRenderAll();
      }
    };

    const handleDblClick = () => {
      // Finish polygon clip on double-click
      if (activeTool === 'polygon_clip' && selectedLayerId && polygonPointsRef.current.length >= 3) {
        const points: [number, number][] = polygonPointsRef.current.map(p => [p.x, p.y]);
        applyPolygonClip(selectedLayerId, { type: 'subtract', points });

        // Clean up dots
        polygonDotsRef.current.forEach(d => canvas.remove(d));
        polygonDotsRef.current = [];
        polygonPointsRef.current = [];
        canvas.requestRenderAll();
      }
    };

    const handleWheel = (opt: fabric.IEvent) => {
      const e = opt.e as WheelEvent;
      const delta = e.deltaY;
      let zoom = canvas.getZoom();
      zoom *= 0.999 ** delta;
      zoom = Math.min(Math.max(zoom, 0.1), 5);
      canvas.zoomToPoint({ x: e.offsetX, y: e.offsetY } as fabric.Point, zoom);
      e.preventDefault();
      e.stopPropagation();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    canvas.on('mouse:down', handleMouseDown);
    canvas.on('mouse:move', handleMouseMove);
    canvas.on('mouse:up', handleMouseUp);
    canvas.on('mouse:dblclick', handleDblClick);
    canvas.on('mouse:wheel', handleWheel);

    canvas.requestRenderAll();

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      canvas.off('mouse:down', handleMouseDown);
      canvas.off('mouse:move', handleMouseMove);
      canvas.off('mouse:up', handleMouseUp);
      canvas.off('mouse:dblclick', handleDblClick);
      canvas.off('mouse:wheel', handleWheel);
    };
  }, [activeTool, selectedLayerId]);

  // Sync layer opacity, showMask, and zIndex to fabric.js canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    layers.forEach((layer) => {
      const group = layerObjectsRef.current.get(layer.reconstructionId);
      if (!group) return;

      // Sync the opacity: index 0 (black mask), index 1 (original plan), other (vectors)
      const objects = group.getObjects();

      let hasOriginalPlan = objects.length > 1 && !(objects[1] instanceof fabric.Polygon || objects[1] instanceof fabric.Circle);

      objects.forEach((obj, idx) => {
        if (idx === 0) {
          // Black mask always visible if showMask is true
          obj.set({ opacity: layer.showMask ? 1 : 0, visible: layer.showMask });
        } else if (idx === 1 && hasOriginalPlan) {
          // Original Plan fades out according to maskOpacity
          obj.set({ opacity: layer.showMask ? layer.maskOpacity : 0, visible: layer.showMask });
        } else {
          // Vectors stay fully visible if showMask is true
          obj.set({
            opacity: layer.showMask ? 1 : 0,
            visible: layer.showMask,
          });
        }
      });

      // Sync positional state from React state (for Ctrl+Z Undo/Redo)
      // Check if coordinate differs to avoid reacting to our own drags
      if (Math.abs(group.left! - layer.transform.translate_x) > 0.01 ||
          Math.abs(group.top! - layer.transform.translate_y) > 0.01 ||
          Math.abs(group.scaleX! - layer.transform.scale_x) > 0.01 ||
          Math.abs(group.scaleY! - layer.transform.scale_y) > 0.01 ||
          Math.abs(group.angle! - layer.transform.rotation_deg) > 0.01) {

        group.set({
          left: layer.transform.translate_x,
          top: layer.transform.translate_y,
          scaleX: layer.transform.scale_x,
          scaleY: layer.transform.scale_y,
          angle: layer.transform.rotation_deg,
        });
        group.setCoords();
      }

      // Update zIndex by reordering on canvas
      canvas.moveTo(group, layer.zIndex);
    });

    canvas.requestRenderAll();
  }, [layers.map(l => `${l.reconstructionId}:${l.maskOpacity}:${l.showMask}:${l.zIndex}:${l.transform.translate_x}:${l.transform.translate_y}:${l.transform.rotation_deg}`).join(',')]);

  // Remove plan from canvas
  const removePlanFromCanvas = useCallback((layerId: string) => {
    const group = layerObjectsRef.current.get(layerId);
    if (group) {
      canvasRef.current?.remove(group);
      layerObjectsRef.current.delete(layerId);
    }
  }, []);

  return {
    canvasRef,
    loadPlanToCanvas,
    removePlanFromCanvas,
    applyPolygonClip,
    applyRectCrop,
    exportState,
    restoreSnapshot,
  };
};

// Helper functions
const prepareCroppedPlanImage = (
  imageUrl: string | undefined,
  rotation?: number,
  cropRect?: { x: number; y: number; width: number; height: number }
): Promise<string | null> => {
  return new Promise((resolve) => {
    if (!imageUrl) {
      resolve(null);
      return;
    }

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const rot = rotation ?? 0;
      const swap = rot === 90 || rot === 270;
      const rCanvas = document.createElement('canvas');
      rCanvas.width = swap ? img.height : img.width;
      rCanvas.height = swap ? img.width : img.height;
      const rCtx = rCanvas.getContext('2d');
      if (!rCtx) {
        resolve(null);
        return;
      }
      rCtx.translate(rCanvas.width / 2, rCanvas.height / 2);
      rCtx.rotate((rot * Math.PI) / 180);
      rCtx.drawImage(img, -img.width / 2, -img.height / 2);

      if (cropRect) {
        const cx = Math.round(cropRect.x * rCanvas.width);
        const cy = Math.round(cropRect.y * rCanvas.height);
        const cw = Math.round(cropRect.width * rCanvas.width);
        const ch = Math.round(cropRect.height * rCanvas.height);
        const cropCanvas = document.createElement('canvas');
        cropCanvas.width = cw;
        cropCanvas.height = ch;
        const cropCtx = cropCanvas.getContext('2d');
        if (!cropCtx) {
          resolve(rCanvas.toDataURL());
          return;
        }
        cropCtx.drawImage(rCanvas, cx, cy, cw, ch, 0, 0, cw, ch);
        resolve(cropCanvas.toDataURL());
      } else {
        resolve(rCanvas.toDataURL());
      }
    };
    img.onerror = () => resolve(null);
    img.src = imageUrl;
  });
};

function createMaskObjects(
  vectorModel: LayerData['vectorModel'],
  color: string,
  opacity: number,
  showMask: boolean,
  imageWidth: number,
  imageHeight: number,
): fabric.Object[] {
  if (!showMask || !vectorModel) return [];

  const objects: fabric.Object[] = [];



  vectorModel.rooms.forEach((room) => {
    if (room.polygon.length < 3) return;

    const polygon = new fabric.Polygon(
      room.polygon.map((point) => ({
        x: point.x * imageWidth,
        y: point.y * imageHeight,
      })),
      {
        fill: `${color}33`,
        stroke: color,
        strokeWidth: 1,
        opacity,
        selectable: false,
        evented: false,
      },
    );

    objects.push(polygon);
  });

  vectorModel.doors.forEach((door) => {
    const circle = new fabric.Circle({
      left: door.position.x * imageWidth,
      top: door.position.y * imageHeight,
      radius: 6, // Fixed visible dot
      fill: color,
      opacity,
      originX: 'center',
      originY: 'center',
      selectable: false,
      evented: false,
    });

    objects.push(circle);
  });

  return objects;
}

function findLayerIdByObject(obj: fabric.Object, map: Map<string, fabric.Group>): string | null {
  for (const [id, group] of map.entries()) {
    if (group === obj) return id;
  }
  return null;
}
