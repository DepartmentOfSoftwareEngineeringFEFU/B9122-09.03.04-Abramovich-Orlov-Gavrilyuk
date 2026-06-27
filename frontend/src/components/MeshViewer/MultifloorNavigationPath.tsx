import React, { useMemo, useEffect, useRef } from 'react';
import * as THREE from 'three';
import { Line, Html } from '@react-three/drei';
import { NavigationPath } from './NavigationPath';
import type { PathSegment3D, TransitionUsed3D, Room3DInfo } from '../../types/transitions';

interface TransitionMarkerProps {
  name: string;
  from3D: number[];
  to3D: number[];
}

const TransitionMarker: React.FC<TransitionMarkerProps> = ({ name, from3D, to3D }) => {
  // Store geometry ref for explicit disposal on unmount (Three.js cleanup rule)
  const geometryRef = useRef<THREE.BufferGeometry | null>(null);

  const points = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(from3D[0], from3D[1] ?? 0, from3D[2] ?? 0),
      new THREE.Vector3(to3D[0], to3D[1] ?? 0, to3D[2] ?? 0),
    ]);
    geometryRef.current = geometry;
    return [
      new THREE.Vector3(from3D[0], from3D[1] ?? 0, from3D[2] ?? 0),
      new THREE.Vector3(to3D[0], to3D[1] ?? 0, to3D[2] ?? 0),
    ];
  }, [from3D, to3D]);

  // Dispose GPU geometry on unmount
  useEffect(() => {
    return () => {
      geometryRef.current?.dispose();
    };
  }, []);

  const midpoint: [number, number, number] = [
    (from3D[0] + to3D[0]) / 2,
    ((from3D[1] ?? 0) + (to3D[1] ?? 0)) / 2,
    ((from3D[2] ?? 0) + (to3D[2] ?? 0)) / 2,
  ];

  return (
    <>
      <Line
        points={points}
        color="#FFD700"
        lineWidth={3}
        depthTest={true}
        renderOrder={2}
      />
      <Html position={midpoint}>
        <div
          style={{
            background: '#FFD700',
            color: '#000',
            padding: '2px 6px',
            fontSize: '11px',
            fontFamily: 'monospace',
            borderRadius: '3px',
            whiteSpace: 'nowrap',
          }}
        >
          {name}
        </div>
      </Html>
    </>
  );
};

interface MultifloorNavigationPathProps {
  pathSegments: PathSegment3D[];
  transitionsUsed: TransitionUsed3D[];
  fromRoom3D?: Room3DInfo | null;
  toRoom3D?: Room3DInfo | null;
}

export const MultifloorNavigationPath: React.FC<MultifloorNavigationPathProps> = ({
  pathSegments,
  transitionsUsed,
  fromRoom3D,
  toRoom3D,
}) => {
  if (pathSegments.length === 0) return null;

  const lastIndex = pathSegments.length - 1;

  return (
    <>
      {pathSegments.map((segment, i) => (
        <NavigationPath
          key={segment.reconstruction_id}
          coordinates={segment.coordinates_3d}
          fromRoom3D={
            i === 0 && fromRoom3D
              ? { position: fromRoom3D.position as [number, number, number], size: fromRoom3D.size as [number, number, number] }
              : undefined
          }
          toRoom3D={
            i === lastIndex && toRoom3D
              ? { position: toRoom3D.position as [number, number, number], size: toRoom3D.size as [number, number, number] }
              : undefined
          }
          fromRoomName={i === 0 ? `Этаж ${segment.floor_number}` : undefined}
          toRoomName={i === lastIndex ? `Этаж ${segment.floor_number}` : undefined}
        />
      ))}
      {transitionsUsed.map((t, i) => (
        <TransitionMarker key={i} name={t.name} from3D={t.from_3d} to3D={t.to_3d} />
      ))}
    </>
  );
};
