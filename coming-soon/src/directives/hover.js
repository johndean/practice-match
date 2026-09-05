// The design expresses hover states as inline style deltas (style-hover="…").
// This applies that CSS string on pointer-enter and reverts on leave, keeping the
// markup 1:1 with the approved page.
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
    el.__on = () => decls.forEach(([p, val]) => {
      prev.set(p, el.style.getPropertyValue(p));
      el.style.setProperty(p, val);
    });
    el.__off = () => decls.forEach(([p]) => {
      const was = prev.get(p);
      if (was) el.style.setProperty(p, was);
      else el.style.removeProperty(p);
    });
    el.addEventListener("mouseenter", el.__on);
    el.addEventListener("mouseleave", el.__off);
  },
  unmounted(el) {
    el.removeEventListener("mouseenter", el.__on);
    el.removeEventListener("mouseleave", el.__off);
  }
};
