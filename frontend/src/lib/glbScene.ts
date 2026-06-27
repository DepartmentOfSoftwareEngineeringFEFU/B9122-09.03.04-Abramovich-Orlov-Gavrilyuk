// Shared trimesh-GLB scene preparation, extracted from MeshViewer so both the
// single-mesh viewer and the stacked BuildingMeshViewer (subfeature B) use the
// IDENTICAL, tested fix — no drift that would silently render floors black.
//
// trimesh (Python) exports GLBs that need two fixes before Three can light them:
//   1) it bakes dark RGBA vertex colors → GLTFLoader multiplies them × material
//      color → near-black. We delete the 'color' attribute.
//   2) its vertex normals are missing/incorrect → a PBR (MeshStandardMaterial)
//      gets zero lighting → black. We recompute normals.
// We also apply a clean matte standard material. Everything operates on a CLONE
// (geometry included) so the useGLTF cache / input scene is never mutated.

import * as THREE from 'three';

export const WALL_FALLBACK_COLOR = '#BDBDBD';

export interface PrepareTrimeshOptions {
  /**
   * Keep the GLB's baked per-vertex colours instead of flattening everything to one
   * grey. The building viewer uses this so the dark floor slab stays visually distinct
   * from the grey walls. Default `false` (single-mesh viewer → uniform grey). Safe only
   * when the baked colours are light/correct (these floor GLBs bake explicit greys, not
   * the dark defaults that caused the original black-wall bug). Normals are recomputed
   * either way, so lighting is correct.
   */
  keepVertexColors?: boolean;
  /** Fallback uniform colour when NOT keeping vertex colours. */
  color?: string;
}

/**
 * Clone a trimesh-exported scene and fix it for correct (non-black) rendering:
 * recompute normals, apply a matte standard material, and either strip baked vertex
 * colors (default → uniform grey) or keep them (`keepVertexColors`). The input `scene`
 * is never mutated (the returned subtree owns cloned geometry + freshly minted
 * materials — dispose it with `disposeObject3D(.., {disposeGeometry:true})`).
 */
export function prepareTrimeshScene(
  scene: THREE.Object3D,
  opts: PrepareTrimeshOptions = {},
): THREE.Object3D {
  const keepVertexColors = opts.keepVertexColors ?? false;
  const color = opts.color ?? WALL_FALLBACK_COLOR;
  const cloned = scene.clone(true);
  cloned.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      // Object3D.clone() shares geometry by reference — clone it so the edits
      // below never touch the cached/original geometry.
      child.geometry = child.geometry.clone();
      if (!keepVertexColors && child.geometry.hasAttribute('color')) {
        child.geometry.deleteAttribute('color');
      }
      child.geometry.computeVertexNormals();
      child.material = new THREE.MeshStandardMaterial({
        // With vertexColors, material.color is multiplied by the per-vertex colour,
        // so keep it white to render the baked colours faithfully.
        color: keepVertexColors ? '#ffffff' : color,
        vertexColors: keepVertexColors,
        roughness: 1.0,
        metalness: 0.0,
        side: THREE.DoubleSide,
      });
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });
  return cloned;
}
