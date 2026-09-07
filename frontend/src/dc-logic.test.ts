import { describe, expect, it } from 'vitest';
import { DCLogic } from './dc-logic.js';

// `dc-logic.js` is the 13-line React-shaped base class that lets the approved prototype's
// script (`logic.js`, a verbatim port) run unchanged under Vue: every screen interaction in
// the app goes through this `setState`. It is hand-written, not generated, and it had no test
// of its own — the re-review's M10 finding. The four properties below are the ones `logic.js`
// relies on and the ones a Pinia rewrite would have to preserve (see the file's own warning).
describe('DCLogic — the prototype\'s setState, ported', () => {
  class C extends DCLogic {
    constructor(props?: unknown) {
      super(props as Record<string, unknown>);
      this.state = { screen: 'browse', activeId: null };
    }
    state: Record<string, unknown>;
  }

  it('merges an object patch into the SAME state object, leaving other keys alone', () => {
    const c = new C();
    const before = c.state;
    c.setState({ activeId: 'p2' });
    expect(c.state).toBe(before);   // Vue's reactive proxy wraps this object; replacing it would break every binding
    expect(c.state).toEqual({ screen: 'browse', activeId: 'p2' });
  });

  it('calls a functional patch with the current state, React-style', () => {
    const c = new C();
    c.setState({ activeId: 'p1' });
    c.setState((s: Record<string, unknown>) => ({ activeId: `${s.activeId}-again` }));
    expect(c.state.activeId).toBe('p1-again');
  });

  it('ignores a patch that yields nothing — a functional patch may decline to change state', () => {
    const c = new C();
    c.setState(() => null);
    expect(c.state).toEqual({ screen: 'browse', activeId: null });
  });

  it('runs the callback after the merge, and tolerates its absence', () => {
    const c = new C();
    const seen: unknown[] = [];
    c.setState({ screen: 'detail' }, () => seen.push(c.state.screen));
    expect(seen).toEqual(['detail']);
    expect(() => c.setState({ screen: 'browse' })).not.toThrow();
    // The prototype calls setState(patch, cb) with cb sometimes undefined; a non-function
    // second argument must be ignored rather than called.
    expect(() => c.setState({ screen: 'browse' }, undefined)).not.toThrow();
  });

  it('defaults props to an empty object, whether omitted or passed as null', () => {
    expect(new C().props).toEqual({});
    expect(new C(null).props).toEqual({});
    expect(new C({ startScreen: 'browse' }).props).toEqual({ startScreen: 'browse' });
  });
});
