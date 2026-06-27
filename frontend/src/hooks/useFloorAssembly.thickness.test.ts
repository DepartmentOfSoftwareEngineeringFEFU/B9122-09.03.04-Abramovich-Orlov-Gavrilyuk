import { describe, it, expect } from 'vitest';
import {
  draftsToInputs,
  connectorsToDrafts,
  DEFAULT_CONNECTOR_THICKNESS_M,
  type ConnectorDraft,
} from './useFloorAssembly';
import type { Connector } from '../types/floorAssembly';

describe('draftsToInputs', () => {
  it('passes thickness_m through to the API input', () => {
    const drafts: ConnectorDraft[] = [
      { points: [[0.1, 0.2], [0.5, 0.6]], thickness_m: 0.3 },
      { points: [[0.2, 0.3], [0.7, 0.8]], thickness_m: 1.25 },
    ];
    const out = draftsToInputs(drafts);
    expect(out[0].thickness_m).toBe(0.3);
    expect(out[1].thickness_m).toBe(1.25);
    expect(out[0].points).toEqual([[0.1, 0.2], [0.5, 0.6]]);
  });
});

describe('connectorsToDrafts', () => {
  it('keeps server thickness_m when present', () => {
    const server: Connector[] = [
      { id: 1, points: [[0, 0], [1, 1]], thickness_m: 0.5, height_m: null, connects: null },
    ];
    expect(connectorsToDrafts(server)[0].thickness_m).toBe(0.5);
  });

  it('falls back to DEFAULT_CONNECTOR_THICKNESS_M when server thickness is null', () => {
    const server: Connector[] = [
      { id: 2, points: [[0, 0], [1, 1]], thickness_m: null, height_m: null, connects: null },
    ];
    expect(connectorsToDrafts(server)[0].thickness_m).toBe(DEFAULT_CONNECTOR_THICKNESS_M);
  });
});
