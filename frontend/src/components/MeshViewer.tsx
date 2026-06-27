import { forwardRef, Suspense, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls, useGLTF } from '@react-three/drei';
import { OBJLoader } from 'three-stdlib';
import * as THREE from 'three';
import { RoomOverlay } from './MeshViewer/RoomOverlay';
import type { RoomDisplay } from '../types/roomDisplay';
import type { Room3DApi } from '../api/apiService';
import { disposeObject3D } from '../lib/disposeObject3D';
import { prepareTrimeshScene } from '../lib/glbScene';

/*
   2GIS / Яндекс Карты palette
    */
const COLORS = {
  wallFallback: '#BDBDBD',  // light grey для стен
  background:   '#FFFFFF',  // белый фон
};

/*
   Public handle for programmatic camera control
    */
export interface MeshViewerHandle {
  zoomIn: () => void;
  zoomOut: () => void;
}

/*
   Camera: auto-fit to model, top-down isometric
    */
function CameraSetup({ modelRef }: { modelRef: React.RefObject<THREE.Object3D> }) {
  const { camera, controls } = useThree();

  useEffect(() => {
    if (!modelRef.current) return;

    const box = new THREE.Box3().setFromObject(modelRef.current);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    const maxDim = Math.max(size.x, size.z);
    const dist = maxDim * 1.0;

    // Изометрия ~70° сверху — как 2GIS при открытии здания
    camera.position.set(
      center.x + dist * 0.15,
      center.y + dist * 0.85,
      center.z + dist * 0.35,
    );
    camera.lookAt(center);
    (camera as THREE.PerspectiveCamera).far = Math.max(5000, dist * 4);
    camera.updateProjectionMatrix();

    if (controls) {
      const ctrl = controls as unknown as { target: THREE.Vector3; update: () => void };
      ctrl.target.copy(center);
      ctrl.update();
    }
  }, [camera, controls, modelRef]);

  return null;
}

/*
   Floor plane — бежевый пол под моделью
    */
function FloorPlane({ modelRef }: { modelRef: React.RefObject<THREE.Object3D> }) {
  const meshRef = useRef<THREE.Mesh>(null);

  useEffect(() => {
    if (!modelRef.current || !meshRef.current) return;

    const box = new THREE.Box3().setFromObject(modelRef.current);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    // Пол чуть больше модели
    const pad = 1;
    meshRef.current.scale.set(size.x * pad, size.z * pad, 1);
    meshRef.current.position.set(center.x, box.min.y - 0.05, center.z);
  }, [modelRef]);

  return (
    <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[1, 1]} />
      <meshLambertMaterial color="#FFFFFF" />
    </mesh>
  );
}

/*
   Apply 2GIS-style materials to loaded model
    */
function applyMapMaterials(root: THREE.Object3D, _useVertexColors: boolean) {
  root.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      const material = new THREE.MeshStandardMaterial({
        color: COLORS.wallFallback,
        roughness: 0.8,
        metalness: 0.0,
        side: THREE.DoubleSide,
      });
      child.material = material;
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });
}

/*
   OBJ model loader
    */
interface ObjModelProps {
  url: string;
  rooms: RoomDisplay[];
  showRooms: boolean;
  rooms3D?: Room3DApi[];
}

function ObjModel({ url, rooms, showRooms, rooms3D }: ObjModelProps) {
  const obj = useLoader(OBJLoader, url);
  const ref = useRef<THREE.Object3D>(null);

  useEffect(() => {
    if (ref.current) applyMapMaterials(ref.current, false);
  }, [obj]);

  // Free the per-mount MeshStandardMaterials applyMapMaterials minted for this
  // OBJ on unmount / url change. disposeGeometry=false: the geometry is the
  // SHARED useLoader(OBJLoader) cache (not a per-load clone like GlbModel), so
  // disposing it would corrupt a later reload of the same url.
  useEffect(() => {
    const root = obj;
    return () => disposeObject3D(root, { disposeGeometry: false });
  }, [obj]);

  return (
    <>
      <primitive ref={ref} object={obj} />
      <CameraSetup modelRef={ref} />
      <FloorPlane modelRef={ref} />
      <RoomOverlay modelRef={ref} rooms={rooms} visible={showRooms} rooms3D={rooms3D} />
    </>
  );
}

/*
   GLB model loader

   BUG FIX (2026-03-21): стены из trimesh GLB рендерились чёрными.
   Причина — две проблемы в GLB, экспортируемом библиотекой trimesh (Python):

   1) VERTEX COLORS: trimesh записывает vertex colors как RGBA [74,74,74,255]
      в GLB. Three.js GLTFLoader видит их, создаёт MeshStandardMaterial с
      vertexColors: true, и УМНОЖАЕТ vertex colors × material.color.
      Тёмные vertex colors × любой цвет = почти чёрный результат.
      → Решение: удалить атрибут 'color' из geometry (deleteAttribute).

   2) NORMALS: trimesh экспортирует GLB с некорректными/отсутствующими
      нормалями вершин. MeshStandardMaterial — PBR-материал, который
      рассчитывает освещение на основе нормалей. Без корректных нормалей
      все грани получают нулевое освещение → чёрный цвет.
      → Решение: пересчитать нормали (geometry.computeVertexNormals()).

   3) useMemo вместо useEffect: useGLTF из drei кэширует scene.
      Материалы нужно заменить ДО первого рендера (useMemo + clone),
      а не после (useEffect), иначе первый кадр мигнёт чёрным, и
      при StrictMode useEffect может не сработать корректно.

   Проверено: MeshBasicMaterial (игнорирует нормали и свет) показывал
   цвет корректно → подтвердило что проблема именно в нормалях.
    */
