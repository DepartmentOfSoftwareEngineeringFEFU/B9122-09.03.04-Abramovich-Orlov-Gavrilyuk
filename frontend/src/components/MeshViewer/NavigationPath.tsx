import React, { useMemo } from 'react';
import * as THREE from 'three';
import { Line, Box, Html } from '@react-three/drei';
import { buildRoutePolyline, CORNER_RADIUS_M } from './routePath.helpers';

interface NavigationPathProps {
  coordinates: number[][] | null;
  fromRoom3D?: {
    position: [number, number, number];
    size: [number, number, number];
    rotation?: number;
  };
  toRoom3D?: {
    position: [number, number, number];
    size: [number, number, number];
    rotation?: number;
  };
  fromRoomName?: string;
  toRoomName?: string;
  segments?: Array<{ coordinates: number[][] }>;
}

export const NavigationPath: React.FC<NavigationPathProps> = ({
  coordinates,
  fromRoom3D,
  toRoom3D,
  fromRoomName,
  toRoomName,
  segments,
}) => {
  const curvePoints = useMemo(() => {
    const activeCoordinates = segments?.[0]?.coordinates ?? coordinates;
    if (!activeCoordinates || activeCoordinates.length < 2) return null;

    const vectors = activeCoordinates.map(
      ([x, y, z]) => new THREE.Vector3(x, (y ?? 0) + 0.15, z),
    );
    return buildRoutePolyline(vectors, CORNER_RADIUS_M);
  }, [coordinates, segments]);

  if (!curvePoints) return null;

  return (
    <>
      <Line
        points={curvePoints}
        color="#FF4500"
        lineWidth={4}
        depthTest={true}
        renderOrder={1}
      />

      {fromRoom3D && (
        <group position={fromRoom3D.position} rotation={[0, fromRoom3D.rotation ?? 0, 0]}>
          <Box args={fromRoom3D.size}>
            <meshStandardMaterial
              color="#FF4500"
              transparent
              opacity={0.4}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </Box>
          {fromRoomName && (
            <Html center position={[0, fromRoom3D.size[1] / 2 + 0.2, 0]}>
              <div style={{
                color: 'white',
                fontWeight: 500,
                fontSize: '14px',
                fontFamily: 'system-ui, -apple-system, sans-serif',
                textShadow: '0px 1px 3px rgba(0,0,0,0.8)',
                pointerEvents: 'none',
                whiteSpace: 'nowrap'
              }}>
                {fromRoomName}
              </div>
            </Html>
          )}
        </group>
      )}

      {toRoom3D && (
        <group position={toRoom3D.position} rotation={[0, toRoom3D.rotation ?? 0, 0]}>
          <Box args={toRoom3D.size}>
            <meshStandardMaterial
              color="#FF4500"
              transparent
              opacity={0.4}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </Box>
          {toRoomName && (
            <Html center position={[0, toRoom3D.size[1] / 2 + 0.2, 0]}>
              <div style={{
                color: 'white',
                fontWeight: 500,
                fontSize: '14px',
                fontFamily: 'system-ui, -apple-system, sans-serif',
                textShadow: '0px 1px 3px rgba(0,0,0,0.8)',
                pointerEvents: 'none',
                whiteSpace: 'nowrap'
              }}>
                {toRoomName}
              </div>
            </Html>
          )}
        </group>
      )}
    </>
  );
};
