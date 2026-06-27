import { describe, it, expect, vi } from 'vitest';
import { disposeObject3D, type Traversable } from './disposeObject3D';

// A fake Object3D subtree: traverse visits each given child (mirrors three's
// Object3D.traverse). Meshes are plain objects carrying dispose spies — no WebGL
// or real three needed, so this runs in the node env.
const mockRoot = (children: unknown[]): Traversable => ({
  traverse(callback: (child: unknown) => void): void {
    children.forEach((child) => callback(child));
  },
});

const mockMesh = () => ({
  geometry: { dispose: vi.fn() },
  material: { dispose: vi.fn() },
});

describe('disposeObject3D', () => {
  it('disposes geometry AND material when disposeGeometry is true (GLB clones)', () => {
    const mesh = mockMesh();
    disposeObject3D(mockRoot([mesh]), { disposeGeometry: true });
    expect(mesh.geometry.dispose).toHaveBeenCalledTimes(1);
    expect(mesh.material.dispose).toHaveBeenCalledTimes(1);
  });

  it('disposes ONLY material when disposeGeometry is false (OBJ shares the loader cache)', () => {
    const mesh = mockMesh();
    disposeObject3D(mockRoot([mesh]), { disposeGeometry: false });
    expect(mesh.geometry.dispose).not.toHaveBeenCalled();
    expect(mesh.material.dispose).toHaveBeenCalledTimes(1);
  });

  it('disposes every material when a mesh has a material array', () => {
    const materials = [{ dispose: vi.fn() }, { dispose: vi.fn() }];
    const mesh = { geometry: { dispose: vi.fn() }, material: materials };
    disposeObject3D(mockRoot([mesh]), { disposeGeometry: true });
    materials.forEach((m) => expect(m.dispose).toHaveBeenCalledTimes(1));
  });

  it('skips non-mesh nodes (groups/lights have no geometry or material)', () => {
    const group = {};
    expect(() =>
      disposeObject3D(mockRoot([group]), { disposeGeometry: true }),
    ).not.toThrow();
  });
});
