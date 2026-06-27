import { describe, it, expect } from 'vitest';
import { rectToPolygon } from './Step8Connectors';

describe('rectToPolygon', () => {
  it('builds a 4-corner rectangle from two opposite corners', () => {
    const poly = rectToPolygon([0.2, 0.3], [0.6, 0.7]);
    expect(poly).toEqual([
      [0.2, 0.3],
      [0.6, 0.3],
      [0.6, 0.7],
      [0.2, 0.7],
    ]);
  });

  it('normalises corner order (drag up-left still yields min→max)', () => {
    const poly = rectToPolygon([0.6, 0.7], [0.2, 0.3]);
    expect(poly).toEqual([
      [0.2, 0.3],
      [0.6, 0.3],
      [0.6, 0.7],
      [0.2, 0.7],
    ]);
  });

  it('clamps coordinates to the unit square [0,1]', () => {
    const poly = rectToPolygon([-0.5, -0.2], [1.4, 1.9]);
    expect(poly).toEqual([
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ]);
  });
});
