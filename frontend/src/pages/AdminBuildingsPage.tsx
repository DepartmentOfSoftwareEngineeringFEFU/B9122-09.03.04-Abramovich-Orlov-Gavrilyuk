import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Building2, Layers, Plus, Edit2, Trash2, Eye,
  ChevronDown, X, AlertTriangle, CheckCircle, AlertCircle,
  MoreVertical, MoreHorizontal, GripVertical, Check, Map as MapIcon, ImageOff, Boxes,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useBuildings } from '../hooks/useBuildings';
import { useFloors } from '../hooks/useFloors';
import { reconstructionApi, type ReconstructionListItem } from '../api/apiService';
import type { Building, Floor } from '../types/hierarchy';
import styles from './AdminBuildingsPage.module.css';

// ========================================================
// Helpers
// ========================================================

const BUILDING_CODE_RE = /^[A-Za-z]{1,5}$/;
function validateBuildingCode(code: string): string | null {
  if (!code.trim()) return 'Код обязателен';
  if (!BUILDING_CODE_RE.test(code.trim())) return 'Код: 1–5 латинских букв';
  return null;
}
function validateBuildingName(name: string): string | null {
  if (!name.trim()) return 'Название обязательно';
  return null;
}
function validateFloorNumber(raw: string): string | null {
  const n = parseInt(raw, 10);
  if (isNaN(n)) return 'Введите целое число';
  if (n < 0) return 'Номер этажа ≥ 0';
  if (n > 50) return 'Номер этажа ≤ 50';
  return null;
}

function extractApiError(err: unknown, fallback: string): string {
  if (err !== null && typeof err === 'object') {
    const e = err as Record<string, unknown>;
    if ('response' in e && e.response !== null && typeof e.response === 'object') {
      const response = e.response as Record<string, unknown>;
      if ('status' in response && response.status === 409) return fallback;
      if ('data' in response && response.data !== null && typeof response.data === 'object') {
        const data = response.data as Record<string, unknown>;
        if ('detail' in data && typeof data.detail === 'string') return data.detail;
      }
    }
    if ('message' in e && typeof e.message === 'string') return e.message;
  }
  return fallback;
}

const getPluralFloors = (count: number) => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod100 >= 11 && mod100 <= 19) return `${count} этажей`;
  if (mod10 === 1) return `${count} этаж`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} этажа`;
  return `${count} этажей`;
};

const getPluralSections = (count: number) => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod100 >= 11 && mod100 <= 19) return `${count} отсеков`;
  if (mod10 === 1) return `${count} отсек`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} отсека`;
  return `${count} отсеков`;
};

// ========================================================
// Toast hook
// ========================================================
interface ToastState { message: string; isError: boolean; }
function useToast() {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback((message: string, isError = false) => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    setToast({ message, isError });
    timerRef.current = setTimeout(() => setToast(null), 4000);
  }, []);
  useEffect(() => () => { if (timerRef.current !== null) clearTimeout(timerRef.current); }, []);
  return { toast, show };
}

// ========================================================
// BuildingCard
// ========================================================
interface BuildingCardProps {
  building: Building;
  onEdit: (b: Building) => void;
  onDelete: (b: Building) => void;
  onAddFloor: (b: Building) => void;
  onDeleteFloor: (f: Floor, b: Building) => void;
  /** When this changes and matches building.id, the card reloads its floors. */
  floorRefreshSignal: { buildingId: number; tick: number } | null;
}

