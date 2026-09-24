import { describe, expect, it } from 'vitest';
import {
  CAPABILITY_ORDER, LEVEL_LABEL, capabilityOptions, capabilityPhrase, orderedCapabilities
} from './capabilities';

describe('the disclosure-capability vocabulary', () => {
  it('names the five capabilities in the order this product states them everywhere else', () => {
    expect(CAPABILITY_ORDER).toEqual(['IDENTITY', 'EXACT_LOCATION', 'UNREDACTED_IMAGES', 'FINANCIALS', 'FLOOR_PLANS']);
  });

  it('gives every capability a label and never leaves one reading as a shouted enum', () => {
    for (const name of CAPABILITY_ORDER) expect(LEVEL_LABEL[name]).toBeTruthy();
  });

  it('offers the five as chooser rows, never the umbrella level', () => {
    expect(capabilityOptions().map((o) => o.value)).toEqual([...CAPABILITY_ORDER]);
    expect(capabilityOptions().map((o) => o.value)).not.toContain('FULL_CONFIDENTIAL');
  });

  it('orders a set into the declared order and drops a name this build has never heard of', () => {
    expect(orderedCapabilities(['FLOOR_PLANS', 'IDENTITY'])).toEqual(['IDENTITY', 'FLOOR_PLANS']);
    expect(orderedCapabilities(['FINANCIALS', 'TELEPATHY'])).toEqual(['FINANCIALS']);
  });

  it('answers an empty list for no grant and for an empty grant alike, and the caller tells them apart', () => {
    expect(orderedCapabilities(null)).toEqual([]);
    expect(orderedCapabilities([])).toEqual([]);
  });

  it('reads a set back as a phrase a seller can read', () => {
    expect(capabilityPhrase(['FINANCIALS'])).toBe('financials');
    expect(capabilityPhrase(['FLOOR_PLANS', 'FINANCIALS'])).toBe('financials and floor plans');
    expect(capabilityPhrase(['IDENTITY', 'FINANCIALS', 'FLOOR_PLANS'])).toBe('identity, financials and floor plans');
  });

  it('says nothing at all for an empty set, so the caller supplies its own sentence for that', () => {
    expect(capabilityPhrase([])).toBe('');
    expect(capabilityPhrase(null)).toBe('');
  });
});
