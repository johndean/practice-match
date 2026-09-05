// Minimal base class so the approved logic class runs unchanged under Vue.
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
