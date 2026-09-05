// Market Data map surface: street/satellite basemaps, drive-time rings,
// community data bubbles sized and colored from real coordinates, price pins.
// Loaded via <x-import component="MarketMap" from="./MarketMap.jsx">.

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

const BASEMAPS = {
  map: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles © Esri"
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics"
  }
};

function pricePin(label, active) {
  const bg = active ? "var(--vf-navy)" : "var(--vf-white)";
  const fg = active ? "var(--vf-white)" : "var(--vf-navy)";
  return (
    '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;' +
    "white-space:nowrap;padding:5px 10px;border-radius:999px;background:" + bg + ";color:" + fg + ";" +
    "border:1px solid " + (active ? "var(--vf-navy)" : "#d4dde5") + ";" +
    'box-shadow:0 2px 6px rgba(0,58,112,.25);">' + label + "</div>"
  );
}

// Zoom-in uses the authentic VIN icon (assets/icons/add-plus.svg).
// SUBSTITUTIONS — the VIN set has no minus, target, heart or check icon. Per the design
// system's iconography rule (no unicode glyphs as icons) these are closest-match
// filled silhouettes matched to the set's heavy/filled weight. Replace when VIN ships them.
const ICON_MINUS = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="#002855" d="M112 272h416a48 48 0 0 1 0 96H112a48 48 0 0 1 0-96z"/></svg>');
const ICON_TARGET = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="#002855" d="M320 40a40 40 0 0 1 40 40v26a216 216 0 0 1 174 174h26a40 40 0 0 1 0 80h-26a216 216 0 0 1-174 174v26a40 40 0 0 1-80 0v-26A216 216 0 0 1 106 360H80a40 40 0 0 1 0-80h26a216 216 0 0 1 174-174V80a40 40 0 0 1 40-40zm0 144a136 136 0 1 0 0 272 136 136 0 0 0 0-272zm0 72a64 64 0 1 1 0 128 64 64 0 0 1 0-128z"/></svg>');

const iconImg = (src, size) =>
  React.createElement("img", { src, alt: "", width: size, height: size, style: { display: "block", opacity: .85 } });

function dot(size, color, border) {
  return (
    '<div style="width:' + size + "px;height:" + size + "px;border-radius:999px;background:" + color +
    ";border:2px solid " + (border || "rgba(255,255,255,.85)") + ';box-sizing:border-box;"></div>'
  );
}

