import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Building2, Boxes, Layers, X, ArrowRight, ArrowLeft } from 'lucide-react';
import {
  useRouteBuildings,
  type RouteBuilding,
  type RouteBuildingsVariant,
} from '../hooks/useRouteBuildings';
import { Multifloor3DRoutes } from '../components/MeshViewer/Multifloor3DRoutes';
import styles from './Multifloor3DRoutesPage.module.css';

// Building picker landing for "3D-маршруты" (subfeature D). Pick a corpus, then
// the dedicated 3D window opens inline: the stacked building model + a route
// builder (from/to floor+room) that traces the shortest cross-floor path through
// the matched stairs/elevators. The inner view (Multifloor3DRoutes) is the
// reusable piece, shared by two variants:
//   - 'admin'  (/admin/3d-routes) — all buildings, close→/admin, assembly link.
//   - 'public' (/3d-routes)       — published buildings, close→/, no admin links.

const getPluralFloors = (count: number): string => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod100 >= 11 && mod100 <= 19) return `${count} этажей`;
  if (mod10 === 1) return `${count} этаж`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} этажа`;
  return `${count} этажей`;
};

interface Multifloor3DRoutesPageProps {
  /** 'admin' = full admin chrome; 'public' = anonymous end-user screen. */
  variant?: RouteBuildingsVariant;
}

export const Multifloor3DRoutesPage: React.FC<Multifloor3DRoutesPageProps> = ({
  variant = 'admin',
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const isPublic = variant === 'public';
  const homePath = isPublic ? '/' : '/admin';
  const headerLabel = isPublic ? '3D-маршруты' : 'Тестовые маршруты';
  const { buildings, isLoading, error } = useRouteBuildings(variant);
  const [selected, setSelected] = useState<RouteBuilding | null>(null);

  // Deep-link from the public home search dropdown: navigate('/3d-routes',
  // { state: { buildingId } }) pre-opens that corpus once its data lands.
  // Consumed once (ref cleared on match) so "back to list" doesn't re-trigger.
  const preselectIdRef = useRef<number | null>(
    (location.state as { buildingId?: number } | null)?.buildingId ?? null,
  );

  useEffect(() => {
    const targetId = preselectIdRef.current;
    if (targetId == null) return;
    const target = buildings.find((b) => b.id === targetId);
    if (!target) return;
    preselectIdRef.current = null;
    if (target.floors_count >= 1) setSelected(target);
  }, [buildings]);

  if (selected) {
    return (
      <div className={`${styles.page} ${styles.pageFill}`}>
        <div className={styles.darkHeader}>
          <button
            className={styles.backBtn}
            type="button"
            onClick={() => setSelected(null)}
            title="К списку корпусов"
          >
            <ArrowLeft size={18} /> Корпуса
          </button>
          <span className={styles.darkHeaderLabel}>3D-маршруты — {selected.name}</span>
          <button
            className={styles.darkHeaderClose}
            type="button"
            onClick={() => navigate(homePath)}
            title="Закрыть"
          >
            <X size={20} />
          </button>
        </div>
        <div className={styles.viewerHost}>
          <Multifloor3DRoutes
            buildingId={selected.id}
            onGoToAssembly={
              isPublic
                ? undefined
                : () => navigate(`/admin/buildings/${selected.id}/assembly`)
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.darkHeader}>
        <span className={styles.darkHeaderLabel}>{headerLabel}</span>
        <button
          className={styles.darkHeaderClose}
          type="button"
          onClick={() => navigate(homePath)}
          title="Закрыть"
        >
          <X size={20} />
        </button>
      </div>

      <div className={styles.content}>
        <div className={styles.inner}>
          <header className={styles.pageHeader}>
            <h1 className={styles.title}>{headerLabel}</h1>
            <p className={styles.subtitle}>
              Выберите корпус, чтобы открыть его 3D-модель и построить маршрут
              между этажами — кратчайший путь проложится через лестницы и лифты.
            </p>
          </header>

          {isLoading && <div className={styles.stateMsg}>Загрузка корпусов…</div>}

          {!isLoading && error && (
            <div className={`${styles.stateMsg} ${styles.stateError}`}>{error}</div>
          )}

          {!isLoading && !error && buildings.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>
                <Building2 size={64} strokeWidth={1} />
              </div>
              <h3 className={styles.emptyTitle}>Нет корпусов</h3>
              <p className={styles.emptyText}>
                {isPublic
                  ? 'Пока нет опубликованных корпусов с этажами для просмотра.'
                  : 'Сначала создайте корпус и соберите его этажи на странице «Корпуса и этажи».'}
              </p>
              <button
                className={styles.btnPrimary}
                type="button"
                onClick={() => navigate(isPublic ? '/' : '/admin/buildings')}
              >
                {isPublic ? 'На главную' : 'Перейти к корпусам'}
              </button>
            </div>
          )}

          {!isLoading && !error && buildings.length > 0 && (
            <div className={styles.list}>
              {buildings.map((building) => {
                const ready = building.floors_count >= 1;
                return (
                  <button
                    key={building.id}
                    type="button"
                    className={`${styles.card} ${ready ? '' : styles.cardDisabled}`}
                    onClick={() => {
                      if (ready) setSelected(building);
                    }}
                    disabled={!ready}
                    title={
                      ready
                        ? 'Открыть 3D-модель и построить маршрут'
                        : 'Сначала добавьте этажи в корпус'
                    }
                  >
                    <div className={styles.cardIcon}>
                      <Boxes size={22} />
                    </div>
                    <div className={styles.cardMain}>
                      <div className={styles.cardName}>{building.name}</div>
                      <div className={styles.cardCode}>Код: {building.code}</div>
                    </div>
                    <div className={styles.cardMeta}>
                      <span className={styles.floorsBadge}>
                        <Layers size={14} /> {getPluralFloors(building.floors_count)}
                      </span>
                      {ready ? (
                        <span className={styles.openHint}>
                          Открыть <ArrowRight size={16} />
                        </span>
                      ) : (
                        <span className={styles.needHint}>нужны этажи</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Multifloor3DRoutesPage;
