import { afterEach, describe, expect, it, vi } from 'vitest';
import { Component } from './logic.js';

const make = () => new Component();
const respond = (status) => vi.fn(async () => ({ status }));

afterEach(() => vi.unstubAllGlobals());

describe('valid()', () => {
  it('accepts ordinary addresses and rejects malformed ones', () => {
    const c = make();
    expect(c.valid('you@practice.com')).toBe(true);
    expect(c.valid(' You@Practice.COM ')).toBe(true);
    for (const bad of ['', 'nope', 'a@b', 'a b@c.com', null, undefined]) expect(c.valid(bad)).toBe(false);
  });
});

describe('submit()', () => {
  it('asks for an address when the field is empty and does not call the network', async () => {
    const c = make(); vi.stubGlobal('fetch', respond(202));
    await c.submit();
    expect(c.state.error).toBe('Enter your email address.');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects a malformed address without calling the network', async () => {
    const c = make(); c.state.email = 'nope'; vi.stubGlobal('fetch', respond(202));
    await c.submit();
    expect(c.state.error).toBe("That address doesn't look right. Check it and try again.");
    expect(fetch).not.toHaveBeenCalled();
  });
  it('posts the trimmed address to /api/interest and shows the confirmed state on 202', async () => {
    const c = make(); c.state.email = '  You@Practice.com '; vi.stubGlobal('fetch', respond(202));
    await c.submit();
    expect(fetch).toHaveBeenCalledWith('/api/interest', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'You@Practice.com' })
    });
    expect(c.state).toMatchObject({ done: true, error: '', email: 'You@Practice.com', sending: false });
  });
  it('explains a 429 in the error slot and stays on the form', async () => {
    const c = make(); c.state.email = 'you@practice.com'; vi.stubGlobal('fetch', respond(429));
    await c.submit();
    expect(c.state).toMatchObject({ done: false, error: 'Too many attempts — please try again later.', sending: false });
  });
  it('treats any other status as a failure the visitor can retry', async () => {
    const c = make(); c.state.email = 'you@practice.com'; vi.stubGlobal('fetch', respond(500));
    await c.submit();
    expect(c.state).toMatchObject({ done: false, error: 'Something went wrong. Please try again.', sending: false });
  });
  it('treats a network failure the same way', async () => {
    const c = make(); c.state.email = 'you@practice.com';
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    await c.submit();
    expect(c.state).toMatchObject({ done: false, error: 'Something went wrong. Please try again.', sending: false });
  });
  it('ignores a second click while a request is in flight', async () => {
    const c = make(); c.state.email = 'you@practice.com';
    let release; vi.stubGlobal('fetch', vi.fn(() => new Promise((r) => { release = () => r({ status: 202 }); })));
    const first = c.submit();
    await c.submit();
    expect(fetch).toHaveBeenCalledTimes(1);
    release(); await first;
    expect(c.state.done).toBe(true);
  });
});

describe('renderVals()', () => {
  it('maps state to the template: form/done flags, error, input border, five blocks, four rings', () => {
    const c = make(); const v = c.renderVals();
    expect(v.isForm).toBe(true); expect(v.isDone).toBe(false); expect(v.hasError).toBe(false);
    expect(v.blocks).toHaveLength(5); expect(v.rings).toHaveLength(4);
    expect(v.inputStyle).toContain('border: 1px solid #c3d4e2');
    c.state.error = 'x';
    expect(c.renderVals().inputStyle).toContain('var(--color-red)');
  });
  it('advances the teaser on poke and stops at the last quip', () => {
    const c = make();
    for (let i = 0; i < 10; i++) c.renderVals().poke();
    expect(c.renderVals().tease).toBe(c.TEASES[c.TEASES.length - 1]);
  });
  it('setEmail clears a previous error; Enter submits; reset returns to the form', async () => {
    const c = make(); c.state.error = 'old';
    c.renderVals().setEmail({ target: { value: 'you@practice.com' } });
    expect(c.state).toMatchObject({ email: 'you@practice.com', error: '' });
    vi.stubGlobal('fetch', respond(202));
    c.renderVals().onKey({ key: 'Enter' });
    await new Promise((r) => setTimeout(r, 0));
    expect(c.state.done).toBe(true);
    c.renderVals().onKey({ key: 'a' });
    c.renderVals().reset();
    expect(c.state).toMatchObject({ done: false, email: '', error: '' });
  });
});
