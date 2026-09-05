// Minimal React-shaped base class so the approved logic runs unchanged under Vue.
// Replace with a Pinia store only if you also re-verify every screen against the prototype.
export class DCLogic {
  constructor(props = {}) {
    this.props = props || {};
  }

  setState(patch, cb) {
    const next = typeof patch === "function" ? patch(this.state) : patch;
    if (next) Object.assign(this.state, next);
    if (typeof cb === "function") cb();
  }
}
