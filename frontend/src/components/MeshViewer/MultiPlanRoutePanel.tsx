import React from 'react';
import type { MultiPlanRouteResponse } from '../../types/transitions';

interface MultiPlanRoutePanelProps {
  route: MultiPlanRouteResponse | null;
}

export const MultiPlanRoutePanel: React.FC<MultiPlanRoutePanelProps> = ({ route }) => {
  if (!route) return null;
  return (
    <div>
      <div>{route.status}</div>
      <div>{route.total_distance_meters ?? 0}</div>
      {route.segments.map((segment, index) => (
        <div key={index}>{segment.floor_label ?? segment.reconstruction_name ?? segment.reconstruction_id}</div>
      ))}
    </div>
  );
};
