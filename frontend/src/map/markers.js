// Marker HTML builders, ported verbatim from the approved prototype. Inline styles are intentional: divIcons live outside the app stylesheet scope.

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