const BuildingCard: React.FC<BuildingCardProps> = ({
  building, onEdit, onDelete, onAddFloor, onDeleteFloor, floorRefreshSignal,
}) => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const { floors, isLoading: floorsLoading, loadForBuilding } = useFloors();
  const [activeDropdown, setActiveDropdown] = useState(false);
  const [editing, setEditing] = useState<{ type: 'building' | 'floor'; id: number; value: string } | null>(null);

  const handleExpand = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    if (next && floors.length === 0 && !floorsLoading) void loadForBuilding(building.id);
  }, [expanded, floors.length, floorsLoading, loadForBuilding, building.id]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!activeDropdown) return;
    const handler = () => setActiveDropdown(false);
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [activeDropdown]);

  // Always expand when floors load
  useEffect(() => {
    if (floors.length > 0 && !expanded) setExpanded(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floors.length]);

  // Reload floors when parent signals a change for this building (create/delete)
  useEffect(() => {
    if (floorRefreshSignal !== null && floorRefreshSignal.buildingId === building.id) {
      setExpanded(true);
      void loadForBuilding(building.id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floorRefreshSignal]);

  const startEditBuilding = () => {
    setEditing({ type: 'building', id: building.id, value: building.name });
    setActiveDropdown(false);
  };

  const saveEdit = () => {
    if (!editing || !editing.value.trim()) return;
    if (editing.type === 'building') onEdit({ ...building, name: editing.value.trim() });
    setEditing(null);
  };

  const isEditingBuilding = editing?.type === 'building' && editing.id === building.id;

  return (
    <div className={styles.buildingCard}>
      {/* Building row */}
      <div onClick={handleExpand} className={`${styles.buildingRow} ${isEditingBuilding ? styles.buildingRowEditing : ''}`}>
        <div className={styles.buildingIcons}>
          <GripVertical size={18} className={styles.gripIcon} />
          <Building2 size={20} className={styles.buildingIcon} />
        </div>

        {!editing && (
          <div className={`${styles.dropdownWrap} ${styles.dropdownWrapLeft}`}>
            <button
              className={styles.dropdownTrigger}
              type="button"
              onClick={(e) => { e.stopPropagation(); setActiveDropdown(!activeDropdown); }}
              aria-label="Меню корпуса"
            >
              <MoreVertical size={18} />
            </button>
            {activeDropdown && (
              <div className={`${styles.dropdownMenu} ${styles.dropdownMenuLeft}`}>
                <button className={styles.dropdownItem} type="button" onClick={() => { setActiveDropdown(false); onAddFloor(building); }}>
                  <Plus size={16} /> Добавить этаж
                </button>
                <button className={styles.dropdownItem} type="button" onClick={startEditBuilding}>
                  <Edit2 size={16} /> Редактировать корпус
                </button>
                <div className={styles.dropdownDivider} />
                <button className={`${styles.dropdownItem} ${styles.dropdownItemDanger}`} type="button" onClick={() => { setActiveDropdown(false); onDelete(building); }}>
                  <Trash2 size={16} /> Удалить корпус
                </button>
              </div>
            )}
          </div>
        )}

        {isEditingBuilding ? (
          <div className={styles.inlineEdit}>
            <input
              className={styles.inlineInput}
              value={editing!.value}
              onChange={(e) => setEditing({ ...editing!, value: e.target.value })}
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditing(null); }}
            />
            <button className={styles.inlineSave} onClick={saveEdit} type="button"><Check size={16} /></button>
            <button className={styles.inlineCancel} onClick={() => setEditing(null)} type="button"><X size={16} /></button>
          </div>
        ) : (
          <div className={styles.buildingName}>{building.name}</div>
        )}

        {!editing && (
          <div className={styles.buildingActions}>
            {building.floors_count >= 2 && (
              <button
                className={styles.btnAssemble}
                type="button"
                onClick={(e) => { e.stopPropagation(); navigate(`/admin/buildings/${building.id}/assembly`); }}
                title="Собрать здание — вертикальная стыковка этажей"
              >
                <Boxes size={14} /> Собрать здание
              </button>
            )}
            <span className={styles.floorsBadge}>
              <Layers size={14} /> {getPluralFloors(building.floors_count)}
            </span>
            <button className={styles.btnGhost} onClick={handleExpand} type="button" aria-label={expanded ? 'Свернуть' : 'Развернуть'}>
              <ChevronDown size={18} style={{ transition: 'transform 0.2s', transform: expanded ? 'rotate(180deg)' : 'none' }} />
            </button>
          </div>
        )}
      </div>

      {/* Tree: floors */}
      {expanded && (
        <div className={styles.treeSection}>
          {floorsLoading && (
            <div style={{ padding: '0.75rem 1rem 0.75rem 89px', color: '#9ca3af', fontSize: '0.8125rem' }}>
              Загрузка этажей...
            </div>
          )}

          {!floorsLoading && floors.map((floor) => (
            <FloorRow
              key={floor.id}
              floor={floor}
              building={building}
              isEditing={editing?.type === 'floor' && editing.id === floor.id}
              editingValue={editing?.type === 'floor' && editing.id === floor.id ? editing.value : null}
              onEditingChange={(value) => editing && setEditing({ ...editing, value })}
              onSaveEdit={saveEdit}
              onCancelEdit={() => setEditing(null)}
              onDeleteFloor={onDeleteFloor}
              navigate={navigate}
              anySiblingEditing={editing !== null}
            />
          ))}

          {/* Add floor button */}
          <div className={styles.addFloorWrap}>
            <div className={styles.treeLineShort} />
            <div className={styles.treeLineH} />
            <div className={styles.addFloorInner}>
              <button className={styles.addFloorBtn} type="button" onClick={() => onAddFloor(building)}>
                <Plus size={16} /> Добавить этаж
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ========================================================
// FloorRow — single floor row with expandable sections grid
// ========================================================
interface FloorRowProps {
  floor: Floor;
  building: Building;
  isEditing: boolean;
  editingValue: string | null;
  onEditingChange: (value: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDeleteFloor: (f: Floor, b: Building) => void;
  navigate: ReturnType<typeof useNavigate>;
  /** True if any row in the parent card is in inline-edit mode (suppresses hover actions). */
  anySiblingEditing: boolean;
}

const FloorRow: React.FC<FloorRowProps> = ({
  floor, building, isEditing, editingValue, onEditingChange,
  onSaveEdit, onCancelEdit, onDeleteFloor, navigate, anySiblingEditing,
}) => {
  const [expanded, setExpanded] = useState(false);
  // The grid shows reconstructions bound to this floor (i.e. plans uploaded via
  // /upload?floor_id=N), NOT geometric Section entities — those only exist once
  // the admin draws them in the floor editor.
  const [reconstructions, setReconstructions] = useState<ReconstructionListItem[]>([]);
  const [recsLoading, setRecsLoading] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ReconstructionListItem | null>(null);

  const loadReconstructions = useCallback(async () => {
    setRecsLoading(true);
    try {
      const items = await reconstructionApi.getReconstructions({ floorId: floor.id });
      setReconstructions(items);
    } catch {
      // Non-fatal: leave grid empty, user can collapse/re-expand to retry
    } finally {
      setRecsLoading(false);
    }
  }, [floor.id]);

  // Eager load: the sections counter shows reconstructions.length, which must be
  // populated before the user expands the row. One GET per floor on mount.
  useEffect(() => {
    void loadReconstructions();
  }, [loadReconstructions]);

  const toggleExpand = useCallback(() => {
    setExpanded((v) => !v);
  }, []);

  const handleAddSection = useCallback(() => {
    navigate(`/upload?building_id=${building.id}&floor_id=${floor.id}`);
  }, [navigate, building.id, floor.id]);

  const handleEditReconstruction = useCallback((rec: ReconstructionListItem) => {
    navigate(`/admin/edit/${rec.id}`);
  }, [navigate]);

  const handleConfirmDelete = useCallback(async () => {
    if (pendingDelete === null) return;
    try {
      await reconstructionApi.deleteReconstruction(pendingDelete.id);
      setReconstructions((prev) => prev.filter((r) => r.id !== pendingDelete.id));
    } finally {
      setPendingDelete(null);
    }
  }, [pendingDelete]);

  return (
    <div className={styles.floorWrap}>
      <div className={styles.treeLine} />
      <div className={styles.treeLineH} />
      <div onClick={toggleExpand} className={`${styles.floorRow} ${isEditing ? styles.floorRowEditing : ''}`}>
        <div className={styles.floorRowIcons}>
          <GripVertical size={16} className={styles.gripIcon} />
          <button
            type="button"
            className={styles.floorExpandBtn}
            
            aria-label={expanded ? 'Свернуть отсеки' : 'Развернуть отсеки'}
            title={expanded ? 'Свернуть отсеки' : 'Показать отсеки'}
          >
            <ChevronDown
              size={16}
              style={{ transition: 'transform 0.2s', transform: expanded ? 'rotate(180deg)' : 'none' }}
            />
          </button>
          <Layers size={16} style={{ color: '#6b7280' }} />
        </div>

        {isEditing ? (
          <div className={styles.inlineEdit}>
            <input
              className={styles.inlineInput}
              value={editingValue ?? ''}
              onChange={(e) => onEditingChange(e.target.value)}
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') onSaveEdit(); if (e.key === 'Escape') onCancelEdit(); }}
            />
            <button className={styles.inlineSave} onClick={onSaveEdit} type="button"><Check size={16} /></button>
            <button className={styles.inlineCancel} onClick={onCancelEdit} type="button"><X size={16} /></button>
          </div>
        ) : (
          <div className={styles.floorName}>
            <span className={styles.floorNameText}>Этаж {floor.number}</span>
            {floor.sections_count === 0 && (
              <button
                type="button"
                className={styles.btnCreateMap}
                onClick={() => navigate(`/admin/floor-editor?floor_id=${floor.id}`)}
                title="Создать карту отсеков для этого этажа"
              >
                <MapIcon size={14} /> Создать карту отсеков
              </button>
            )}
            <span className={styles.sectionsCountBadge} title="Количество отсеков на этаже">
              <Layers size={12} /> {getPluralSections(reconstructions.length)}
            </span>
          </div>
        )}

        {!anySiblingEditing && (
          <div className={styles.floorActions}>
            {floor.sections_count > 0 && (
              <button className={styles.btnGhost} type="button" title="Открыть редактор карты отсеков" onClick={() => navigate(`/admin/floor-editor?floor_id=${floor.id}`)}>
                <Edit2 size={16} /> Редактировать карту отсеков
              </button>
            )}
            <button className={`${styles.btnGhost} ${styles.btnGhostDanger}`} type="button" title="Удалить этаж" onClick={() => onDeleteFloor(floor, building)}>
              <Trash2 size={16} />
            </button>
          </div>
        )}
      </div>

      {expanded && (
        <div className={styles.sectionsPanel}>
          {recsLoading ? (
            <div className={styles.sectionsLoading}>Загрузка отсеков...</div>
          ) : (
            <div className={styles.sectionsGrid}>
              {reconstructions.map((rec) => (
                <SectionCard
                  key={rec.id}
                  reconstruction={rec}
                  onEdit={handleEditReconstruction}
                  onRequestDelete={setPendingDelete}
                />
              ))}
              <button
                type="button"
                className={styles.addSectionTile}
                onClick={handleAddSection}
                title="Добавить отсек — загрузить план"
              >
                <div className={styles.addSectionPlus}>
                  <Plus size={28} strokeWidth={2.5} />
                </div>
                <span className={styles.addSectionLabel}>Добавить отсек</span>
              </button>
            </div>
          )}
        </div>
      )}

      {pendingDelete !== null && (
        <ConfirmDeleteModal
          title="Удалить отсек?"
          message={`Вы действительно хотите удалить «${pendingDelete.name}»? Это действие нельзя отменить.`}
          onClose={() => setPendingDelete(null)}
          onConfirm={handleConfirmDelete}
        />
      )}
    </div>
  );
};

// ========================================================
// SectionCard — thumbnail tile for an uploaded plan (reconstruction), with 3-dot menu (edit/delete)
// ========================================================
interface SectionCardProps {
  reconstruction: ReconstructionListItem;
  onEdit: (rec: ReconstructionListItem) => void;
  onRequestDelete: (rec: ReconstructionListItem) => void;
}

const SectionCard: React.FC<SectionCardProps> = ({ reconstruction, onEdit, onRequestDelete }) => {
  const preview = reconstruction.preview_url;
  // Prefer the section number when the reconstruction is already bound to one,
  // otherwise fall back to the user-typed plan name.
  const label = reconstruction.section !== null
    ? `Отсек ${reconstruction.section.number}`
    : reconstruction.name;
  const [menuOpen, setMenuOpen] = useState(false);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const handler = () => setMenuOpen(false);
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [menuOpen]);

  return (
    <div className={styles.sectionCard} title={label}>
      <div className={styles.sectionThumb}>
        {preview !== null ? (
          <img src={preview} alt={label} className={styles.sectionThumbImg} />
        ) : (
          <div className={styles.sectionThumbEmpty}>
            <ImageOff size={28} />
          </div>
        )}
      </div>

      {/* Menu lives outside .sectionThumb because the thumb clips overflow. */}
      <div className={styles.sectionMenuWrap}>
        <button
          type="button"
          className={styles.sectionMenuTrigger}
          onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
          aria-label="Меню отсека"
          title="Действия"
        >
          <MoreHorizontal size={14} />
        </button>
        {menuOpen && (
          <div className={`${styles.dropdownMenu} ${styles.sectionMenuDropdown}`} onClick={(e) => e.stopPropagation()}>
            <button
              className={styles.dropdownItem}
              type="button"
              onClick={() => { setMenuOpen(false); onEdit(reconstruction); }}
              title="Редактировать план отсека"
            >
              <Edit2 size={16} /> Редактировать
            </button>
            <div className={styles.dropdownDivider} />
            <button
              className={`${styles.dropdownItem} ${styles.dropdownItemDanger}`}
              type="button"
              onClick={() => { setMenuOpen(false); onRequestDelete(reconstruction); }}
            >
              <Trash2 size={16} /> Удалить
            </button>
          </div>
        )}
      </div>

      <span className={styles.sectionLabel}>{label}</span>
    </div>
  );
};

// ========================================================
// Modals
// ========================================================

interface BuildingFormValues { code: string; name: string; }

const CreateBuildingModal: React.FC<{ onClose: () => void; onSubmit: (v: BuildingFormValues) => Promise<void> }> = ({ onClose, onSubmit }) => {
  const [values, setValues] = useState<BuildingFormValues>({ code: '', name: '' });
  const [errors, setErrors] = useState<Partial<BuildingFormValues>>({});
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Partial<BuildingFormValues> = {};
    const ce = validateBuildingCode(values.code); if (ce) next.code = ce;
    const ne = validateBuildingName(values.name); if (ne) next.name = ne;
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setSubmitting(true);
    try { await onSubmit({ ...values, code: values.code.trim().toUpperCase() }); } finally { setSubmitting(false); }
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>Добавить корпус</h2>
          <button className={styles.modalCloseBtn} onClick={onClose} type="button"><X size={18} /></button>
        </div>
        <form onSubmit={(e) => { void handleSubmit(e); }}>
          <div className={styles.modalBody}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Код корпуса <span className={styles.formRequired}>*</span></label>
              <input className={`${styles.formInput} ${errors.code ? styles.formInputError : ''}`} type="text" maxLength={5} value={values.code} onChange={(e) => setValues(v => ({ ...v, code: e.target.value }))} placeholder="A" autoFocus />
              {errors.code && <p className={styles.formError}>{errors.code}</p>}
              <p className={styles.formHint}>1–5 латинских букв</p>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Название <span className={styles.formRequired}>*</span></label>
              <input className={`${styles.formInput} ${errors.name ? styles.formInputError : ''}`} type="text" value={values.name} onChange={(e) => setValues(v => ({ ...v, name: e.target.value }))} placeholder="Корпус A" />
              {errors.name && <p className={styles.formError}>{errors.name}</p>}
            </div>
          </div>
          <div className={styles.modalFooter}>
            <button type="button" className={styles.btnSecondaryText} onClick={onClose}>Отмена</button>
            <button type="submit" className={styles.btnPrimary} disabled={submitting}>{submitting ? 'Создание...' : 'Создать'}</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const CreateFloorModal: React.FC<{ buildingCode: string; onClose: () => void; onSubmit: (n: number) => Promise<void> }> = ({ buildingCode, onClose, onSubmit }) => {
  const [raw, setRaw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validateFloorNumber(raw);
    if (err) { setError(err); return; }
    setSubmitting(true);
    try { await onSubmit(parseInt(raw, 10)); } finally { setSubmitting(false); }
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>Добавить этаж в {buildingCode}</h2>
          <button className={styles.modalCloseBtn} onClick={onClose} type="button"><X size={18} /></button>
        </div>
        <form onSubmit={(e) => { void handleSubmit(e); }}>
          <div className={styles.modalBody}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Номер этажа <span className={styles.formRequired}>*</span></label>
              <input className={`${styles.formInput} ${error ? styles.formInputError : ''}`} type="number" min={0} max={50} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="1" autoFocus />
              {error && <p className={styles.formError}>{error}</p>}
              <p className={styles.formHint}>Диапазон: 0–50</p>
            </div>
          </div>
          <div className={styles.modalFooter}>
            <button type="button" className={styles.btnSecondaryText} onClick={onClose}>Отмена</button>
            <button type="submit" className={styles.btnPrimary} disabled={submitting}>{submitting ? 'Создание...' : 'Добавить'}</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const ConfirmDeleteModal: React.FC<{
  title: string; message: string; onClose: () => void; onConfirm: () => Promise<void>;
}> = ({ title, message, onClose, onConfirm }) => {
  const [submitting, setSubmitting] = useState(false);
  const handle = async () => { setSubmitting(true); try { await onConfirm(); } finally { setSubmitting(false); } };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalBody} style={{ paddingTop: '1.5rem' }}>
          <div className={styles.confirmRow}>
            <div className={styles.confirmIcon}><AlertTriangle size={24} /></div>
            <div>
              <h3 className={styles.confirmTitle}>{title}</h3>
              <p className={styles.confirmText}>{message}</p>
            </div>
          </div>
        </div>
        <div className={styles.modalFooter}>
          <button type="button" className={styles.btnOutline} onClick={onClose}>Отмена</button>
          <button type="button" className={styles.btnDanger} onClick={() => { void handle(); }} disabled={submitting}>
            {submitting ? 'Удаление...' : 'Удалить'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ========================================================
// Modal state
// ========================================================
type ModalState =
  | { kind: 'none' }
  | { kind: 'createBuilding' }
  | { kind: 'editBuilding'; building: Building }
  | { kind: 'deleteBuilding'; building: Building }
  | { kind: 'createFloor'; building: Building }
  | { kind: 'deleteFloor'; floor: Floor; building: Building };

// ========================================================
// Page
// ========================================================
export const AdminBuildingsPage: React.FC = () => {
  const { buildings, isLoading, error, refetch: refetchBuildings, createBuilding, updateBuilding, deleteBuilding } = useBuildings();
  const { createFloor, deleteFloor } = useFloors();
  const [modal, setModal] = useState<ModalState>({ kind: 'none' });
  const { toast, show: showToast } = useToast();
  const closeModal = useCallback(() => setModal({ kind: 'none' }), []);

  // Each BuildingCard owns its own useFloors() instance, so the parent's create/delete
  // does NOT update the card's local floors array. Bump this signal after a successful
  // mutation and the matching card reloads its list (and auto-expands).
  const [floorRefreshSignal, setFloorRefreshSignal] = useState<{ buildingId: number; tick: number } | null>(null);
  const bumpFloorRefresh = useCallback((buildingId: number) => {
    setFloorRefreshSignal((prev) => ({ buildingId, tick: (prev?.tick ?? 0) + 1 }));
  }, []);

  const handleCreateBuilding = useCallback(async (values: BuildingFormValues) => {
    try {
      await createBuilding({ code: values.code, name: values.name });
      showToast(`Корпус ${values.code} создан`);
      closeModal();
    } catch (err: unknown) { showToast(extractApiError(err, `Корпус с кодом ${values.code} уже существует`), true); }
  }, [createBuilding, showToast, closeModal]);

  const handleUpdateBuilding = useCallback(async (building: Building) => {
    try {
      await updateBuilding(building.id, { name: building.name });
      showToast('Корпус обновлён');
    } catch (err: unknown) { showToast(extractApiError(err, 'Ошибка обновления'), true); }
  }, [updateBuilding, showToast]);

  const handleDeleteBuilding = useCallback(async (building: Building) => {
    try {
      await deleteBuilding(building.id);
      showToast(`Корпус ${building.code} удалён`);
      closeModal();
    } catch (err: unknown) { showToast(extractApiError(err, 'Ошибка удаления'), true); }
  }, [deleteBuilding, showToast, closeModal]);

  const handleCreateFloor = useCallback(async (building: Building, number: number) => {
    try {
      await createFloor(building.id, number);
      showToast(`Этаж ${number} создан`);
      closeModal();
      bumpFloorRefresh(building.id);
      void refetchBuildings();
    } catch (err: unknown) { showToast(extractApiError(err, `Этаж ${number} уже существует`), true); }
  }, [createFloor, showToast, closeModal, bumpFloorRefresh, refetchBuildings]);

  const handleDeleteFloor = useCallback(async (floor: Floor, building: Building) => {
    try {
      await deleteFloor(floor.id);
      showToast(`Этаж ${floor.number} удалён`);
      closeModal();
      bumpFloorRefresh(building.id);
      void refetchBuildings();
    } catch (err: unknown) { showToast(extractApiError(err, 'Ошибка удаления этажа'), true); }
  }, [deleteFloor, showToast, closeModal, bumpFloorRefresh, refetchBuildings]);

  // --- Skeleton ---
  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.content}>
          <div className={styles.inner}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
              <div>
                <div className={styles.skeletonBar} style={{ width: 200, height: 28, marginBottom: 8 }} />
                <div className={styles.skeletonBar} style={{ width: 300, height: 16 }} />
              </div>
              <div className={styles.skeletonBar} style={{ width: 160, height: 40, background: 'rgba(255,85,0,0.3)' }} />
            </div>
            <div className={styles.skeletonCard}>
              {[1, 2, 3].map(i => (<div key={i} className={styles.skeletonRow} style={{ marginBottom: i < 3 ? 8 : 0 }}>
                <div className={styles.skeletonBlock} style={{ width: 24, height: 24 }} />
                <div className={styles.skeletonBlock} style={{ width: 140, height: 20 }} />
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 16 }}>
                  <div className={styles.skeletonBlock} style={{ width: 70, height: 20 }} />
                  <div className={styles.skeletonBlock} style={{ width: 20, height: 20 }} />
                </div>
              </div>))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.content}><div className={styles.inner} style={{ textAlign: 'center', padding: '3rem', color: '#ef4444' }}>{error}</div></div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.content}>
        <div className={styles.inner}>
          <header className={styles.pageHeader}>
            <div>
              <h1 className={styles.title}>Корпуса и этажи</h1>
              <p className={styles.subtitle}>Управление иерархией зданий, этажей и планов</p>
            </div>
            <button className={styles.btnPrimary} type="button" onClick={() => setModal({ kind: 'createBuilding' })}>
              <Plus size={16} /> Добавить корпус
            </button>
          </header>

          {buildings.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}><Building2 size={64} strokeWidth={1} /></div>
              <h3 className={styles.emptyTitle}>Нет корпусов</h3>
              <p className={styles.emptyText}>Добавьте первый корпус, чтобы начать работу с иерархией здания</p>
              <button className={styles.btnPrimary} type="button" onClick={() => setModal({ kind: 'createBuilding' })}>
                <Plus size={16} /> Добавить корпус
              </button>
            </div>
          ) : (
            <div className={styles.buildingList}>
              {buildings.map(building => (
                <BuildingCard
                  key={building.id}
                  building={building}
                  onEdit={(b) => { void handleUpdateBuilding(b); }}
                  onDelete={(b) => setModal({ kind: 'deleteBuilding', building: b })}
                  onAddFloor={(b) => setModal({ kind: 'createFloor', building: b })}
                  onDeleteFloor={(f, b) => setModal({ kind: 'deleteFloor', floor: f, building: b })}
                  floorRefreshSignal={floorRefreshSignal}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {modal.kind === 'createBuilding' && <CreateBuildingModal onClose={closeModal} onSubmit={handleCreateBuilding} />}
      {modal.kind === 'createFloor' && <CreateFloorModal buildingCode={modal.building.code} onClose={closeModal} onSubmit={(n) => handleCreateFloor(modal.building, n)} />}
      {modal.kind === 'deleteBuilding' && (
        <ConfirmDeleteModal
          title="Удалить корпус?"
          message={`Вы действительно хотите удалить корпус «${modal.building.name}»? Все этажи и отсеки внутри него будут удалены. Это действие нельзя отменить.`}
          onClose={closeModal}
          onConfirm={() => handleDeleteBuilding(modal.building)}
        />
      )}
      {modal.kind === 'deleteFloor' && (
        <ConfirmDeleteModal
          title="Удалить этаж?"
          message={`Вы действительно хотите удалить этаж ${modal.floor.number} корпуса «${modal.building.code}»? Все отсеки этажа будут удалены. Это действие нельзя отменить.`}
          onClose={closeModal}
          onConfirm={() => handleDeleteFloor(modal.floor, modal.building)}
        />
      )}

      {/* Toast */}
      {toast !== null && (
        <div className={`${styles.toast} ${toast.isError ? styles.toastError : ''}`}>
          {toast.isError ? <AlertCircle size={20} className={styles.toastIconError} /> : <CheckCircle size={20} className={styles.toastIconSuccess} />}
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default AdminBuildingsPage;
