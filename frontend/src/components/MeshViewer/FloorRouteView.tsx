import React, { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { Box, Html, Line } from '@react-three/drei';
import type {
  PathSegment3D,
  Room3DInfo,
  TransitionUsed3D,
} from '../../types/transitions';
import {
  normalizePoint3D,
  normalizeSegmentCoords,
  segmentYOffset,
} from '../../hooks/useRouteTest.helpers';
import { buildRoutePolyline, CORNER_RADIUS_M } from './routePath.helpers';

interface TeleportButtonProps {
  position: [number, number, number];
  label: string;
  direction: 'forward' | 'back';
  onClick: () => void;
}

const TeleportButton: React.FC<TeleportButtonProps> = ({
  position,
  label,
  direction,
  onClick,
}) => (
  <Html position={position} center distanceFactor={undefined} zIndexRange={[100, 0]}>
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      style={{
        background: direction === 'forward' ? '#FFD700' : '#cccccc',
        color: '#000',
        border: '2px solid #000',
        padding: '6px 12px',
        fontSize: '13px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        fontWeight: 600,
        borderRadius: '6px',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        boxShadow: '0 2px 6px rgba(0,0,0,0.4)',
        userSelect: 'none',
      }}
    >
      {direction === 'forward' ? `→ ${label}` : `← ${label}`}
    </button>
  </Html>
);

const RoomMarker: React.FC<{
  position: [number, number, number];
  size: [number, number, number];
  label: string;
}> = ({ position, size, label }) => (
  <group position={position}>
    <Box args={size}>
      <meshStandardMaterial
        color="#FF4500"
        transparent
        opacity={0.4}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </Box>
    <Html center position={[0, size[1] / 2 + 0.2, 0]}>
      <div
        style={{
          color: 'white',
          fontWeight: 500,
          fontSize: '14px',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          textShadow: '0px 1px 3px rgba(0,0,0,0.8)',
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>
    </Html>
  </group>
);

interface FloorRouteViewProps {
  segment: PathSegment3D;
  outgoing: TransitionUsed3D | null;
  incoming: TransitionUsed3D | null;
  fromRoom3D?: Room3DInfo | null;
  toRoom3D?: Room3DInfo | null;
  fromRoomLabel?: string;
  toRoomLabel?: string;
  isFirst: boolean;
  isLast: boolean;
  onTeleportForward: () => void;
  onTeleportBack: () => void;
}

/**
 * Renders the route on a single floor:
 *   - line of the segment, normalized to floor-local Y;
 *   - clickable teleport buttons at incoming/outgoing transition endpoints;
 *   - room highlights only on the first/last segment.
 *
 * Assumes parent <MeshViewer> renders the corresponding floor's mesh
 * (whose Y starts at 0).
 */
export const FloorRouteView: React.FC<FloorRouteViewProps> = ({
  segment,
  outgoing,
  incoming,
  fromRoom3D,
  toRoom3D,
  fromRoomLabel,
  toRoomLabel,
  isFirst,
  isLast,
  onTeleportForward,
  onTeleportBack,
}) => {
  const yOffset = useMemo(() => segmentYOffset(segment), [segment]);

  const curvePoints = useMemo(() => {
    const local = normalizeSegmentCoords(segment, yOffset);
    if (local.length < 2) return null;
    const vectors = local.map(
      ([x, y, z]) => new THREE.Vector3(x, (y ?? 0) + 0.15, z),
    );
    return buildRoutePolyline(vectors, CORNER_RADIUS_M);
  }, [segment, yOffset]);

  // Track any geometry we let drei build internally — drei's <Line>
  // already disposes its own geometry on unmount, but we still keep a ref
  // for explicit safety per project Three.js cleanup rules.
  const lineGeomRef = useRef<THREE.BufferGeometry | null>(null);
  useEffect(() => () => lineGeomRef.current?.dispose(), []);

  const fromRoomNormalized = fromRoom3D
    ? {
        position: normalizePoint3D(fromRoom3D.position, yOffset),
        size: [
          fromRoom3D.size[0] ?? 0,
          fromRoom3D.size[1] ?? 0,
          fromRoom3D.size[2] ?? 0,
        ] as [number, number, number],
      }
    : null;

  const toRoomNormalized = toRoom3D
    ? {
        position: normalizePoint3D(toRoom3D.position, yOffset),
        size: [
          toRoom3D.size[0] ?? 0,
          toRoom3D.size[1] ?? 0,
          toRoom3D.size[2] ?? 0,
        ] as [number, number, number],
      }
    : null;

  const outgoingButtonPos: [number, number, number] | null = outgoing
    ? normalizePoint3D(outgoing.from_3d, yOffset)
    : null;
  const incomingButtonPos: [number, number, number] | null = incoming
    ? normalizePoint3D(incoming.to_3d, yOffset)
    : null;

  return (
    <>
      {curvePoints && (
        <Line
          points={curvePoints}
          color="#FF4500"
          lineWidth={4}
          depthTest={true}
          renderOrder={1}
        />
      )}

      {isFirst && fromRoomNormalized && fromRoomLabel && (
        <RoomMarker
          position={fromRoomNormalized.position}
          size={fromRoomNormalized.size}
          label={fromRoomLabel}
        />
      )}
      {isLast && toRoomNormalized && toRoomLabel && (
        <RoomMarker
          position={toRoomNormalized.position}
          size={toRoomNormalized.size}
          label={toRoomLabel}
        />
      )}

      {outgoingButtonPos && outgoing && (
        <TeleportButton
          position={outgoingButtonPos}
          label={outgoing.name}
          direction="forward"
          onClick={onTeleportForward}
        />
      )}
      {incomingButtonPos && incoming && (
        <TeleportButton
          position={incomingButtonPos}
          label={incoming.name}
          direction="back"
          onClick={onTeleportBack}
        />
      )}
    </>
  );
};
