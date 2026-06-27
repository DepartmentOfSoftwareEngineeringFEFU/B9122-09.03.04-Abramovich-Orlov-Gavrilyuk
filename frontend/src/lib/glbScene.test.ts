import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { prepareTrimeshScene } from './glbScene';

// Build a one-triangle mesh carrying a baked vertex-color attribute (what trimesh
// exports) and a MeshBasicMaterial, inside a Group — no WebGL, runs in node.
function meshWithColor(): THREE.Mesh {
  const geom = new THREE.BufferGeometry();
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const colors = new Float32Array([0.29, 0.29, 0.29, 0.29, 0.29, 0.29, 0.29, 0.29, 0.29]);
  geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  return new THREE.Mesh(geom, new THREE.MeshBasicMaterial());
}

describe('prepareTrimeshScene', () => {
  it('removes the baked vertex color attribute', () => {
    const scene = new THREE.Group();
    scene.add(meshWithColor());

    const out = prepareTrimeshScene(scene);

    const mesh = out.children[0] as THREE.Mesh;
    expect(mesh.geometry.hasAttribute('color')).toBe(false);
  });

  it('computes normals and applies a standard material; input is not mutated', () => {
    const scene = new THREE.Group();
    const original = meshWithColor();
    scene.add(original);

    const out = prepareTrimeshScene(scene);

    const mesh = out.children[0] as THREE.Mesh;
    expect(mesh.geometry.hasAttribute('normal')).toBe(true);
    expect(mesh.material instanceof THREE.MeshStandardMaterial).toBe(true);
    // the input scene's mesh is untouched (clone, not in-place)
    expect(original.geometry.hasAttribute('color')).toBe(true);
    expect(original.material instanceof THREE.MeshBasicMaterial).toBe(true);
  });

  it('keeps vertex colors + uses a vertexColors material when keepVertexColors=true', () => {
    const scene = new THREE.Group();
    scene.add(meshWithColor());

    const out = prepareTrimeshScene(scene, { keepVertexColors: true });

    const mesh = out.children[0] as THREE.Mesh;
    expect(mesh.geometry.hasAttribute('color')).toBe(true);
    const mat = mesh.material as THREE.MeshStandardMaterial;
    expect(mat.vertexColors).toBe(true);
  });
});
