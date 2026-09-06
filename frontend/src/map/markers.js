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

export function practicePin(label, selected) {
  // Selected: a single prominent dot — the open callout above it carries the price, so a
  // pill as well would duplicate it.
  if (selected) {
    return (
      '<div style="display:flex;justify-content:center;align-items:flex-end;height:100%">' +
        '<div style="width:20px;height:20px;border-radius:999px;background:#339dde;' +
        'border:3px solid #fff;box-shadow:0 2px 7px rgba(0,58,112,.45)"></div>' +
      "</div>"
    );
  }
  return (
    '<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">' +
      '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;font-size:11.5px;font-weight:800;' +
      "white-space:nowrap;padding:3px 8px;border-radius:5px;background:#ffffff;color:#003a70;" +
      "border:1px solid rgba(0,58,112,.18);box-shadow:0 1px 4px rgba(0,58,112,.22);" + '">' + label + "</div>" +
      '<div style="width:9px;height:9px;border-radius:999px;background:#003a70;' +
      'border:2px solid #fff;box-shadow:0 1px 4px rgba(0,58,112,.4)"></div>' +
    "</div>"
  );
}

export function practiceCallout(p) {
  const photo = p.photoSrc
    ? '<div style="width:62px;height:48px;flex:none;border-radius:4px;overflow:hidden;background:#deecf7">' +
      '<img src="' + p.photoSrc + '" alt="" style="width:100%;height:100%;object-fit:cover;object-position:60% 45%;display:block"></div>'
    : "";
  return (
    '<div style="display:flex;gap:9px;align-items:center;font-family:ProximaNova,Arial,Helvetica,sans-serif">' +
      photo +
      '<div style="min-width:0">' +
        '<div style="font-size:12px;font-weight:800;color:#003a70;white-space:nowrap">' + p.name + "</div>" +
        '<div style="font-size:15px;font-weight:800;color:#003a70;line-height:1.2">' + p.priceLabel + "</div>" +
        '<div style="font-size:10.5px;color:#494949;white-space:nowrap">' + (p.meta || "") + "</div>" +
      "</div>" +
    "</div>"
  );
}
