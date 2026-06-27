import { useCallback, useState } from 'react';
import { buildingNavApi } from '../api/buildingNavApi';
import type { MultifloorRouteResponse } from '../types/buildingNav';
import {
  buildMultifloorRoutePayload,
  extractApiDetail,
} from './useMultifloorRoute.helpers';

/**
 * Cross-floor route state + runner (subfeature D). Holds the from/to floor+room
 * pickers, calls POST multifloor-route and surfaces the `status`
 * (success | no_path | not_aligned) to the panel. Logic-only hook (the pure
 * payload builder lives in useMultifloorRoute.helpers for unit tests).
 */
export function useMultifloorRoute(buildingId: number) {
  const [fromFloorId, setFromFloorId] = useState<number | null>(null);
  const [fromRoom, setFromRoom] = useState('');
  const [toFloorId, setToFloorId] = useState<number | null>(null);
  const [toRoom, setToRoom] = useState('');
  const [result, setResult] = useState<MultifloorRouteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (): Promise<void> => {
    const payload = buildMultifloorRoutePayload({
      fromFloorId,
      fromRoom,
      toFloorId,
      toRoom,
    });
    if (payload === null) {
      setError('Выберите этажи и комнаты отправления и назначения');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await buildingNavApi.postMultifloorRoute(buildingId, payload);
      setResult(res);
    } catch (err) {
      setError(extractApiDetail(err, 'Не удалось построить маршрут'));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [buildingId, fromFloorId, fromRoom, toFloorId, toRoom]);

  const reset = useCallback((): void => {
    setResult(null);
    setError(null);
  }, []);

  return {
    fromFloorId,
    setFromFloorId,
    fromRoom,
    setFromRoom,
    toFloorId,
    setToFloorId,
    toRoom,
    setToRoom,
    result,
    loading,
    error,
    run,
    reset,
  };
}
