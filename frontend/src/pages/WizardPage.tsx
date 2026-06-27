import React, { useRef, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useWizard } from '../hooks/useWizard';
import { useFileUpload } from '../hooks/useFileUpload';
import { WizardShell } from '../components/Wizard/WizardShell';
import { StepUpload } from '../components/Wizard/StepUpload';
import { StepPreprocess } from '../components/Wizard/StepPreprocess';
// СКРЫТО (опорные точки теперь ставятся при создании отсеков). Чтобы вернуть
// этап — раскомментируйте импорт + case 3 ниже и верните нумерацию шагов на 6.
// import { StepControlPoints } from '../components/Wizard/StepControlPoints';
import { StepWallEditor } from '../components/Wizard/StepWallEditor';
import { StepNavGraph } from '../components/Wizard/StepNavGraph';
import { StepView3D } from '../components/Wizard/StepView3D';
import type { WallEditorCanvasRef } from '../components/Editor/WallEditorCanvas';

export const WizardPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const wizard = useWizard();
  const upload = useFileUpload();
  const canvasRef = useRef<WallEditorCanvasRef>(null);

  const { state } = wizard;

  // Pre-fill building/floor from URL when arriving from AdminBuildingsPage.
  // Runs once: deliberately ignores subsequent searchParams changes so we don't
  // overwrite a user's manual change in the floor selector.
  useEffect(() => {
    const buildingRaw = searchParams.get('building_id');
    const floorRaw = searchParams.get('floor_id');
    const buildingId = buildingRaw !== null ? parseInt(buildingRaw, 10) : NaN;
    const floorId = floorRaw !== null ? parseInt(floorRaw, 10) : NaN;
    if (!isNaN(buildingId) && !isNaN(floorId)) {
      void wizard.setFloor(buildingId, floorId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleNext = async () => {
    if (state.step === 1 && upload.files.length > 0) {
      const file = upload.files[0];
      wizard.setPlanFile(file.id, file.url);
      wizard.nextStep();
    } else if (state.step === 2) {
      await wizard.calculateMask();
      wizard.nextStep();
    } else if (state.step === 3 && canvasRef.current) {
      const blob = await canvasRef.current.getBlob();
      const { rooms, doors } = canvasRef.current.getAnnotations();
      const canvasState = await canvasRef.current.getCanvasState?.();
      const editedMaskId = await wizard.saveMaskAndAnnotations(blob, rooms, doors, canvasState);
      if (editedMaskId) {
        await wizard.buildNavGraph(editedMaskId, rooms, doors);
      }
    } else if (state.step === 4) {
      await wizard.buildMesh(state.editedMaskFileId ?? state.maskFileId ?? undefined);
    } else if (state.step === 5) {
      await wizard.save(state.planName);
    }
  };

  const handlePrev = () => {
    if (state.step === 1) {
      navigate('/admin');
    } else if (state.step === 3) {
      if (!window.confirm('Вернуться на шаг 2? Все нарисованные стены и разметка будут потеряны.')) return;
      wizard.prevStep();
    } else {
      wizard.prevStep();
    }
  };

  const isNextDisabled =
    (state.step === 1 && (upload.files.length === 0 || wizard.selectedFloorId === null || !state.planName.trim())) ||
    state.isLoading;

  const nextLabel =
    state.step === 3 ? '> ПОСТРОИТЬ ГРАФ' :
    state.step === 4 ? '> ПОСТРОИТЬ 3D' :
    state.step === 5 ? 'СОХРАНИТЬ И ВЫЙТИ' :
    undefined;

  const maskUrl = `/api/v1/uploads/masks/${state.editedMaskFileId ?? state.maskFileId}.png`;

  const renderStep = () => {
    switch (state.step) {
      case 1:
        return (
          <StepUpload
            files={upload.files}
            onFilesSelect={upload.addFiles}
            onRemove={upload.removeFile}
            isUploading={upload.isUploading}
            selectedBuildingId={wizard.selectedBuildingId}
            selectedFloorId={wizard.selectedFloorId}
            planName={state.planName}
            onPlanNameChange={wizard.setPlanName}
            onFloorChange={({ buildingId, floorId }) => { void wizard.setFloor(buildingId, floorId); }}
          />
        );
      case 2:
        return (
          <StepPreprocess
            planUrl={state.planUrl!}
            cropRect={state.cropRect}
            rotation={state.rotation}
            onCropChange={wizard.setCropRect}
            onRotate={() =>
              wizard.setRotation(((state.rotation + 90) % 360) as 0 | 90 | 180 | 270)
            }
          />
        );
      // case «Опорные точки» СКРЫТ — точки ставятся при создании отсеков.
      case 3:
        return (
          <StepWallEditor
            maskUrl={maskUrl}
            planFileId={state.planFileId}
            planUrl={state.planUrl ?? undefined}
            cropRect={state.cropRect}
            rotation={state.rotation}
            blockSize={state.blockSize}
            thresholdC={state.thresholdC}
            canvasRef={canvasRef}
            onBlockSizeChange={wizard.setBlockSize}
            onThresholdCChange={wizard.setThresholdC}
            initialRooms={state.rooms}
            initialDoors={state.doors}
          />
        );
      case 4:
        return (
          <StepNavGraph
            navGraphId={state.navGraphId}
            maskUrl={maskUrl}
          />
        );
      case 5:
        return (
          <StepView3D
            meshUrl={state.meshUrl}
            reconstructionId={state.reconstructionId}
            navGraphId={state.navGraphId}
            rooms={state.rooms}
            onNext={handleNext}
            onPrev={handlePrev}
            isNextDisabled={isNextDisabled}
          />
        );

      default:
        return null;
    }
  };

  return (
    <WizardShell
      currentStep={state.step}
      totalSteps={5}
      onNext={handleNext}
      onPrev={handlePrev}
      onClose={() => navigate('/admin/buildings')}
      nextDisabled={isNextDisabled}
      nextLabel={nextLabel}
      hideFooter={state.step === 5}
    >
      {renderStep()}
    </WizardShell>
  );
};

export default WizardPage;
