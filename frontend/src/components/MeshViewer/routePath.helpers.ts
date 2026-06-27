import * as THREE from 'three';

/** Радиус фаски по умолчанию (world units ≈ метры). 0 ⇒ строго прямые. */
export const CORNER_RADIUS_M = 0.3;

/**
 * Wall-safe полилиния из разреженных (los_prune) точек: прямые сегменты + на
 * внутренних углах ограниченная квадратичная фаска Безье. Квадратичный Безье
 * лежит в выпуклой оболочке 3 контрольных точек = треугольнике угла, внутри
 * исходных (wall-clear) сегментов → срезает угол ВНУТРЬ, не выгибается в стену
 * (в отличие от CatmullRom, который проходит ЧЕРЕЗ вершину и выгибается наружу).
 *
 * @param points уже-смещённые мировые точки
 * @param radius радиус фаски (world units); <=0 ⇒ прямые сегменты
 * @returns точки для drei <Line>, либо null если точек < 2
 */
export const buildRoutePolyline = (
  points: THREE.Vector3[],
  radius: number = CORNER_RADIUS_M,
): THREE.Vector3[] | null => {
  if (!points || points.length < 2) return null;
  if (points.length === 2 || radius <= 0) return points.map((p) => p.clone());

  const SAMPLES = 6;
  const out: THREE.Vector3[] = [points[0].clone()];
  for (let i = 1; i < points.length - 1; i += 1) {
    const prev = points[i - 1];
    const v = points[i];
    const next = points[i + 1];
    const toPrev = prev.clone().sub(v);
    const toNext = next.clone().sub(v);
    const lenPrev = toPrev.length();
    const lenNext = toNext.length();
    if (lenPrev < 1e-6 || lenNext < 1e-6) {
      out.push(v.clone());
      continue;
    }
    const r = Math.min(radius, 0.4 * lenPrev, 0.4 * lenNext);
    const pIn = v.clone().add(toPrev.normalize().multiplyScalar(r));
    const pOut = v.clone().add(toNext.normalize().multiplyScalar(r));
    out.push(pIn);
    for (let s = 1; s < SAMPLES; s += 1) {
      const t = s / SAMPLES;
      const omt = 1 - t;
      // quadratic Bézier (pIn, v, pOut)
      const b = pIn
        .clone()
        .multiplyScalar(omt * omt)
        .add(v.clone().multiplyScalar(2 * omt * t))
        .add(pOut.clone().multiplyScalar(t * t));
      out.push(b);
    }
    out.push(pOut);
  }
  out.push(points[points.length - 1].clone());
  return out;
};
