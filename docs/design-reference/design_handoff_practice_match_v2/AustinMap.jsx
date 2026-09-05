// Leaflet + OpenStreetMap map surface for the Practice Match prototype.
// Loaded via <x-import component="AustinMap" from="./AustinMap.jsx"> so that the
// map container exists before Leaflet initializes.

const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

let leafletPromise = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-leaflet]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = LEAFLET_CSS;
      link.integrity = "sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H";
      link.crossOrigin = "anonymous";
      link.setAttribute("data-leaflet", "");
      document.head.appendChild(link);
    }
    const s = document.createElement("script");
    s.src = LEAFLET_JS;
    s.integrity = "sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH";
    s.crossOrigin = "anonymous";
    s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("leaflet-failed"));
    document.head.appendChild(s);
  });
  return leafletPromise;
}

function pill(label, active, muted) {
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

function clusterIcon(count) {
  return (
    '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;width:44px;height:44px;' +
    "border-radius:999px;background:var(--color-navy);color:var(--color-white);display:flex;align-items:center;" +
    "justify-content:center;font-size:15px;font-weight:800;border:3px solid rgba(255,255,255,.75);" +
    'box-shadow:0 4px 10px rgba(0,58,112,.3);">' + count + "</div>"
  );
}

function clusterize(markers, zoom) {
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

function AustinMap(props) {
  const {
    markers = [],
    activeId = null,
    hoverId = null,
    onSelect,
    onClusterClick,
    center = [30.31, -97.75],
    zoom = 10,
    dimmed = [],
  } = props;

  const hostRef = React.useRef(null);
  const mapRef = React.useRef(null);
  const layerRef = React.useRef(null);
  const [status, setStatus] = React.useState("loading");
  const [z, setZ] = React.useState(zoom);

  React.useEffect(() => {
    let dead = false;
    loadLeaflet()
      .then((L) => {
        if (dead || !hostRef.current || mapRef.current) return;
        const map = L.map(hostRef.current, {
          center,
          zoom,
          zoomControl: false,
          attributionControl: true,
        });
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
          attribution: "Tiles © Esri",
          maxZoom: 18,
        }).addTo(map);
        // The gray canvas carries almost no labels — Esri's matching reference layer supplies them.
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18, pane: "shadowPane" }).addTo(map);
        L.control.zoom({ position: "bottomright" }).addTo(map);
        layerRef.current = L.layerGroup().addTo(map);
        map.on("zoomend", () => setZ(map.getZoom()));
        mapRef.current = map;
        setStatus("ready");
        setTimeout(() => map.invalidateSize(), 60);
      })
      .catch(() => !dead && setStatus("error"));
    return () => {
      dead = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  React.useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!L || !map || !layerRef.current) return;
    layerRef.current.clearLayers();
    clusterize(markers, z).forEach((entry) => {
      if (entry.kind === "cluster") {
        const icon = L.divIcon({
          html: clusterIcon(entry.count),
          className: "",
          iconSize: [44, 44],
          iconAnchor: [22, 22],
        });
        L.marker([entry.lat, entry.lng], { icon })
          .on("click", () => {
            map.setView([entry.lat, entry.lng], Math.max(z + 2, 11));
            if (onClusterClick) onClusterClick(entry.ids);
          })
          .addTo(layerRef.current);
      } else {
        const m = entry.m;
        const active = m.id === activeId || m.id === hoverId;
        const icon = L.divIcon({
          html: pill(m.priceLabel, active, dimmed.indexOf(m.id) > -1),
          className: "",
          iconSize: [70, 26],
          iconAnchor: [35, 13],
        });
        L.marker([m.lat, m.lng], { icon, zIndexOffset: active ? 1000 : 0 })
          .on("click", () => onSelect && onSelect(m.id))
          .addTo(layerRef.current);
      }
    });
  }, [markers, activeId, hoverId, z, status, dimmed]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const t = setTimeout(() => map.invalidateSize(), 80);
    return () => clearTimeout(t);
  }, [props.resizeKey]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !center) return;
    map.setView(center, zoom, { animate: true });
  }, [center && center[0], center && center[1], zoom, status]);

  return React.createElement(
    "div",
    { style: { position: "absolute", inset: 0, background: "#f5f5f5" } },
    React.createElement("div", { ref: hostRef, style: { position: "absolute", inset: 0 } }),
    status !== "ready" &&
      React.createElement(
        "div",
        {
          style: {
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
            background: "var(--color-off-white)",
            textAlign: "center",
            padding: "24px",
            fontFamily: "ProximaNova, Arial, Helvetica, sans-serif",
          },
        },
        status === "loading"
          ? React.createElement(
              "div",
              { style: { fontSize: "13px", fontWeight: 500, color: "var(--color-steel)" } },
              "Loading map…"
            )
          : React.createElement(
              "div",
              { style: { maxWidth: "300px" } },
              React.createElement(
                "div",
                { style: { fontSize: "16px", fontWeight: 800, color: "var(--color-navy)" } },
                "Map unavailable"
              ),
              React.createElement(
                "p",
                { style: { fontSize: "13px", color: "var(--color-steel)", lineHeight: 1.5 } },
                "The map service could not be reached. Results are still listed on the left, and location filters continue to work."
              )
            )
      )
  );
}

module.exports = { AustinMap };
