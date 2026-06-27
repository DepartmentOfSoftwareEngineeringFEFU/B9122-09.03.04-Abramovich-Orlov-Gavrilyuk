import { useCallback, useEffect, useState } from 'react';
import { buildingNavApi } from '../api/buildingNavApi';
import type {
  TransitionLink,
  TransitionOverride,
  UnmatchedTransition,
} from '../types/buildingNav';
import { extractApiDetail } from './useMultifloorRoute.helpers';
import { applyLinkOverride } from './useTransitionLinks.helpers';

/**
 * Load the auto-matched cross-floor links + unmatched nodes for review, hold a
 * pending override set the operator edits, and persist it (subfeature D). The
 * pure override math lives in useTransitionLinks.helpers (unit-tested).
 */
export function useTransitionLinks(buildingId: number) {
  const [links, setLinks] = useState<TransitionLink[]>([]);
  const [unmatched, setUnmatched] = useState<UnmatchedTransition[]>([]);
  const [overrides, setOverrides] = useState<TransitionOverride[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const res = await buildingNavApi.getTransitionLinks(buildingId);
      setLinks(res.links);
      setUnmatched(res.unmatched);
      setStatus(res.status);
      setOverrides([]); // server state already reflects saved overrides
    } catch (err) {
      setError(extractApiDetail(err, 'Не удалось загрузить связи переходов'));
    } finally {
      setLoading(false);
    }
  }, [buildingId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = useCallback(
    (link: TransitionLink, action: 'disable' | 'force'): void => {
      setOverrides((prev) => applyLinkOverride(prev, link, action));
    },
    [],
  );

  const save = useCallback(async (): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      await buildingNavApi.putTransitionLinks(buildingId, overrides);
      await load();
    } catch (err) {
      setError(extractApiDetail(err, 'Не удалось сохранить связи переходов'));
    } finally {
      setSaving(false);
    }
  }, [buildingId, overrides, load]);

  return {
    links,
    unmatched,
    status,
    overrides,
    loading,
    saving,
    error,
    load,
    toggle,
    save,
  };
}
