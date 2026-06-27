// Full-screen 3D view for one building (reached from the assembly page's
// «Открыть 3D»). A proper screen — dark header + back button, matching the other
// admin screens — NOT a modal. Reuses the same `Multifloor3DRoutes` inner view
// as the «3D-маршруты» page, so the stacked model + cross-floor route builder are
// available right after aligning the floors. Styling shared with that page.

import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, X } from 'lucide-react';
import { Multifloor3DRoutes } from '../components/MeshViewer/Multifloor3DRoutes';
import styles from './Multifloor3DRoutesPage.module.css';

export const BuildingScenePage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const buildingId = id !== undefined ? parseInt(id, 10) : NaN;

  const backToAssembly = (): void =>
    navigate(`/admin/buildings/${buildingId}/assembly`);

  if (Number.isNaN(buildingId)) {
    return (
      <div className={styles.page}>
        <div className={styles.darkHeader}>
          <span className={styles.darkHeaderLabel}>3D-модель здания</span>
        </div>
        <div className={styles.content}>Некорректный идентификатор здания</div>
      </div>
    );
  }

  return (
    <div className={`${styles.page} ${styles.pageFill}`}>
      <div className={styles.darkHeader}>
        <button
          className={styles.backBtn}
          type="button"
          onClick={backToAssembly}
          title="Назад к сборке здания"
        >
          <ArrowLeft size={18} /> Назад
        </button>
        <span className={styles.darkHeaderLabel}>3D-модель здания</span>
        <button
          className={styles.darkHeaderClose}
          type="button"
          onClick={() => navigate('/admin/buildings')}
          title="Закрыть"
        >
          <X size={20} />
        </button>
      </div>
      <div className={styles.viewerHost}>
        <Multifloor3DRoutes buildingId={buildingId} onGoToAssembly={backToAssembly} />
      </div>
    </div>
  );
};

export default BuildingScenePage;
