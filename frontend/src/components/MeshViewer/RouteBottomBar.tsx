import React from 'react';
import styles from './RouteBottomBar.module.css';
import type { RoomAnnotation } from '../../types/wizard';
import { ArrowLeftRight } from 'lucide-react';

interface RouteBottomBarProps {
  rooms: RoomAnnotation[];
  fromRoom: string;
  toRoom: string;
  onFromChange: (val: string) => void;
  onToChange: (val: string) => void;
  onFindRoute: () => void;
  isLoading: boolean;
  onPrev: () => void;
  onNext: () => void;
  isNextDisabled: boolean;
  // Optional multifloor props
  multifloorMode?: boolean;
  availablePlans?: Array<{ id: number; name: string }>;
  fromReconId?: number;
  toReconId?: number;
  onFromReconChange?: (id: number) => void;
  onToReconChange?: (id: number) => void;
}

export const RouteBottomBar: React.FC<RouteBottomBarProps> = ({
  rooms,
  fromRoom,
  toRoom,
  onFromChange,
  onToChange,
  onFindRoute,
  isLoading,
  onPrev,
  onNext,
  isNextDisabled,
  multifloorMode,
  availablePlans,
  fromReconId,
  toReconId,
  onFromReconChange,
  onToReconChange,
}) => {
  const [fromSearch, setFromSearch] = React.useState('');
  const [toSearch, setToSearch] = React.useState('');

  const canFind = fromRoom && toRoom && fromRoom !== toRoom && !isLoading;

  const handleSwap = () => {
    if (fromRoom || toRoom) {
      const temp = fromRoom;
      onFromChange(toRoom);
      onToChange(temp);
    }
  };

  React.useEffect(() => {
    if (canFind) {
      onFindRoute();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromRoom, toRoom]);

  React.useEffect(() => {
    const room = rooms.find(r => r.id === fromRoom);
    if (room) setFromSearch(room.name || room.room_type);
    else setFromSearch('');
  }, [fromRoom, rooms]);

  React.useEffect(() => {
    const room = rooms.find(r => r.id === toRoom);
    if (room) setToSearch(room.name || room.room_type);
    else setToSearch('');
  }, [toRoom, rooms]);

  const handleSearchChange = (
    val: string,
    setSearch: React.Dispatch<React.SetStateAction<string>>,
    setRoom: (id: string) => void
  ) => {
    setSearch(val);
    const matched = rooms.find(r => {
      const label = r.name || r.room_type;
      return label.toLowerCase() === val.toLowerCase();
    });
    if (matched) setRoom(matched.id);
    else setRoom('');
  };

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLInputElement>,
    searchVal: string,
    setSearch: React.Dispatch<React.SetStateAction<string>>,
    setRoom: (id: string) => void,
    isToRoom: boolean
  ) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!searchVal.trim()) return;

      const availableRooms = isToRoom ? rooms.filter(r => r.id !== fromRoom) : rooms;
      const matches = availableRooms.filter(r => {
        const label = r.name || r.room_type;
        return label.toLowerCase().includes(searchVal.toLowerCase());
      });

      if (matches.length > 0) {
        // user requested "самый нижний" (bottommost), which is the last in the array
        const bestMatch = matches[matches.length - 1];
        setRoom(bestMatch.id);
        setSearch(bestMatch.name || bestMatch.room_type);
        e.currentTarget.blur();
      }
    }
  };

  return (
    <div className={styles.bottomBar}>
      <button type="button" className={styles.btnBack} onClick={onPrev}>
        Назад
      </button>

      <div className={styles.centerControls}>
        {multifloorMode && availablePlans && availablePlans.length > 0 && (
          <>
            <div className={styles.fieldGroup}>
              <span className={styles.label}>Этаж от:</span>
              <select
                className={styles.select}
                value={fromReconId ?? ''}
                onChange={(e) => onFromReconChange?.(Number(e.target.value))}
              >
                {availablePlans.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className={styles.line} />
            <div className={styles.fieldGroup}>
              <span className={styles.label}>Этаж до:</span>
              <select
                className={styles.select}
                value={toReconId ?? ''}
                onChange={(e) => onToReconChange?.(Number(e.target.value))}
              >
                {availablePlans.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className={styles.line} />
          </>
        )}
        <div className={styles.fieldGroup}>
          <span className={styles.label}>От:</span>
          <input
            className={styles.select}
            list="rooms-list-from"
            value={fromSearch}
            onChange={(e) => handleSearchChange(e.target.value, setFromSearch, onFromChange)}
            onKeyDown={(e) => handleKeyDown(e, fromSearch, setFromSearch, onFromChange, false)}
            placeholder="Выберите аудиторию"
          />
        </div>

        <div className={styles.line} />

        <button type="button" className={styles.swapBtn} onClick={handleSwap} title="Поменять местами">
          <ArrowLeftRight size={16} />
        </button>

        <div className={styles.line} />

        <div className={styles.fieldGroup}>
          <span className={styles.label}>До:</span>
          <input
            className={styles.select}
            list="rooms-list-to"
            value={toSearch}
            onChange={(e) => handleSearchChange(e.target.value, setToSearch, onToChange)}
            onKeyDown={(e) => handleKeyDown(e, toSearch, setToSearch, onToChange, true)}
            placeholder="Выберите аудиторию"
          />
        </div>
      </div>

      <button type="button" className={styles.btnNext} onClick={onNext} disabled={isNextDisabled}>
        {'> Далее'}
      </button>

      {/* Datalists for autocompletion */}
      <datalist id="rooms-list-from">
        {rooms.map(room => (
          <option key={room.id} value={room.name || room.room_type} />
        ))}
      </datalist>
      <datalist id="rooms-list-to">
        {rooms.filter(r => r.id !== fromRoom).map(room => (
          <option key={room.id} value={room.name || room.room_type} />
        ))}
      </datalist>
    </div>
  );
};
