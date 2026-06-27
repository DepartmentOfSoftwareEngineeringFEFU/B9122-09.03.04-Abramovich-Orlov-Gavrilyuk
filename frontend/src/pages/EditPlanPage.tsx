import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { reconstructionApi } from '../api/apiService';
import { WizardShell } from '../components/Wizard/WizardShell';
import { StepWallEditor } from '../components/Wizard/StepWallEditor';
import { StepNavGraph } from '../components/Wizard/StepNavGraph';
import { StepView3D } from '../components/Wizard/StepView3D';
import type { WallEditorCanvasRef } from '../components/Editor/WallEditorCanvas';
import type { RoomAnnotation, DoorAnnotation, CropRect } from '../types/wizard';
import type { VectorizationResult } from '../types/reconstructionVectors';
import type { ReconstructionFloor, ReconstructionSectionBrief } from '../types/hierarchy';

function toRoomAnnotation(room: VectorizationResult['rooms'][number]): RoomAnnotation {
  if (room.polygon.length === 4) {
    const xs = room.polygon.map((p) => p.x);
    const ys = room.polygon.map((p) => p.y);
    return {
      id: room.id,
      name: room.name,
      room_type: room.room_type,
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
      floor_from: room.floor_from,
      floor_to: room.floor_to,
      floors_excluded: room.floors_excluded,
    };
  }

  const side = Math.sqrt(room.area_normalized);
  return {
    id: room.id,
    name: room.name,
    room_type: room.room_type,
    x: room.center.x - side / 2,
    y: room.center.y - side / 2,
    width: side,
    height: side,
    floor_from: room.floor_from,
    floor_to: room.floor_to,
    floors_excluded: room.floors_excluded,
  };
}

interface PlanData {
  maskUrl: string;
  maskFileId: string | null;
  planUrl: string;
  rotation: number;
  cropRect: CropRect | null;
  meshUrl: string | null;
  initialRooms: RoomAnnotation[];
  initialDoors: DoorAnnotation[];
  rawVectors: VectorizationResult | null;
  floor: ReconstructionFloor | null;
  section: ReconstructionSectionBrief | null;
}

