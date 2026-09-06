import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App.vue';
import { vHover } from './directives/hover.js';

const mountApp = () => mount(App, { global: { directives: { hover: vHover } } });
// A real keystroke: the DOM value changes and ONLY an `input` event fires — `change` waits for blur or
// Enter. (`setValue()` is not used: @vue/test-utils fires both events, which would hide the difference.)
const type = async (field, text) => { field.element.value = text; await field.trigger('input'); };
afterEach(() => vi.unstubAllGlobals());

describe('the email field', () => {
  it('commits every keystroke, so Enter submits what the visitor can see (John, 2026-09-06)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ status: 202 })));
    const w = mountApp();
    const field = w.find('input[type="email"]');
    await type(field, 'you@practice.com');
    await field.trigger('keydown', { key: 'Enter' });
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();
    expect(fetch).toHaveBeenCalledWith('/api/interest', expect.objectContaining({ body: JSON.stringify({ email: 'you@practice.com' }) }));
    expect(w.text()).toContain("You're on the list");
  });
  it('clears a previous error as soon as the visitor types', async () => {
    const w = mountApp();
    const field = w.find('input[type="email"]');
    await type(field, 'nope');
    await field.trigger('keydown', { key: 'Enter' });
    expect(w.text()).toContain("That address doesn't look right");
    await type(field, 'you@practice.com');
    expect(w.text()).not.toContain("That address doesn't look right");
  });
});