function MarketMap(props) {
  const {
    practices = [],
    communities = [],
    layers = {},
    valueLayer = null,
    basemap = "map",
    activeId = null,
    onSelect,
    onBasemap,
    center = [30.31, -97.75],
    zoom = 10,
    driveCenter = null,
    resizeKey = ""
  } = props;

  const hostRef = React.useRef(null);
  const mapRef = React.useRef(null);
  const tileRef = React.useRef(null);
  const labelRef = React.useRef(null);
  const overlayRef = React.useRef(null);
  const pinRef = React.useRef(null);
  const [status, setStatus] = React.useState("loading");

  React.useEffect(() => {
    let dead = false;
    loadLeaflet()
      .then((L) => {
        if (dead || !hostRef.current || mapRef.current) return;
        const map = L.map(hostRef.current, { center, zoom, zoomControl: false, attributionControl: true });
        tileRef.current = L.tileLayer(BASEMAPS[basemap].url, {
          attribution: BASEMAPS[basemap].attribution,
          maxZoom: 18
        }).addTo(map);
        // The gray canvas carries almost no labels — Esri's matching reference layer supplies them.
        labelRef.current = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18, pane: "shadowPane" });
        if (basemap === "map") labelRef.current.addTo(map);
        overlayRef.current = L.layerGroup().addTo(map);
        pinRef.current = L.layerGroup().addTo(map);
        L.control.scale({ imperial: true, metric: false, position: "bottomright" }).addTo(map);
        mapRef.current = map;
        setStatus("ready");
        setTimeout(() => map.invalidateSize(), 60);
      })
      .catch(() => !dead && setStatus("error"));
    return () => {
      dead = true;
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, []);

  React.useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!L || !map || !tileRef.current) return;
    const cfg = BASEMAPS[basemap] || BASEMAPS.map;
    tileRef.current.setUrl(cfg.url);
    if (labelRef.current) {
      if (basemap === "map") labelRef.current.addTo(map);
      else map.removeLayer(labelRef.current);
    }
    tileRef.current.options.attribution = cfg.attribution;
    map.attributionControl._update && map.attributionControl._update();
  }, [basemap, status]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !center) return;
    map.setView(center, zoom, { animate: true });
  }, [center && center[0], center && center[1], zoom, status]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const t = setTimeout(() => map.invalidateSize(), 80);
    return () => clearTimeout(t);
  }, [resizeKey]);

  // Drive-time rings + community data bubbles
  React.useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!L || !map || !overlayRef.current) return;
    const g = overlayRef.current;
    g.clearLayers();
    const hub = driveCenter || center;

    if (layers.drive10 && hub) {
      L.circle(hub, {
        radius: 16000, stroke: false, fillColor: "#339dde", fillOpacity: 0.16, interactive: false
      }).addTo(g);
    }
    if (layers.drive5 && hub) {
      L.circle(hub, {
        radius: 8000, stroke: false, fillColor: "#003a70", fillOpacity: 0.2, interactive: false
      }).addTo(g);
    }

    if (valueLayer) {
      communities.forEach((c) => {
        const v = c.values[valueLayer];
        if (v == null) return;
        const size = 16 + Math.round(v.t * 30);
        L.marker([c.lat, c.lng], {
          icon: L.divIcon({ html: dot(size, v.color), className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
          interactive: true
        })
          .bindTooltip(c.name + " — " + v.label, { direction: "top", offset: [0, -6] })
          .addTo(g);
      });
    }

    if (layers.competition) {
      communities.forEach((c) => {
        const n = c.vets || 0;
        if (!n) return;
        const size = 8 + Math.min(n, 14);
        L.marker([c.lat + 0.012, c.lng + 0.012], {
          icon: L.divIcon({ html: dot(size, "rgba(120,86,190,.75)", "rgba(255,255,255,.9)"), className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
          interactive: true
        })
          .bindTooltip(c.name + " — " + n + " veterinary establishments", { direction: "top", offset: [0, -6] })
          .addTo(g);
      });
    }
  }, [communities, layers.drive5, layers.drive10, layers.competition, valueLayer, driveCenter && driveCenter[0], status]);

  // Practice price pins
  React.useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!L || !map || !pinRef.current) return;
    pinRef.current.clearLayers();
    if (!layers.practices) return;
    practices.forEach((p) => {
      const active = p.id === activeId;
      L.marker([p.lat, p.lng], {
        icon: L.divIcon({ html: pricePin(p.priceLabel, active), className: "", iconSize: [72, 26], iconAnchor: [36, 13] }),
        zIndexOffset: active ? 1000 : 0
      })
        .on("click", () => onSelect && onSelect(p.id))
        .addTo(pinRef.current);
    });
  }, [practices, activeId, layers.practices, status]);

  // The VIN icons are circle-enclosed, so each icon IS the button — no wrapper disc.
  const ctrlBtn = {
    width: "32px", height: "32px", display: "grid", placeItems: "center",
    background: "none", border: 0, borderRadius: "999px", cursor: "pointer", padding: 0,
    filter: "drop-shadow(0 1px 3px rgba(0,58,112,.3))"
  };

  return React.createElement(
    "div",
    { style: { position: "absolute", inset: 0, background: "#f5f5f5" } },
    React.createElement("div", { ref: hostRef, style: { position: "absolute", inset: 0 } }),
    status === "ready" &&
      React.createElement(
        "div",
        { style: { position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", zIndex: 500, display: "flex", flexDirection: "column", gap: "4px" } },
        React.createElement("button", { style: ctrlBtn, onClick: () => mapRef.current && mapRef.current.zoomIn(), "aria-label": "Zoom in" }, iconImg("assets/icons/zoom-in-disc.svg", 28)),
        React.createElement("button", { style: ctrlBtn, onClick: () => mapRef.current && mapRef.current.zoomOut(), "aria-label": "Zoom out" }, iconImg("assets/icons/sub-zoom-out-disc.svg", 28)),
        React.createElement("button", { style: Object.assign({}, ctrlBtn, { marginTop: "6px" }), onClick: () => mapRef.current && mapRef.current.setView(center, zoom), "aria-label": "Recenter" }, iconImg("assets/icons/sub-recenter-disc.svg", 28))
      ),
    status !== "ready" &&
      React.createElement(
        "div",
        { style: { position: "absolute", inset: 0, display: "grid", placeItems: "center", background: "#f5f5f5", textAlign: "center", padding: "24px", fontFamily: "ProximaNova, Arial, Helvetica, sans-serif" } },
        status === "loading"
          ? React.createElement("div", { style: { fontSize: "13px", fontWeight: 500, color: "var(--vf-text)" } }, "Loading map…")
          : React.createElement(
              "div",
              { style: { maxWidth: "320px" } },
              React.createElement("div", { style: { fontFamily: "ProximaNova, Arial, Helvetica, sans-serif", fontSize: "17px", fontWeight: 700, color: "var(--vf-navy)" } }, "Map unavailable"),
              React.createElement("p", { style: { fontSize: "13px", color: "var(--vf-text)", lineHeight: 1.6 } }, "The map service could not be reached. Listings and market figures on the right are unaffected, and every data layer remains available as a table.")
            )
      )
  );
}

module.exports = { MarketMap };
