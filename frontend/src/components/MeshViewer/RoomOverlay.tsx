import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { Box, Html } from '@react-three/drei';
import type { RoomDisplay } from '../../types/roomDisplay';
import { normalizedToWorld } from '../../types/roomDisplay';
import type { Room3DApi } from '../../api/apiService';

interface ComputedRoom {
  id: string;
  name: string;
  room_type: string;
  color: string;
  position: [number, number, number];
  size: [number, number, number];
  rotation: number;
}

interface RoomOverlayProps {
  modelRef: React.RefObject<THREE.Object3D | null>;
  rooms: RoomDisplay[];
  visible: boolean;
  wallHeight?: number;
  // Optional: exact 3D positions from backend (same formula as route markers).
  // When provided, takes priority over the bounding-box approach.
  rooms3D?: Room3DApi[];
}

export const RoomOverlay: React.FC<RoomOverlayProps> = ({
  modelRef,
  rooms,
  visible,
  wallHeight = 3.0,
  rooms3D,
}) => {
  const [computed, setComputed] = useState<ComputedRoom[]>([]);
  const boxGeomRef = useRef<THREE.BufferGeometry | null>(null);

  useEffect(() => () => { boxGeomRef.current?.dispose(); }, []);

  // Build color lookup from RoomDisplay so backend positions get correct color.
  const colorById = useMemo(() => {
    const m = new Map<string, { color: string; name: string; room_type: string }>();
    for (const r of rooms) m.set(r.id, { color: r.color, name: r.name, room_type: r.room_type });
    return m;
  }, [rooms]);

  useEffect(() => {
    if (!visible) {
      setComputed([]);
      return;
    }

    // Preferred path: backend-provided 3D positions (identical formula to route markers).
    if (rooms3D && rooms3D.length > 0) {
      setComputed(
        rooms3D.map((r) => {
          const meta = colorById.get(r.id);
          return {
            id: r.id,
            name: meta?.name ?? r.name,
            room_type: meta?.room_type ?? r.room_type,
            color: meta?.color ?? '#c8c8c8',
            position: r.position,
            size: r.size,
            rotation: r.rotation ?? 0,
          };
        }),
      );
      return;
    }

    // Fallback: bounding-box lerp when backend positions aren't available.
    if (!modelRef.current || rooms.length === 0) {
      setComputed([]);
      return;
    }
    modelRef.current.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(modelRef.current, true);
    if (box.isEmpty()) {
      setComputed([]);
      return;
    }
    const rangeX = box.max.x - box.min.x;
    const rangeZ = box.max.z - box.min.z;

    setComputed(
      rooms.map((room) => ({
        id: room.id,
        name: room.name,
        room_type: room.room_type,
        color: room.color,
        position: normalizedToWorld(room.center_x, room.center_y, box, wallHeight),
        size: [
          Math.max(room.width_norm * rangeX, 0.1),
          wallHeight * 0.8,
          Math.max(room.height_norm * rangeZ, 0.1),
        ],
        rotation: 0,
      })),
    );
  }, [visible, rooms, rooms3D, modelRef, wallHeight, colorById]);

  if (!visible || computed.length === 0) return null;

  return (
    <>
      {computed.map((r) => (
        <group key={r.id} position={r.position} rotation={[0, r.rotation, 0]}>
          <Box args={r.size as [number, number, number]}>
            <meshStandardMaterial
              color={r.color}
              transparent
              opacity={0.4}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </Box>
          <Html center position={[0, r.size[1] / 2 + 0.2, 0]}>
            <div
              style={{
                color: 'white',
                fontWeight: 500,
                fontSize: '13px',
                fontFamily: 'system-ui, -apple-system, sans-serif',
                textShadow: '0px 1px 3px rgba(0,0,0,0.8)',
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                background: 'rgba(0,0,0,0.35)',
                padding: '2px 6px',
                borderRadius: '4px',
              }}
            >
              {r.name || r.room_type}
            </div>
          </Html>
        </group>
      ))}
    </>
  );
};
