import React, { useState } from 'react';
import styles from './FloorSectionsTable.module.css';
import wizardStyles from './WizardStep.module.css';
import { NewSectionDialog } from './NewSectionDialog';
import type { SectionDraft } from '../../hooks/useFloorEditorWizard';

interface FloorSectionsTableProps {
  sectionDrafts: SectionDraft[];
  isDirty: boolean;
  isLoading: boolean;
  onUpdateSectionDraft: (idx: number, partial: Partial<SectionDraft>) => void;
  onDeleteSectionDraft: (idx: number) => void;
  onSave: () => Promise<void>;
  onEditScheme: () => void;
  onSwitchToOverview: () => void;
}

export const FloorSectionsTable: React.FC<FloorSectionsTableProps> = ({
  sectionDrafts,
  isDirty,
  isLoading,
  onUpdateSectionDraft,
  onDeleteSectionDraft,
  onSave,
  onEditScheme,
  onSwitchToOverview,
}) => {
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameTargetIdx, setRenameTargetIdx] = useState<number | null>(null);

  const handleRenameConfirm = (num: number, _color: string) => {
    if (renameTargetIdx !== null) {
      onUpdateSectionDraft(renameTargetIdx, { number: num });
    }
    setRenameDialogOpen(false);
    setRenameTargetIdx(null);
  };

  const handleDelete = (idx: number) => {
    const section = sectionDrafts[idx];
    if (window.confirm(`Удалить отсек №${section.number}? Действие нельзя отменить без перезагрузки`)) {
      onDeleteSectionDraft(idx);
    }
  };

  const handleEditScheme = () => {
    if (window.confirm('Перейти в редактор схемы? Несохранённые изменения будут потеряны.')) {
      onEditScheme();
    }
  };

  const takenNumbers = sectionDrafts
    .filter((_, i) => i !== renameTargetIdx)
    .map((d) => d.number);

  return (
    <div className={styles.page}>
      {/* Top bar */}
      <div className={styles.topBar}>
        <button className={styles.backBtn} onClick={onSwitchToOverview} type="button">
          ▦ Графический вид
        </button>
        <h2 className={styles.title}>Итоговый список отсеков</h2>
        <div className={styles.topActions}>
          <button className={styles.exportBtn} type="button" title="Экспорт схемы (в разработке)">
            ↓ Экспорт схемы
          </button>
          <button className={styles.editSchemeBtn} onClick={handleEditScheme} type="button">
            Редактировать схему
          </button>
          <button
            className={styles.saveBtn}
            onClick={() => void onSave()}
            disabled={isLoading || !isDirty}
            type="button"
          >
            Сохранить изменения
          </button>
        </div>
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Номер отсека</th>
              <th className={styles.th}>Описание</th>
              <th className={styles.th}>План</th>
              <th className={styles.th}>Статус</th>
              <th className={styles.th}>Действия</th>
            </tr>
          </thead>
          <tbody>
            {sectionDrafts.length === 0 && (
              <tr>
                <td className={styles.td} colSpan={5} style={{ textAlign: 'center', color: '#999' }}>
                  Нет отсеков
                </td>
              </tr>
            )}
            {sectionDrafts.map((d, idx) => {
              const plan = d.reconstruction_brief;
              const isBound = d.reconstruction_id !== null;
              return (
                <tr key={idx} className={styles.tr}>
                  <td className={styles.td}>
                    <strong>{d.number}</strong>
                  </td>
                  <td className={styles.td} style={{ color: '#999' }}>
                    {/* Description is client-side only; not persisted to backend */}
                    —
                  </td>
                  <td className={styles.td}>
                    {plan && plan.name ? plan.name : isBound ? `План #${d.reconstruction_id}` : '—'}
                  </td>
                  <td className={styles.td}>
                    <span className={`${styles.badge} ${isBound ? styles.badgeBound : styles.badgeUnbound}`}>
                      {isBound ? 'Привязан' : 'Не привязан'}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <div className={styles.actionBtns}>
                      <button
                        className={styles.actionBtn}
                        title="Изменить номер"
                        onClick={() => {
                          setRenameTargetIdx(idx);
                          setRenameDialogOpen(true);
                        }}
                        type="button"
                      >
                        ✏
                      </button>
                      <button
                        className={`${styles.actionBtn} ${styles.actionBtnDelete}`}
                        title="Удалить"
                        onClick={() => handleDelete(idx)}
                        type="button"
                      >
                        🗑
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <footer className={wizardStyles.footer}>
        <button className={wizardStyles.btnBack} onClick={onSwitchToOverview} type="button">
          ← Назад
        </button>
      </footer>

      <NewSectionDialog
        open={renameDialogOpen}
        initialNumber={renameTargetIdx !== null ? sectionDrafts[renameTargetIdx]?.number ?? null : null}
        takenNumbers={takenNumbers}
        onConfirm={handleRenameConfirm}
        onCancel={() => { setRenameDialogOpen(false); setRenameTargetIdx(null); }}
      />
    </div>
  );
};