interface GlbModelProps {
  url: string;
  rooms: RoomDisplay[];
  showRooms: boolean;
  rooms3D?: Room3DApi[];
}

function GlbModel({ url, rooms, showRooms, rooms3D }: GlbModelProps) {
  const { scene } = useGLTF(url);
  const ref = useRef<THREE.Object3D>(null);

  // Process materials BEFORE render via useMemo (not useEffect which runs after).
  // The trimesh-GLB fix (strip baked vertex colors + recompute normals + apply a
  // matte material — see bug description above) lives in the shared lib/glbScene
  // helper so MeshViewer and BuildingMeshViewer use the identical, tested fix.
  const processedScene = useMemo(() => prepareTrimeshScene(scene), [scene]);

  // Dispose the cloned geometries + the MeshStandardMaterials minted above when
  // this processedScene is replaced or the component unmounts. disposeGeometry=
  // true: GlbModel CLONES its geometry per load (see useMemo), so it owns and must
  // free it — <Canvas> only disposes its renderer, not these per-load clones.
  useEffect(() => {
    const root = processedScene;
    return () => disposeObject3D(root, { disposeGeometry: true });
  }, [processedScene]);

  return (
    <>
      <primitive ref={ref} object={processedScene} />
      <CameraSetup modelRef={ref} />
      <FloorPlane modelRef={ref} />
      <RoomOverlay modelRef={ref} rooms={rooms} visible={showRooms} rooms3D={rooms3D} />
    </>
  );
}

/*
   ControlsBridge — exposes camera zoom outward
   via useImperativeHandle on the MeshViewer ref.

   Approach B: move camera position along the
   (camera - target) vector. Works regardless of
   whether OrbitControls.dollyIn/Out is public.
    */
const ZOOM_FACTOR = 1.15;

interface ControlsBridgeProps {
  handleRef: React.ForwardedRef<MeshViewerHandle>;
}

function ControlsBridge({ handleRef }: ControlsBridgeProps) {
  const { camera, controls } = useThree();

  useImperativeHandle(
    handleRef,
    () => ({
      zoomIn: () => {
        const ctrl = controls as unknown as { target: THREE.Vector3; update: () => void } | null;
        const target = ctrl?.target ?? new THREE.Vector3(0, 0, 0);
        const offset = new THREE.Vector3().subVectors(camera.position, target);
        offset.multiplyScalar(1 / ZOOM_FACTOR);
        camera.position.copy(target).add(offset);
        ctrl?.update();
      },
      zoomOut: () => {
        const ctrl = controls as unknown as { target: THREE.Vector3; update: () => void } | null;
        const target = ctrl?.target ?? new THREE.Vector3(0, 0, 0);
        const offset = new THREE.Vector3().subVectors(camera.position, target);
        offset.multiplyScalar(ZOOM_FACTOR);
        camera.position.copy(target).add(offset);
        ctrl?.update();
      },
    }),
    [camera, controls],
  );

  return null;
}

/*
   Main MeshViewer component
    */
interface MeshViewerProps {
  url: string;
  format?: 'obj' | 'glb';
  children?: React.ReactNode;
  rooms?: RoomDisplay[];
  showRooms?: boolean;
  rooms3D?: Room3DApi[];
}

const MeshViewer = forwardRef<MeshViewerHandle, MeshViewerProps>(function MeshViewer(
  { url, format, children, rooms = [], showRooms = false, rooms3D },
  ref,
) {
  const modelFormat: 'obj' | 'glb' =
    format ?? (url.toLowerCase().endsWith('.glb') ? 'glb' : 'obj');

  return (
    <Canvas
      camera={{ position: [0, 50, 20], fov: 45, near: 0.1, far: 5000 }}
      shadows
      style={{ background: COLORS.background }}
      gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.2 }}
    >
      {/* Мягкий ambient — доминирует, чтобы скрыть артефакты нормалей */}
      <ambientLight intensity={0.9} color="#ffffff" />

      {/* Основной направленный — ослаблен, только для теней */}
      <directionalLight
        position={[30, 60, 30]}
        intensity={0.7}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-far={200}
        shadow-camera-left={-100}
        shadow-camera-right={100}
        shadow-camera-top={100}
        shadow-camera-bottom={-100}
        shadow-bias={-0.001}
      />

      {/* Заполняющий с другой стороны */}
      <directionalLight position={[-20, 30, -20]} intensity={0.2} />

      {/* Hemisphere — тёплый сверху, нейтральный снизу */}
      <hemisphereLight args={['#e8e4dc', '#b0aaa0', 0.4]} />

      <Suspense fallback={null}>
        {modelFormat === 'glb'
          ? <GlbModel url={url} rooms={rooms} showRooms={showRooms} rooms3D={rooms3D} />
          : <ObjModel url={url} rooms={rooms} showRooms={showRooms} rooms3D={rooms3D} />
        }
      </Suspense>

      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        maxPolarAngle={Math.PI / 2.1}
        minDistance={1}
        maxDistance={500}
      />

      <ControlsBridge handleRef={ref} />

      {children}
    </Canvas>
  );
});

export default MeshViewer;
