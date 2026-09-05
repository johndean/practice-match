// Ported verbatim from the approved 'Coming Soon.dc.html'. Values are design-approved.
import { DCLogic } from './dc-logic.js';

class Component extends DCLogic {
  state = { email: "", error: "", done: false, pokes: 0, sending: false };

  // Redacted teaser. Widths are arbitrary — deliberately NOT the letter counts of any
  // real sentence, so nothing can be inferred from them. Clicking only changes the
  // quip; the blocks never resolve.
  TEASES = [
    "No, we're not telling. Not yet.",
    "Still not telling.",
    "You can keep clicking. We admire the persistence.",
    "A colleague of yours asked the same thing.",
    "It'll be worth the wait. That's all you get."
  ];

  valid(e) {
    return /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(String(e || "").trim());
  }

  // Wired to the Practice Match API (spec 2026-09-06): the page's own validation runs first,
  // then one POST; 202 confirms, 429 and any failure use the error slot below the field.
  submit = async () => {
    const e = this.state.email.trim();
    if (!e) return this.setState({ error: "Enter your email address." });
    if (!this.valid(e)) return this.setState({ error: "That address doesn't look right. Check it and try again." });
    if (this.state.sending) return;
    this.setState({ sending: true, error: "" });
    try {
      const res = await fetch("/api/interest", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: e })
      });
      if (res.status === 202) return this.setState({ sending: false, error: "", done: true, email: e });
      if (res.status === 429) return this.setState({ sending: false, error: "Too many attempts — please try again later." });
      this.setState({ sending: false, error: "Something went wrong. Please try again." });
    } catch {
      this.setState({ sending: false, error: "Something went wrong. Please try again." });
    }
  };

  renderVals() {
    const s = this.state;
    return {
      email: s.email,
      hasError: !!s.error,
      errorText: s.error,
      isForm: !s.done,
      isDone: s.done,
      setEmail: (ev) => this.setState({ email: ev.target.value, error: "" }),
      onKey: (ev) => { if (ev.key === "Enter") this.submit(); },
      submit: this.submit,
      reset: () => this.setState({ done: false, email: "", error: "" }),
      tease: this.TEASES[Math.min(s.pokes, this.TEASES.length - 1)],
      blocks: [58, 92, 34, 116, 46].map((w, i) => ({
        style: "display: block; width: " + w + "px; height: 13px; border-radius: 3px; background: var(--vf-navy); " +
          "opacity: .16; animation: cs-shimmer 4.2s ease-in-out infinite " + (i * 0.32) + "s;"
      })),
      poke: () => this.setState({ pokes: Math.min(s.pokes + 1, this.TEASES.length - 1) }),
      // Concentric accent rings, staggered — the palette's own device, saying only
      // that work is underway.
      rings: [0, 1, 2, 3].map((i) => ({
        style: "position: absolute; inset: 0; border: 1px solid #003a70; border-radius: 999px; opacity: 0; " +
          "animation: cs-ring 9s var(--easing-out) infinite " + (i * 2.25) + "s;"
      })),
      inputStyle: "flex: 1 1 250px; min-width: 0; height: 54px; padding: 0 16px; font-size: 16px; color: #003a70; background: #ffffff; border: 1px solid " +
        (s.error ? "var(--color-red)" : "#c3d4e2") + "; border-radius: 6px; outline: none;"
    };
  }
}

export { Component };
