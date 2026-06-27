// Pure GPU-resource disposal for a loaded Object3D subtree, extracted from
// MeshViewer so the cleanup is unit-testable in the node env with
// plain mock geometry/material objects.
//
// `disposeGeometry` differs by loader: GlbModel CLONES its geometry per load, so
// it owns and must free it (`true`); ObjModel renders the SHARED useLoader cache,
// so it must NOT dispose the geometry (`false`) — only the per-mount materials it
// minted. Duck-typed (no `instanceof THREE.Mesh`) so it works on both real three
// objects and the test mocks.

export interface Disposable {
  dispose: () => void;
}

interface MeshLike {
  geometry?: unknown;
  material?: unknown;
}

export interface Traversable {
  traverse: (callback: (child: unknown) => void) => void;
}

const isDisposable = (value: unknown): value is Disposable =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as Disposable).dispose === 'function';

const disposeMaterial = (material: unknown): void => {
  if (Array.isArray(material)) {
    material.forEach((m) => {
      if (isDisposable(m)) m.dispose();
    });
  } else if (isDisposable(material)) {
    material.dispose();
  }
};

/**
 * Traverse `root` and dispose each mesh's material (always) and geometry (only
 * when `disposeGeometry` is true). Non-mesh nodes (groups, lights — no
 * geometry/material) are skipped.
 */
export const disposeObject3D = (
  root: Traversable,
  options: { disposeGeometry: boolean },
): void => {
  root.traverse((child) => {
    const mesh = child as MeshLike;
    if (options.disposeGeometry && isDisposable(mesh.geometry)) {
      mesh.geometry.dispose();
    }
    disposeMaterial(mesh.material);
  });
};
