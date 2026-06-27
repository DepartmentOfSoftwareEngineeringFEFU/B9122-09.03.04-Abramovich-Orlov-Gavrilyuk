import { useState, useCallback } from 'react';
import type { StitchingSnapshot } from '../types/stitching';

interface UseStitchingHistoryReturn {
  pushState: (snapshot: StitchingSnapshot) => void;
  undo: () => StitchingSnapshot | null;
  redo: () => StitchingSnapshot | null;
  canUndo: boolean;
  canRedo: boolean;
  clear: () => void;
}

export const useStitchingHistory = (
  maxSteps: number = 50
): UseStitchingHistoryReturn => {
  const [history, setHistory] = useState<StitchingSnapshot[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(-1);

  const pushState = useCallback((snapshot: StitchingSnapshot) => {
    setHistory((prev) => {
      // Cut off "future" if we're not at the end
      const newHistory = prev.slice(0, currentIndex + 1);

      // Add new snapshot
      newHistory.push(snapshot);

      // FIFO: remove oldest if > maxSteps
      if (newHistory.length > maxSteps) {
        newHistory.shift();
        setCurrentIndex(newHistory.length - 1);
      } else {
        setCurrentIndex(newHistory.length - 1);
      }

      return newHistory;
    });
  }, [currentIndex, maxSteps]);

  const undo = useCallback((): StitchingSnapshot | null => {
    if (currentIndex <= 0) return null;

    const newIndex = currentIndex - 1;
    setCurrentIndex(newIndex);
    return history[newIndex];
  }, [currentIndex, history]);

  const redo = useCallback((): StitchingSnapshot | null => {
    if (currentIndex >= history.length - 1) return null;

    const newIndex = currentIndex + 1;
    setCurrentIndex(newIndex);
    return history[newIndex];
  }, [currentIndex, history]);

  const clear = useCallback(() => {
    setHistory([]);
    setCurrentIndex(-1);
  }, []);

  const canUndo = currentIndex > 0;
  const canRedo = currentIndex < history.length - 1;

  return {
    pushState,
    undo,
    redo,
    canUndo,
    canRedo,
    clear,
  };
};
