// Marker HTML builders, ported verbatim from the approved prototype. Inline styles are intentional: divIcons live outside the app stylesheet scope.

export function pill(label, active, muted) {
  const bg = muted ? "var(--color-steel)" : active ? "var(--vf-accent)" : "var(--color-white)";
  const fg = muted ? "var(--color-white)" : "var(--color-navy)";
  const border = muted ? "var(--color-steel)" : active ? "var(--vf-accent)" : "var(--border-subtle)";
  return (
    '<div style="' +
    "font-family:ProximaNova,Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;" +
    "letter-spacing:-.01em;white-space:nowrap;padding:5px 10px;border-radius:999px;" +
    "background:" + bg + ";color:" + fg + ";border:1px solid " + border + ";" +
    "box-shadow:0 2px 5px rgba(0,58,112,.22);transform:translateY(" + (active ? "-2px" : "0") + ");" +
    '">' + label + "</div>"
  );
}

export function clusterIcon(count) {
  return (
    '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;width:44px;height:44px;' +
    "border-radius:999px;background:var(--color-navy);color:var(--color-white);display:flex;align-items:center;" +
    "justify-content:center;font-size:15px;font-weight:800;border:3px solid rgba(255,255,255,.75);" +
    'box-shadow:0 4px 10px rgba(0,58,112,.3);">' + count + "</div>"
  );
}

export function clusterize(markers, zoom) {
  if (zoom >= 10) return markers.map((m) => ({ kind: "pin", m }));
  const cell = zoom >= 8 ? 0.28 : 0.9;
  const buckets = new Map();
  markers.forEach((m) => {
    const key = Math.round(m.lat / cell) + ":" + Math.round(m.lng / cell);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(m);
  });
  const out = [];
  buckets.forEach((group) => {
    if (group.length === 1) out.push({ kind: "pin", m: group[0] });
    else {
      const lat = group.reduce((a, m) => a + m.lat, 0) / group.length;
      const lng = group.reduce((a, m) => a + m.lng, 0) / group.length;
      out.push({ kind: "cluster", lat, lng, count: group.length, ids: group.map((m) => m.id) });
    }
  });
  return out;
}

export function pricePin(label, active) {
  const bg = active ? "var(--vf-navy)" : "var(--vf-white)";
  const fg = active ? "var(--vf-white)" : "var(--vf-navy)";
  return (
    '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;' +
    "white-space:nowrap;padding:5px 10px;border-radius:999px;background:" + bg + ";color:" + fg + ";" +
    "border:1px solid " + (active ? "var(--vf-navy)" : "#d4dde5") + ";" +
    'box-shadow:0 2px 6px rgba(0,58,112,.25);">' + label + "</div>"
  );
}

export function dot(size, color, border) {
  return (
    '<div style="width:' + size + "px;height:" + size + "px;border-radius:999px;background:" + color +
    ";border:2px solid " + (border || "rgba(255,255,255,.85)") + ';box-sizing:border-box;"></div>'
  );
}
