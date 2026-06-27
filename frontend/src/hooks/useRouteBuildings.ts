// Building list for the 3D-routes picker, in two flavours:
//   - 'admin'  → GET /buildings (auth-required, ALL buildings)
//   - 'public' → GET /buildings?published=true (no auth, published only)
// The public flavour MUST avoid the admin list: that call 401s for an anonymous
// visitor, and the axios interceptor force-redirects to /login — which would
// break the public /3d-routes screen. Both shapes are normalised to RouteBuilding
// so the page renders one card list regardless of variant.

import { useState, useEffect } from 'react';
import { buildingsApi } from '../api/buildingsApi';

export type RouteBuildingsVariant = 'admin' | 'public';

export interface RouteBuilding {
  id: number;
  name: string;
  code: string;
  floors_count: number;
}

interface UseRouteBuildingsReturn {
  buildings: RouteBuilding[];
  isLoading: boolean;
  error: string | null;
}

export const useRouteBuildings = (
  variant: RouteBuildingsVariant,
): UseRouteBuildingsReturn => {
  const [buildings, setBuildings] = useState<RouteBuilding[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async (): Promise<void> => {
      setIsLoading(true);
      setError(null);
      try {
        const mapped: RouteBuilding[] =
          variant === 'public'
            ? (await buildingsApi.listPublished()).map((b) => ({
                id: b.id,
                name: b.name,
                code: b.code,
                floors_count: b.floors.length,
              }))
            : (await buildingsApi.list()).map((b) => ({
                id: b.id,
                name: b.name,
                code: b.code,
                floors_count: b.floors_count,
              }));
        if (!cancelled) setBuildings(mapped);
      } catch {
        if (!cancelled) setError('Ошибка загрузки корпусов');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [variant]);

  return { buildings, isLoading, error };
};
