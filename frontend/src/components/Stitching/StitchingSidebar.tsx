import React from 'react';
import { ToolPanel } from './ToolPanel';
import { LayerPanel } from './LayerPanel';
import { PropertiesPanel } from './PropertiesPanel';
import type { LayerData } from '../../types/stitching';
import styles from './StitchingSidebar.module.css';

interface StitchingSidebarProps {
  activeTool: "move" | "rotate" | "rect_crop" | "polygon_clip";
  onToolChange: (tool: "move" | "rotate" | "rect_crop" | "polygon_clip") => void;
  layers: LayerData[];
  selectedLayerId: string | null;
  onLayerSelect: (layerId: string) => void;
  onLayerMove: (layerId: string, direction: 'up' | 'down') => void;
  onMaskOpacityChange: (layerId: string, opacity: number) => void;
  onShowMaskToggle: (layerId: string) => void;
  onPropertyChange: (layerId: string, property: string, value: number) => void;
}

export const StitchingSidebar: React.FC<StitchingSidebarProps> = (props) => {
  const selectedLayer = props.layers.find((l) => l.reconstructionId === props.selectedLayerId) || null;

  return (
    <div className={styles.stitchingSidebar}>
      <ToolPanel
        activeTool={props.activeTool}
        onToolChange={props.onToolChange}
      />
      <LayerPanel
        layers={props.layers}
        selectedLayerId={props.selectedLayerId}
        onLayerSelect={props.onLayerSelect}
        onLayerMove={props.onLayerMove}
        onMaskOpacityChange={props.onMaskOpacityChange}
        onShowMaskToggle={props.onShowMaskToggle}
      />
      <PropertiesPanel
        selectedLayer={selectedLayer}
        onPropertyChange={(property, value) => {
          if (props.selectedLayerId) {
            props.onPropertyChange(props.selectedLayerId, property, value);
          }
        }}
      />
    </div>
  );
};