export const EditPlanPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const canvasRef = useRef<WallEditorCanvasRef>(null);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isBuildingGraph, setIsBuildingGraph] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<PlanData | null>(null);
  const [navGraphId, setNavGraphId] = useState<string | null>(null);
  const [currentRooms, setCurrentRooms] = useState<RoomAnnotation[]>([]);

  useEffect(() => {
    if (!id) return;
    const loadData = async () => {
      try {
        const numId = parseInt(id, 10);
        const [rec, vectors] = await Promise.all([
          reconstructionApi.getReconstructionById(numId),
          reconstructionApi.getReconstructionVectors(numId).catch(() => null),
        ]);

        const vectorData = vectors as VectorizationResult | null;
        const rooms: RoomAnnotation[] = (vectorData?.rooms ?? []).map((r) => {
          const xs = r.polygon.map((p) => p.x);
          const ys = r.polygon.map((p) => p.y);
          return {
            id: r.id,
            name: r.name,
            room_type: r.room_type,
            x: Math.min(...xs),
            y: Math.min(...ys),
            width: Math.max(...xs) - Math.min(...xs),
            height: Math.max(...ys) - Math.min(...ys),
            polygon: r.polygon,
            center: r.center,
            area_normalized: r.area_normalized,
            floor_from: r.floor_from,
            floor_to: r.floor_to,
            floors_excluded: r.floors_excluded,
          };
        });

        void toRoomAnnotation;

        const doors: DoorAnnotation[] = (vectorData?.doors ?? []).map((d) => ({
          id: d.id,
          x1: d.position.x,
          y1: d.position.y,
          x2: d.position.x,
          y2: d.position.y,
          room_id: d.connects?.[0] ?? null,
        }));

        const fallbackCropRect = rec.crop_rect ?? null;

        setData({
          maskUrl: rec.preview_url || '',
          maskFileId: rec.mask_file_id || null,
          planUrl: rec.original_image_url || '',
          rotation: vectorData?.rotation_angle ?? rec.rotation_angle ?? 0,
          cropRect: vectorData?.crop_rect ?? fallbackCropRect,
          meshUrl: rec.url ?? null,
          initialRooms: rooms,
          initialDoors: doors,
          rawVectors: vectorData,
          floor: rec.floor ?? null,
          section: rec.section ?? null,
        });
        setCurrentRooms(rooms);
      } catch (err) {
        setError('Ошибка загрузки данных плана');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, [id]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  const handleClose = useCallback(() => {
    if (window.confirm('Выйти без сохранения? Изменения будут потеряны.')) {
      navigate('/admin');
    }
  }, [navigate]);

  const handlePrev = useCallback(() => {
    if (step === 3) {
      setStep(2);
    } else if (step === 2) {
      setStep(1);
    } else {
      handleClose();
    }
  }, [step, handleClose]);

  const saveVectors = useCallback(async () => {
    if (!canvasRef.current || !id || !data) return null;
    const { rooms, doors } = canvasRef.current.getAnnotations();

    const updatedPayload: VectorizationResult = {
      ...(data.rawVectors ?? {
        rooms: [],
        doors: [],
        rotation_angle: data.rotation,
        crop_rect: data.cropRect,
      }),
      rooms: rooms.map((r) => ({
        id: r.id,
        name: r.name,
        room_type: r.room_type,
        center: r.center ?? { x: r.x + r.width / 2, y: r.y + r.height / 2 },
        polygon: r.polygon ?? [
          { x: r.x, y: r.y },
          { x: r.x + r.width, y: r.y },
          { x: r.x + r.width, y: r.y + r.height },
          { x: r.x, y: r.y + r.height },
        ],
        area_normalized: r.area_normalized ?? (r.width * r.height),
        floor_from: r.floor_from,
        floor_to: r.floor_to,
        floors_excluded: r.floors_excluded,
      })),
      doors: doors.map((d) => ({
        id: d.id,
        position: { x: d.x1, y: d.y1 },
        width: 0.05,
        connects: d.room_id ? [d.room_id] : [],
      })),
    };

    await reconstructionApi.updateVectorizationData(parseInt(id, 10), updatedPayload);
    setCurrentRooms(rooms);
    return { rooms, doors };
  }, [id, data]);

  const handleNext = useCallback(async () => {
    if (step === 1) {
      if (!data?.maskFileId) {
        if (data?.meshUrl) {
          setStep(3);
        } else {
          try {
            await saveVectors();
            navigate('/admin');
          } catch (err) {
            alert('Ошибка при сохранении: ' + err);
          }
        }
        return;
      }

      setIsBuildingGraph(true);
      try {
        const result = await saveVectors();
        if (!result) return;

        const navResult = await reconstructionApi.buildNavGraph(
          data.maskFileId,
          result.rooms,
          result.doors
        );
        setNavGraphId(navResult.graph_id);
        setStep(2);
      } catch (err) {
        console.error('Nav graph build error:', err);
        alert('Ошибка построения навигационного графа: ' + err);
      } finally {
        setIsBuildingGraph(false);
      }
    } else if (step === 2) {
      if (data?.meshUrl) {
        setStep(3);
      } else {
        navigate('/admin');
      }
    } else {
      navigate('/admin');
    }
  }, [step, data, saveVectors, navigate]);

  const handleSaveAndExit = useCallback(async () => {
    navigate('/admin');
  }, [navigate]);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0a0a0a', color: '#888',  }}>
        SYS.LOADING... загрузка плана...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0a0a0a', color: '#888',  gap: '16px' }}>
        <div>{error ?? 'Данные не найдены'}</div>
        <button onClick={() => navigate('/admin')} style={{ padding: '8px 20px', background: '#222', color: '#fff', border: '1px solid #444', cursor: 'pointer',  }}>
          ← Назад
        </button>
      </div>
    );
  }

  const totalSteps = data.meshUrl ? 3 : 2;

  let nextLabel: string;
  if (step === 1) {
    nextLabel = isBuildingGraph ? 'Построение графа...' : '> Далее';
  } else if (step === 2 && data.meshUrl) {
    nextLabel = '> 3D Просмотр';
  } else {
    nextLabel = 'Сохранить изменения';
  }

  return (
    <>
      <WizardShell
        currentStep={step}
        totalSteps={totalSteps}
        onNext={handleNext}
        onPrev={handlePrev}
        onClose={handleClose}
        nextLabel={nextLabel}
        nextDisabled={isBuildingGraph}
        hideFooter={step === 3}
      >
        {step === 1 ? (
          <StepWallEditor
            maskUrl={data.maskUrl}
            planFileId={null}
            planUrl={data.planUrl}
            cropRect={data.cropRect}
            rotation={data.rotation as any}
            blockSize={15}
            thresholdC={10}
            canvasRef={canvasRef}
            onBlockSizeChange={() => {}}
            onThresholdCChange={() => {}}
            initialRooms={data.initialRooms}
            initialDoors={data.initialDoors}
            hideMaskParams={true}
          />
        ) : step === 2 ? (
          <StepNavGraph
            navGraphId={navGraphId}
            maskUrl={data.maskUrl}
          />
        ) : (
          <StepView3D
            meshUrl={data.meshUrl}
            reconstructionId={id ? parseInt(id, 10) : null}
            navGraphId={navGraphId}
            rooms={currentRooms}
            onNext={handleSaveAndExit}
            onPrev={() => setStep(2)}
            isNextDisabled={false}
            nextLabel="Сохранить изменения"
          />
        )}
      </WizardShell>
    </>
  );
};

export default EditPlanPage;
