/**
 * Crop Selector Component
 * 
 * Allows user to select a rectangular region of an image
 * by dragging to create a selection box.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import './CropSelector.css';

interface CropSelectorProps {
  imageUrl: string;
  onCropComplete: (cropRect: CropRect) => void;
  onCancel: () => void;
}

export interface CropRect {
  x: number;      // Left position (0-1 ratio)
  y: number;      // Top position (0-1 ratio)
  width: number;  // Width (0-1 ratio)
  height: number; // Height (0-1 ratio)
}

export default function CropSelector({ imageUrl, onCropComplete, onCancel }: CropSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPoint, setStartPoint] = useState({ x: 0, y: 0 });
  const [cropRect, setCropRect] = useState<CropRect | null>(null);
  
  // Calculate position relative to image
  const getRelativePosition = useCallback((e: React.MouseEvent) => {
    if (!imgRef.current) return { x: 0, y: 0 };
    
    const rect = imgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    
    return {
      x: Math.max(0, Math.min(1, x)),
      y: Math.max(0, Math.min(1, y))
    };
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    const pos = getRelativePosition(e);
    setStartPoint(pos);
    setIsDrawing(true);
    setCropRect(null);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDrawing) return;
    
    const currentPos = getRelativePosition(e);
    
    const x = Math.min(startPoint.x, currentPos.x);
    const y = Math.min(startPoint.y, currentPos.y);
    const width = Math.abs(currentPos.x - startPoint.x);
    const height = Math.abs(currentPos.y - startPoint.y);
    
    setCropRect({ x, y, width, height });
  };

  const handleMouseUp = () => {
    setIsDrawing(false);
  };

  const handleApply = () => {
    if (cropRect && cropRect.width > 0.01 && cropRect.height > 0.01) {
      onCropComplete(cropRect);
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      } else if (e.key === 'Enter' && cropRect) {
        handleApply();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [cropRect, onCancel]);

  return (
    <div className="crop-selector-overlay">
      <div className="crop-selector-modal">
        <h3>Выберите область плана</h3>
        <p className="crop-hint">Выделите область с планом помещения (без текста и легенды)</p>
        
        <div 
          ref={containerRef}
          className="crop-image-container"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <img 
            ref={imgRef}
            src={imageUrl} 
            alt="План для кадрирования" 
            draggable={false}
          />
          
          {/* Selection rectangle */}
          {cropRect && (
            <div 
              className="crop-selection"
              style={{
                left: `${cropRect.x * 100}%`,
                top: `${cropRect.y * 100}%`,
                width: `${cropRect.width * 100}%`,
                height: `${cropRect.height * 100}%`,
              }}
            />
          )}
          
          {/* Dark overlay for non-selected area */}
          {cropRect && (
            <>
              <div className="crop-overlay crop-overlay-top" style={{ height: `${cropRect.y * 100}%` }} />
              <div className="crop-overlay crop-overlay-bottom" style={{ 
                top: `${(cropRect.y + cropRect.height) * 100}%`,
                height: `${(1 - cropRect.y - cropRect.height) * 100}%` 
              }} />
              <div className="crop-overlay crop-overlay-left" style={{ 
                top: `${cropRect.y * 100}%`,
                height: `${cropRect.height * 100}%`,
                width: `${cropRect.x * 100}%`
              }} />
              <div className="crop-overlay crop-overlay-right" style={{ 
                top: `${cropRect.y * 100}%`,
                left: `${(cropRect.x + cropRect.width) * 100}%`,
                height: `${cropRect.height * 100}%`,
                width: `${(1 - cropRect.x - cropRect.width) * 100}%`
              }} />
            </>
          )}
        </div>
        
        <div className="crop-actions">
          <button onClick={onCancel} className="btn-secondary">
            Отмена
          </button>
          <button 
            onClick={handleApply} 
            disabled={!cropRect || cropRect.width < 0.01}
            className="btn-primary"
          >
            Применить кадрирование
          </button>
        </div>
      </div>
    </div>
  );
}
