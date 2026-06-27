// Floor-keyed cross-floor route polyline (subfeature D). A standalone R3F scene
// object: it renders each floor segment + each stair/elevator riser as a drei
// <Line> in the SHARED building-frame world (same frame as B's stacked floor
// GLBs), so the route stays correct no matter which floor meshes are hidden.
//
// Coordinates come straight from the backend — no client
// transform. drei's <Line> owns + disposes its geometry/material on unmount
// (threejs cleanup rule), so this component holds no manual THREE resources.

import React, { useMemo } from 'react';
import * as THREE from 'three';
import { Line } from '@react-three/drei';
import type { FloorPathSegment3D, TransitionUsed3D } from '../../types/buildingNav';
import {
  liftPoint,
  segmentOccluded,
  topRouteFloorNumber,
} from './multifloorRoutePath.helpers';

const ROUTE_COLOR = '#FF4500';
const ROUTE_LIFT = 0.15; // metres above the floor, matching NavigationPath

export interface MultifloorRoutePathProps {
  segments: FloorPathSegment3D[];
  transitions: TransitionUsed3D[];
}

export const MultifloorRoutePath: React.FC<MultifloorRoutePathProps> = ({
  segments,
  transitions,
}) => {
  // The topmost shown floor's line stays always-on-top; lower floors are
  // depth-tested so the floor meshes above occlude them (no bleed-through onto
  // the floor you're looking at). A single visible floor is its own top.
  const topFloor = useMemo(() => topRouteFloorNumber(segments), [segments]);
  const segmentLines = useMemo(
    () =>
      segments
        .map((seg) => ({
          occluded: segmentOccluded(seg.floor_number, topFloor),
          points: seg.coordinates_3d.map(
            (pt) => new THREE.Vector3(...liftPoint(pt, ROUTE_LIFT)),
          ),
        }))
        .filter((s) => s.points.length >= 2),
    [segments, topFloor],
  );

  const risers = useMemo(
    () =>
      transitions.map((tr) => [
        new THREE.Vector3(...liftPoint(tr.from_3d, ROUTE_LIFT)),
        new THREE.Vector3(...liftPoint(tr.to_3d, ROUTE_LIFT)),
      ]),
    [transitions],
  );

  return (
    <>
      {segmentLines.map((seg, i) => (
        <Line
          key={`seg-${i}`}
          points={seg.points}
          color={ROUTE_COLOR}
          lineWidth={4}
          renderOrder={2}
          depthTest={seg.occluded}
        />
      ))}
      {risers.map((pts, i) => (
        <Line
          key={`riser-${i}`}
          points={pts}
          color={ROUTE_COLOR}
          lineWidth={4}
          renderOrder={2}
          depthTest={false}
        />
      ))}
    </>
  );
};

export default MultifloorRoutePath;
