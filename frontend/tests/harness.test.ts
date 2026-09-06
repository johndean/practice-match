import { describe, expect, it } from 'vitest';
import { BLANK_GIF } from './harness';

// The stubbed basemap tile must be TRANSPARENT, not merely blank-looking (controller ruling
// 2026-09-07). MarketMapV3.jsx:190 adds the Esri label tile layer with `pane: "shadowPane"`
// — z-index 500, above the community mosaic's overlay pane at 400 — so an opaque stub paints
// a solid square over every mosaic cell and `npm run test:visual` then compares two unshaded
// maps at zero tolerance while proving nothing about C5/C7. That is exactly what the
// pre-ruling constant did: R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw== has no Graphic
// Control Extension, so it is opaque white. This walks the GIF's real block structure rather
// than pattern-matching the base64, so any future swap has to survive the same check.

/** The Graphic Control Extension's packed field, or null when the GIF carries no GCE. */
function graphicControlFlags(gif: Buffer): number | null {
  expect(gif.subarray(0, 6).toString('latin1')).toBe('GIF89a'); // GIF87a has no GCE at all
  const packed = gif[10];
  // Logical screen descriptor is 7 bytes after the 6-byte header; a global colour table, when
  // present (bit 7), follows it with 2^(N+1) three-byte entries where N is the low 3 bits.
  let i = 13 + (packed & 0x80 ? 3 * (1 << ((packed & 0x07) + 1)) : 0);
  while (i < gif.length) {
    const block = gif[i];
    if (block === 0x3b) return null;          // trailer — no GCE anywhere
    if (block === 0x2c) return null;          // image descriptor reached first — no GCE
    if (block !== 0x21) return null;          // not an extension introducer: give up
    const label = gif[i + 1];
    const size = gif[i + 2];
    if (label === 0xf9) return gif[i + 3];    // GCE: <introducer><label><blockSize><packed>
    i += 3 + size;
    while (gif[i] !== 0x00) i += gif[i] + 1;  // skip any remaining data sub-blocks
    i += 1;
  }
  return null;
}

describe('the stubbed basemap tile', () => {
  it('is a 1×1 GIF', () => {
    expect(BLANK_GIF.readUInt16LE(6)).toBe(1);
    expect(BLANK_GIF.readUInt16LE(8)).toBe(1);
  });

  it('declares a transparent colour, so the label tiles cannot hide the mosaic', () => {
    const flags = graphicControlFlags(BLANK_GIF);
    expect(flags, 'the tile stub carries no Graphic Control Extension — it is opaque').not.toBeNull();
    expect(flags! & 0x01, 'the GCE does not set the transparent-colour flag').toBe(1);
  });

  it('rejects the opaque constant this replaced', () => {
    const opaque = Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', 'base64');
    expect(graphicControlFlags(opaque)).toBeNull();
  });
});
