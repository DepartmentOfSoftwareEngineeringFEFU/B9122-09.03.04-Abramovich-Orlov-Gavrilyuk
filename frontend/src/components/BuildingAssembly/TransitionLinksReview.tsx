// Operator review of the auto-matched cross-floor stair/elevator links
// (subfeature D). Lists each link with an enable/disable toggle, shows unmatched
// nodes for awareness, lets the operator force-link a missing pair, and persists
// the override set. Hosted inside A's BuildingAssemblyPage. JSX only — the pure
// override math is in useTransitionLinks.helpers (unit-tested).

import React, { useState } from 'react';
import { useTransitionLinks } from '../../hooks/useTransitionLinks';
import { pendingAction } from '../../hooks/useTransitionLinks.helpers';
import type { TransitionLink, UnmatchedTransition } from '../../types/buildingNav';
import styles from './TransitionLinksReview.module.css';

const TYPE_LABEL: Record<string, string> = {
  staircase: 'Лестница',
  elevator: 'Лифт',
};

function linkLabel(link: TransitionLink): string {
  const type = TYPE_LABEL[link.type] ?? link.type;
  return `Этаж ${link.lower_floor_number} ↔ Этаж ${link.upper_floor_number} · ${type}`;
}

function unmatchedKey(u: UnmatchedTransition): string {
  return `${u.floor_id}:${u.node}`;
}

interface Props {
  buildingId: number;
}

export const TransitionLinksReview: React.FC<Props> = ({ buildingId }) => {
  const {
    links,
    unmatched,
    status,
    overrides,
    loading,
    saving,
    error,
    toggle,
    save,
  } = useTransitionLinks(buildingId);
  const [forceFrom, setForceFrom] = useState('');
  const [forceTo, setForceTo] = useState('');

  if (loading) {
    return <div className={styles.note}>Загрузка связей переходов…</div>;
  }
  if (status === 'not_aligned') {
    return (
      <div className={styles.note}>
        Этажи не выровнены — сначала выполните сборку здания (расставьте точки и
        нажмите «Решить»).
      </div>
    );
  }

  const isEnabled = (link: TransitionLink): boolean => {
    const p = pendingAction(overrides, link);
    if (p === 'disable') return false;
    if (p === 'force') return true;
    return link.enabled;
  };

  const forceSelected = (): void => {
    const a = unmatched.find((u) => unmatchedKey(u) === forceFrom);
    const b = unmatched.find((u) => unmatchedKey(u) === forceTo);
    if (!a || !b || a === b || a.type !== b.type) return;
    const [lo, hi] = a.floor_number <= b.floor_number ? [a, b] : [b, a];
    const synthetic: TransitionLink = {
      lower_floor_id: lo.floor_id,
      lower_floor_number: lo.floor_number,
      lower_node: lo.node,
      upper_floor_id: hi.floor_id,
      upper_floor_number: hi.floor_number,
      upper_node: hi.node,
      type: lo.type,
      source: 'forced',
      enabled: true,
      distance_m: 0,
    };
    toggle(synthetic, 'force');
    setForceFrom('');
    setForceTo('');
  };

  return (
    <div className={styles.panel}>
      <h3 className={styles.heading}>Связи переходов между этажами</h3>
      <p className={styles.note}>
        Лестницы и лифты, соединяющие этажи по вертикали. Найдены автоматически
        после сборки здания — по ним строится маршрут между этажами. Снимите
        галочку, если связь лишняя. Число справа — насколько точно совпали оси
        (меньше = точнее).
      </p>
      {error && <div className={styles.error}>{error}</div>}

      {links.length === 0 ? (
        <p className={styles.note}>Авто-связи не найдены.</p>
      ) : (
        <ul className={styles.list}>
          {links.map((link, idx) => (
            <li key={linkLabel(link) + link.lower_node + link.upper_node} className={styles.row}>
              <label className={styles.toggle}>
                <input
                  type="checkbox"
                  checked={isEnabled(link)}
                  onChange={() => toggle(link, 'disable')}
                />
                <span>
                  <span className={styles.idx}>{idx + 1}.</span> {linkLabel(link)}
                </span>
              </label>
              <span className={styles.meta}>
                {link.distance_m.toFixed(2)} м
                {link.source === 'forced' ? ' · вручную' : ''}
              </span>
            </li>
          ))}
        </ul>
      )}

      {unmatched.length > 0 && (
        <div className={styles.unmatched}>
          <h4 className={styles.subheading}>Без пары</h4>
          <ul className={styles.list}>
            {unmatched.map((u) => (
              <li key={unmatchedKey(u)} className={styles.note}>
                Этаж {u.floor_number}: {TYPE_LABEL[u.type] ?? u.type} ({u.node})
              </li>
            ))}
          </ul>
          <div className={styles.forceRow}>
            <select value={forceFrom} onChange={(e) => setForceFrom(e.target.value)}>
              <option value="">— этаж A —</option>
              {unmatched.map((u) => (
                <option key={unmatchedKey(u)} value={unmatchedKey(u)}>
                  Эт. {u.floor_number} · {TYPE_LABEL[u.type] ?? u.type}
                </option>
              ))}
            </select>
            <select value={forceTo} onChange={(e) => setForceTo(e.target.value)}>
              <option value="">— этаж B —</option>
              {unmatched.map((u) => (
                <option key={unmatchedKey(u)} value={unmatchedKey(u)}>
                  Эт. {u.floor_number} · {TYPE_LABEL[u.type] ?? u.type}
                </option>
              ))}
            </select>
            <button type="button" onClick={forceSelected} disabled={!forceFrom || !forceTo}>
              Связать
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        className={styles.saveBtn}
        onClick={() => void save()}
        disabled={saving || overrides.length === 0}
      >
        {saving ? 'Сохранение…' : 'Сохранить связи'}
      </button>
    </div>
  );
};

export default TransitionLinksReview;
