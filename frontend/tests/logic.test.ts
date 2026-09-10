import { describe, it, expect } from 'vitest';
import { Component } from '../src/logic';

describe('logic.js characterisation — Task B10: undefined metrics', () => {
  it('marketPanel with all undefined metrics does not throw, render undefined/NaN, or show competition/score', () => {
    const component = new Component();
    component.props = { auth: null };
    component.state = { mdTab: 'insights' };

    const emptyComm = {
      pop: undefined,
      growth: undefined,
      income: undefined,
      hh: undefined,
      vets: undefined,
      econ_k: undefined,
    };

    const listing = { id: 'test', area: 'TestArea', market: 'Test, XX' };

    // Should not throw
    const panel = component.marketPanel(listing, emptyComm, [], 'Test, XX');

    // Check that the returned object contains no undefined or NaN strings
    const panelStr = JSON.stringify(panel);
    expect(panelStr).not.toContain('undefined');
    expect(panelStr).not.toContain('NaN');

    // Check specific fields that were problematic
    expect(panel.compEstab).toBeUndefined();
    expect(panel.compPer10k).toBeUndefined();
    expect(panel.compLevel).toBeUndefined();
    expect(panel.score).toBeUndefined();
    expect(panel.scoreLabel).toBeUndefined();

    // compBars should be empty array or undefined
    if (panel.compBars !== undefined) {
      expect(Array.isArray(panel.compBars)).toBe(true);
    }

    // oppTiles entries with undefined metrics should have empty labels
    const oppTilesWithValues = panel.oppTiles?.filter((t: any) => t.on === true) || [];
    expect(oppTilesWithValues.length).toBe(0); // None should be "on" when all metrics undefined
  });

  it('marketPanel with full figures renders all competition and score fields', () => {
    const component = new Component();
    component.props = { auth: null };
    component.state = { mdTab: 'insights' };

    const fullComm = {
      pop: '100000',
      growth: '+2.0% since 2020',
      income: '75000',
      hh: '50000',
      vets: 25,
      econ_k: 500,
    };

    const listing = { id: 'test', area: 'TestArea', market: 'Test, XX' };

    const panel = component.marketPanel(listing, fullComm, [], 'Test, XX');

    // Should have all competition and score fields
    expect(panel.compEstab).toBeDefined();
    expect(panel.compEstab).not.toBe('undefined');
    expect(panel.compPer10k).toBeDefined();
    expect(panel.compPer10k).not.toBe('NaN');
    expect(panel.compLevel).toBeDefined();
    expect(panel.compLevel).not.toContain('undefined');
    expect(panel.score).toBeDefined();
    expect(typeof panel.score).toBe('number');
    expect(panel.scoreLabel).toBeDefined();
    expect(panel.scoreLabel).not.toBe('undefined');
  });
});
