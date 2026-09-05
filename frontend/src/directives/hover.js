// The prototype expresses hover states as inline style deltas (style-hover="…").
// This directive applies that CSS string on pointer-enter and reverts on leave,
// which keeps the markup 1:1 with the approved design.
const parse = (css) =>
  String(css || "")
    .split(";")
    .map((d) => d.trim())
    .filter(Boolean)
    .map((d) => {
      const i = d.indexOf(":");
      return [d.slice(0, i).trim(), d.slice(i + 1).trim()];
    });

export const vHover = {
  mounted(el, binding) {
    const decls = parse(binding.value);
    const prev = new Map();
    el.__hoverOn = () => {
      decls.forEach(([prop, val]) => {
        prev.set(prop, el.style.getPropertyValue(prop));
        el.style.setProperty(prop, val);
      });
    };
    el.__hoverOff = () => {
      decls.forEach(([prop]) => {
        const p = prev.get(prop);
        if (p) el.style.setProperty(prop, p);
        else el.style.removeProperty(prop);
      });
    };
    el.addEventListener("mouseenter", el.__hoverOn);
    el.addEventListener("mouseleave", el.__hoverOff);
  },
  unmounted(el) {
    el.removeEventListener("mouseenter", el.__hoverOn);
    el.removeEventListener("mouseleave", el.__hoverOff);
  }
};
