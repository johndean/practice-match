import { describe, expect, it } from 'vitest';
import { practiceCallout, practicePin } from './markers.js';

describe('marker HTML builders (moved from lib/leaflet.js)', () => {
  it('practicePin unselected: a label chip above a small navy dot', () => {
    const html = practicePin('$1.45M', false);
    expect(html).toContain('flex-direction:column;align-items:center;gap:3px;');
    expect(html).toContain('font-size:11.5px;font-weight:800;');
    expect(html).toContain('background:#ffffff;color:#003a70;');
    expect(html).toContain('>$1.45M</div>');
    expect(html).toContain('width:9px;height:9px;border-radius:999px;background:#003a70;');
  });

  it('practicePin selected: one prominent dot and no chip — the open callout already carries the price', () => {
    const html = practicePin('$1.45M', true);
    expect(html).toContain('width:20px;height:20px;border-radius:999px;background:#339dde;');
    expect(html).toContain('border:3px solid #fff;');
    expect(html).not.toContain('$1.45M');
  });

  it('practiceCallout renders the photo, name, price and meta', () => {
    const html = practiceCallout({ name: 'Cedar Park', priceLabel: '$1.45M', meta: '3 DVMs · 4,200 sq ft', photoSrc: '/assets/photos/round-rock-exterior-street.webp' });
    expect(html).toContain('<img src="/assets/photos/round-rock-exterior-street.webp"');
    expect(html).toContain('object-position:60% 45%');
    expect(html).toContain('>Cedar Park</div>');
    expect(html).toContain('>$1.45M</div>');
    expect(html).toContain('>3 DVMs · 4,200 sq ft</div>');
  });

  it('practiceCallout omits the photo block entirely when there is no photo, and renders empty meta rather than "undefined"', () => {
    const html = practiceCallout({ name: 'Kyle', priceLabel: '$1.18M' });
    expect(html).not.toContain('<img');
    expect(html).not.toContain('undefined');
    expect(html).toContain('color:#494949;white-space:nowrap"></div>');
  });
});
