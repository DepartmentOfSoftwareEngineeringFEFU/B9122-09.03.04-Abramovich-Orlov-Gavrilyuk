import React, { useEffect, useCallback, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import styles from './FloorEditorPage.module.css';
import { useFloorEditorWizard } from '../hooks/useFloorEditorWizard';
import { useFloorAssembly } from '../hooks/useFloorAssembly';
import { useBuildings } from '../hooks/useBuildings';
import { useFloors } from '../hooks/useFloors';
import { Step1Upload } from '../components/FloorEditor/Step1Upload';
import { Step2CropRotate } from '../components/FloorEditor/Step2CropRotate';
import { Step3WallExtraction } from '../components/FloorEditor/Step3WallExtraction';
import { Step4MarkSections } from '../components/FloorEditor/Step4MarkSections';
import { Step5BindPlans } from '../components/FloorEditor/Step5BindPlans';
import { Step6BindControlPoints } from '../components/FloorEditor/Step6BindControlPoints';
import { Step7SolveTransforms } from '../components/FloorEditor/Step7SolveTransforms';
import { Step8Connectors } from '../components/FloorEditor/Step8Connectors';
import { Step9NavGraph } from '../components/FloorEditor/Step9NavGraph';
import { Step9FloorPreview } from '../components/FloorEditor/Step9FloorPreview';
import { FloorOverview } from '../components/FloorEditor/FloorOverview';
import { FloorSectionsTable } from '../components/FloorEditor/FloorSectionsTable';
import { Toaster } from '../components/Toast/Toaster';

// 5 wizard steps (upload→crop→walls→sections→bind) + 5 assembly steps APPENDED
// after them (master CPs→solve→connectors→nav-graph→preview). Drives the dots.
const TOTAL_STEPS = 10;

export const FloorEditorPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const wizard = useFloorEditorWizard();
  // Sibling hook owning the – assembly steps (6–9). Loaded alongside the
  // wizard from the single GET /assembly read; only meaningful in wizard mode.
  const assembly = useFloorAssembly();

  // Read floor_id from URL query param
  const floorIdParam = searchParams.get('floor_id');
  const urlFloorId = floorIdParam !== null ? parseInt(floorIdParam, 10) : null;

  // Load wizard + assembly state when URL floor_id is present
  useEffect(() => {
    if (urlFloorId !== null && !isNaN(urlFloorId)) {
      void wizard.loadFor(urlFloorId);
      void assembly.load(urlFloorId);
    }
  }, [urlFloorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // The assembly steps (6–10) live on a SEPARATE hook (useFloorAssembly) that is
  // read once at mount. Steps 1–5 (wizard) can change the floor's sections, schema
  // and mask in between, so when the operator crosses from a wizard step (≤5) into
  // step 6 we must re-read the assembly — otherwise step 6 shows the stale карта
  // отсеков + section list captured when the page first opened. Only reload on the
  // ≤5 → 6 crossing; staying within 6–10 keeps in-progress control points.
  const prevStepRef = useRef<number | null>(null);
  useEffect(() => {
    const prev = prevStepRef.current;
    prevStepRef.current = wizard.currentStep;
    if (wizard.currentStep === 6 && prev !== null && prev <= 5) {
      void assembly.reload();
    }
  }, [wizard.currentStep, assembly.reload]);

  const handleSaveAndExit = useCallback(async () => {
    await wizard.saveAll();
    navigate('/admin');
  }, [wizard, navigate]);

  const handleClearAllDrafts = useCallback(() => {
    const count = wizard.sectionDrafts.length;
    for (let i = count - 1; i >= 0; i--) {
      wizard.deleteSectionDraft(i);
    }
  }, [wizard]);

  // Header
  const stepDots = (currentStep: number) => (
    <div className={styles.stepDots}>
      {Array.from({ length: TOTAL_STEPS }, (_, i) => {
        const step = i + 1;
        const cls = [
          styles.stepDot,
          step === currentStep ? styles.stepDotActive : '',
          step < currentStep ? styles.stepDotPassed : '',
        ].filter(Boolean).join(' ');
        return <span key={step} className={cls} />;
      })}
    </div>
  );

  const handleHeaderBack = useCallback(() => {
    if (wizard.mode === 'wizard' && wizard.currentStep > 1) {
      wizard.prevStep();
    } else {
      navigate('/admin');
    }
  }, [wizard, navigate]);

  const header = (
    <header className={styles.header}>
      <button
        className={styles.backBtn}
        onClick={handleHeaderBack}
        type="button"
        title="Назад"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </svg>
      </button>
      {wizard.mode === 'wizard' && stepDots(wizard.currentStep)}
      <button
        className={styles.closeBtn}
        onClick={() => navigate('/admin')}
        type="button"
        title="Закрыть"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </header>
  );

  // No floor_id from URL — show a building/floor picker card
  if (urlFloorId === null || isNaN(urlFloorId)) {
    return (
      <div className={styles.page}>
        {header}
        <div className={styles.pickerWrap}>
          <FloorPickerCard
            onPicked={(fid) => navigate(`/admin/floor-editor?floor_id=${fid}`)}
            onCancel={() => navigate('/admin/buildings')}
          />
        </div>
        <Toaster />
      </div>
    );
  }

  // Loading
  if (wizard.isLoading && !wizard.floorId) {
    return (
      <div className={styles.page}>
        {header}
        <div className={styles.workingArea}>
          <aside className={styles.leftPanel} />
          <div className={styles.centerCanvas}>
            <div className={styles.emptyState}>
              <div className={styles.spinner} />
              <span className={styles.spinnerText}>Загрузка этажа...</span>
            </div>
          </div>
        </div>
        <Toaster />
      </div>
    );
  }

  // Error
  if (wizard.error && !wizard.isLoading) {
    return (
      <div className={styles.page}>
        {header}
        <div className={styles.workingArea}>
          <aside className={styles.leftPanel} />
          <div className={styles.centerCanvas}>
            <div className={styles.emptyState}>
              <p className={styles.errorText}>{wizard.error}</p>
              <button
                className={styles.retryBtn}
                onClick={() => void wizard.loadFor(urlFloorId)}
                type="button"
              >
                Повторить
              </button>
            </div>
          </div>
        </div>
        <Toaster />
      </div>
    );
  }

  // Wizard steps
  const renderWizardStep = () => {
    switch (wizard.currentStep) {
      case 1:
        return (
          <Step1Upload
            schemaImageUrl={wizard.schemaImageUrl}
            isLoading={wizard.isLoading}
            onUploaded={wizard.setSchemaImage}
            onNext={wizard.nextStep}
            onBack={() => navigate('/admin')}
          />
        );
      case 2:
        return (
          <Step2CropRotate
            schemaImageUrl={wizard.schemaImageUrl ?? ''}
            cropBbox={wizard.cropBbox}
            isLoading={wizard.isLoading}
            onCropBboxChange={wizard.setCropBbox}
            onNext={async () => {
              await wizard.commitCropBbox();
              wizard.nextStep();
            }}
            onBack={wizard.prevStep}
          />
        );
      case 3:
        return (
          <Step3WallExtraction
            schemaImageId={wizard.schemaImageId}
            schemaImageUrl={wizard.schemaImageUrl}
            cropBbox={wizard.cropBbox}
            wallPolygons={wizard.wallPolygons}
            isLoading={wizard.isLoading}
            onTriggerExtraction={wizard.triggerWallExtraction}
            onCommitEditedMask={wizard.commitEditedMask}
            onNext={async () => {
              await wizard.commitWallPolygons();
              wizard.nextStep();
            }}
            onBack={wizard.prevStep}
          />
        );
      case 4:
        return (
          <Step4MarkSections
            schemaImageId={wizard.schemaImageId}
            schemaImageUrl={wizard.schemaImageUrl}
            cropBbox={wizard.cropBbox}
            wallPolygons={wizard.wallPolygons}
            editedMaskUrl={wizard.editedMaskUrl}
            sectionDrafts={wizard.sectionDrafts}
            onAddSectionDraft={wizard.addSectionDraft}
            onDeleteSectionDraft={wizard.deleteSectionDraft}
            onClearAllDrafts={handleClearAllDrafts}
            onNext={wizard.nextStep}
            onBack={wizard.prevStep}
            onGoToWalls={() => wizard.goToStep(3)}
          />
        );
      case 5:
        return (
          <Step5BindPlans
            schemaImageId={wizard.schemaImageId}
            schemaImageUrl={wizard.schemaImageUrl}
            cropBbox={wizard.cropBbox}
            editedMaskUrl={wizard.editedMaskUrl}
            sectionDrafts={wizard.sectionDrafts}
            wallPolygons={wizard.wallPolygons}
            buildings={[]}
            isLoading={wizard.isLoading}
            floorId={wizard.floorId}
            onBind={wizard.bindReconstruction}
            onSave={async () => {
              await wizard.saveAll();
            }}
            onSaveAndExit={handleSaveAndExit}
            onBack={wizard.prevStep}
          />
        );
      case 6:
        return (
          <Step6BindControlPoints
            sections={assembly.sections}
            masterMaskUrl={assembly.masterMaskUrl}
            sectionPointsBySection={assembly.sectionPointsBySection}
            masterPointsBySection={assembly.masterPointsBySection}
            activeSectionId={assembly.activeSectionId}
            activePointId={assembly.activePointId}
            isLoading={assembly.isLoading}
            onSelectSection={assembly.setActiveSection}
            onSelectPoint={assembly.setActivePoint}
            onSetSectionPoint={assembly.setSectionPoint}
            onSetMasterPoint={assembly.setMasterPoint}
            onRemovePoint={assembly.removePoint}
            onSave={assembly.saveControlPoints}
            onBack={wizard.prevStep}
            onNext={wizard.nextStep}
          />
        );
      case 7:
        return (
          <Step7SolveTransforms
            sections={assembly.sections}
            masterMaskUrl={assembly.masterMaskUrl}
            solveResult={assembly.solveResult}
            isSolving={assembly.isSolving}
            onSolve={assembly.solveTransforms}
            onBack={wizard.prevStep}
            onNext={wizard.nextStep}
          />
        );
      case 8:
        return (
          <Step8Connectors
            masterMaskUrl={assembly.masterMaskUrl}
            connectorDrafts={assembly.connectorDrafts}
            isSaving={assembly.isSavingConnectors}
            pixelsPerMeter={assembly.pixelsPerMeter}
            onChangeDrafts={assembly.setConnectorDrafts}
            onSave={assembly.replaceConnectors}
            cutoutDrafts={assembly.cutoutDrafts}
            onChangeCutouts={assembly.setCutoutDrafts}
            sections={assembly.sections}
            solveResult={assembly.solveResult}
            onBack={wizard.prevStep}
            onNext={async () => {
              // Persist drawn connectors AND cutout zones before advancing
              // (commit-on-Далее, like crop/walls) so the build on step 9
              // includes both.
              await assembly.replaceConnectors();
              await assembly.replaceCutouts();
              wizard.nextStep();
            }}
          />
        );
      case 9:
        return (
          <Step9NavGraph
            floorId={assembly.floorId}
            masterMaskUrl={assembly.masterMaskUrl}
            onBack={wizard.prevStep}
            onNext={wizard.nextStep}
          />
        );
      case 10:
        return (
          <Step9FloorPreview
            previewGlbUrl={assembly.previewGlbUrl}
            buildResult={assembly.buildResult}
            meshFileGlb={assembly.meshFileGlb}
            isBuilding={assembly.isBuilding}
            isConfirming={assembly.isConfirming}
            onBuild={assembly.buildFloorMesh}
            onConfirm={assembly.confirmFloorMesh}
            onBack={wizard.prevStep}
            floorId={assembly.floorId}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className={styles.page}>
      {header}
      {wizard.mode === 'wizard' && (
        <div className={styles.wizardWrap}>
          {renderWizardStep()}
        </div>
      )}
      {wizard.mode === 'overview' && (
        <FloorOverview
          schemaImageUrl={wizard.schemaImageUrl}
          schemaImageId={wizard.schemaImageId}
          cropBbox={wizard.cropBbox}
          editedMaskUrl={wizard.editedMaskUrl}
          wallPolygons={wizard.wallPolygons}
          sectionDrafts={wizard.sectionDrafts}
          isDirty={wizard.isDirty}
          isLoading={wizard.isLoading}
          onUpdateSectionDraft={wizard.updateSectionDraft}
          onDeleteSectionDraft={wizard.deleteSectionDraft}
          onClearAll={wizard.resetFloor}
          onSave={wizard.saveAll}
          onSwitchToTable={() => wizard.setMode('table')}
          onSwitchToWizard={() => wizard.goToStep(1)}
          onStartAssembly={() => wizard.goToStep(6)}
        />
      )}
      {wizard.mode === 'table' && (
        <FloorSectionsTable
          sectionDrafts={wizard.sectionDrafts}
          isDirty={wizard.isDirty}
          isLoading={wizard.isLoading}
          onUpdateSectionDraft={wizard.updateSectionDraft}
          onDeleteSectionDraft={wizard.deleteSectionDraft}
          onSave={wizard.saveAll}
          onEditScheme={() => wizard.goToStep(1)}
          onSwitchToOverview={() => wizard.setMode('overview')}
        />
      )}
      <Toaster />
    </div>
  );
};

/*
 * Floor picker — shown when /admin/floor-editor opened without ?floor_id=N
 * Allows admin to pick which floor to edit before the wizard starts.
 * */

interface FloorPickerCardProps {
  onPicked: (floorId: number) => void;
  onCancel: () => void;
}

const FloorPickerCard: React.FC<FloorPickerCardProps> = ({ onPicked, onCancel }) => {
  const { buildings, isLoading: buildingsLoading } = useBuildings();
  const { floors, isLoading: floorsLoading, loadForBuilding } = useFloors();
  const [buildingId, setBuildingId] = useState<number | null>(null);
  const [floorId, setFloorId] = useState<number | null>(null);

  useEffect(() => {
    if (buildingId !== null) {
      void loadForBuilding(buildingId);
    }
  }, [buildingId, loadForBuilding]);

  return (
    <div className={styles.pickerCard}>
      <h2 className={styles.pickerTitle}>Выберите этаж для редактирования</h2>
      <p className={styles.pickerHint}>
        Сначала выберите корпус, затем этаж. Если нужного корпуса или этажа нет —
        создайте их в разделе «Корпуса и этажи».
      </p>

      <div className={styles.pickerField}>
        <label className={styles.pickerLabel} htmlFor="fp-building">Корпус</label>
        <select
          id="fp-building"
          className={styles.pickerSelect}
          value={buildingId ?? ''}
          disabled={buildingsLoading || buildings.length === 0}
          onChange={(e) => {
            const v = e.target.value;
            setBuildingId(v === '' ? null : parseInt(v, 10));
            setFloorId(null);
          }}
        >
          <option value="">— выберите корпус —</option>
          {buildings.map((b) => (
            <option key={b.id} value={b.id}>{b.code} — {b.name}</option>
          ))}
        </select>
      </div>

      <div className={styles.pickerField}>
        <label className={styles.pickerLabel} htmlFor="fp-floor">Этаж</label>
        <select
          id="fp-floor"
          className={styles.pickerSelect}
          value={floorId ?? ''}
          disabled={buildingId === null || floorsLoading || floors.length === 0}
          onChange={(e) => {
            const v = e.target.value;
            setFloorId(v === '' ? null : parseInt(v, 10));
          }}
        >
          <option value="">
            {buildingId === null
              ? '— сначала выберите корпус —'
              : floorsLoading
                ? 'Загрузка этажей…'
                : floors.length === 0
                  ? '— в этом корпусе нет этажей —'
                  : '— выберите этаж —'}
          </option>
          {floors.map((f) => (
            <option key={f.id} value={f.id}>Этаж {f.number}</option>
          ))}
        </select>
      </div>

      <div className={styles.pickerActions}>
        <button
          type="button"
          className={styles.pickerBtnSecondary}
          onClick={onCancel}
        >
          К «Корпуса и этажи»
        </button>
        <button
          type="button"
          className={styles.pickerBtnPrimary}
          disabled={floorId === null}
          onClick={() => { if (floorId !== null) onPicked(floorId); }}
        >
          Открыть редактор →
        </button>
      </div>
    </div>
  );
};
