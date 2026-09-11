// Market Data map, V3. One active area layer drawn as a true choropleth, plus small
// practice markers. No bubble encodings: area data shades an area, point data is a point.
//
// GEOMETRY: real Census boundary polygons, handed in as `areas` - one GeoJSON
// FeatureCollection for the active fill layer, each feature already carrying the colour
// `bucket()` chose and the tooltip `areaVals()` built, so this component classes nothing
// and formats nothing. The approximation this file used to draw (grid cells nearest each
// community's centroid, clipped to the metro bounding box) is gone: amendment A24, spec
// 2026-09-10, John's rulings D-C34-D-C37 of 2026-09-10.

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
    attribution: "Tiles \u00a9 Esri"
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery \u00a9 Esri, Maxar, Earthstar Geographics"
  }
};
const LABEL_TILES =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";

// ---- Voronoi via half-plane clipping (Sutherland–Hodgman) -------------------
function clipPolygon(poly, a, b) {
  // Keep the side of the perpendicular bisector of a–b that contains a.
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const side = (p) => -(dx * (p[0] - mx) + dy * (p[1] - my));
  const out = [];
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length];
    const sp = side(p), sq = side(q);
    if (sp >= 0) out.push(p);
    if ((sp >= 0) !== (sq >= 0)) {
      const t = sp / (sp - sq);
      out.push([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]);
    }
  }
  return out;
}

function voronoiCells(sites, bbox) {
  const frame = [
    [bbox.minLat, bbox.minLng],
    [bbox.minLat, bbox.maxLng],
    [bbox.maxLat, bbox.maxLng],
    [bbox.maxLat, bbox.minLng]
  ];
  return sites.map((s) => {
    let poly = frame;
    sites.forEach((o) => {
      if (o === s) return;
      poly = clipPolygon(poly, [s.lat, s.lng], [o.lat, o.lng]);
    });
    return { site: s, poly };
  });
}

// ---- Markers ---------------------------------------------------------------
function practicePin(label, selected) {
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

function practiceCallout(p) {
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

function MarketMapV3(props) {
  const {
    practices = [],
    communities = [],
    areas = null,
    activeLayer = null,
    basemap = "map",
    onBasemap,
    activeId = null,
    onSelect,
    onArea,
    center = [30.31, -97.75],
    zoom = 10,
    driveCenter = null,
    showDrive = false,
    resizeKey = "",
    recenterKey = 0
  } = props;

  const hostRef = React.useRef(null);
  const mapRef = React.useRef(null);
  const tileRef = React.useRef(null);
  const labelRef = React.useRef(null);
  const areaRef = React.useRef(null);
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
        labelRef.current = L.tileLayer(LABEL_TILES, { maxZoom: 18, pane: "shadowPane" });
        if (basemap === "map") labelRef.current.addTo(map);
        areaRef.current = L.layerGroup().addTo(map);
        pinRef.current = L.layerGroup().addTo(map);
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
    if (!L || !map || !tileRef.current) return;
    const cfg = BASEMAPS[basemap] || BASEMAPS.map;
    tileRef.current.setUrl(cfg.url);
    tileRef.current.options.attribution = cfg.attribution;
    if (labelRef.current) {
      if (basemap === "map") labelRef.current.addTo(map);
      else map.removeLayer(labelRef.current);
    }
    if (map.attributionControl._update) map.attributionControl._update();
  }, [basemap, status]);

  // Choropleth: contiguous cells, one active layer, hover reads the value.
  React.useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!L || !map || !areaRef.current) return;
    const g = areaRef.current;
    g.clearLayers();

    if (showDrive && driveCenter) {
      L.circle(driveCenter, {
        radius: 16000, color: "#003a70", weight: 1.5, dashArray: "4 4",
        fill: false, interactive: false
      }).addTo(g);
    }

    if (!activeLayer || !areas || !areas.features.length) return;

    const canvas = L.canvas({ padding: 0.3 });
    L.geoJSON(areas, {
      renderer: canvas,
      style: (f) => ({ renderer: canvas, stroke: false, fillColor: f.properties.color, fillOpacity: 0.5, interactive: true }),
      onEachFeature: (f, l) => {
        l.bindTooltip(f.properties.tip, { sticky: true, className: "rf-tip" });
        l.on("click", () => onArea && onArea(f.properties.name));
      }
    }).addTo(g);
  }, [areas, communities, activeLayer, showDrive, driveCenter && driveCenter[0], status]);

  React.useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!L || !map || !pinRef.current) return;
    pinRef.current.clearLayers();
    practices.forEach((p) => {
      const selected = p.id === activeId;
      const mk = L.marker([p.lat, p.lng], {
        icon: L.divIcon({
          html: practicePin(p.priceLabel, selected),
          className: "",
          iconSize: [78, 34],
          iconAnchor: [39, 34]
        }),
        zIndexOffset: selected ? 1000 : 0,
        keyboard: true,
        title: p.name + " — " + p.priceLabel
      })
        .bindTooltip(practiceCallout(p), {
          direction: "top",
          offset: [0, selected ? -22 : -34],
          className: "rf-callout",
          permanent: selected,
          opacity: 1
        })
        .on("click", () => onSelect && onSelect(p.id))
        .addTo(pinRef.current);
      // The selected practice's callout stays open on the map, and the map pans just far
      // enough to bring both pin and callout inside the viewport.
      if (selected) {
        mk.openTooltip();
        if (map.panInside) {
          map.panInside([p.lat, p.lng], { padding: [48, 110], animate: true });
        }
      }
    });
  }, [practices, activeId, status]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const t = setTimeout(() => map.invalidateSize(), 80);
    return () => clearTimeout(t);
  }, [resizeKey]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !center) return;
    map.setView(center, zoom, { animate: true });
  }, [center && center[0], center && center[1], zoom, recenterKey, status]);

  const stackBtn = {
    width: "34px", height: "32px", display: "grid", placeItems: "center", padding: 0,
    background: "none", border: 0, cursor: "pointer",
    fontFamily: "ProximaNova, Arial, Helvetica, sans-serif", fontSize: "17px",
    fontWeight: 500, color: "#003a70", lineHeight: 1
  };

  const ctrlBtn = {
    width: "32px", height: "32px", display: "grid", placeItems: "center",
    background: "none", border: 0, borderRadius: "999px", cursor: "pointer", padding: 0,
    filter: "drop-shadow(0 1px 3px rgba(0,58,112,.3))"
  };
  const ctrlIcon = { display: "block", opacity: 0.85 };

  return React.createElement(
    "div",
    { style: { position: "absolute", inset: 0, background: "#f5f5f5" } },
    React.createElement("div", { ref: hostRef, style: { position: "absolute", inset: 0 } }),
    status === "ready" &&
      React.createElement(
        "div",
        {
          style: {
            position: "absolute", right: "12px", top: "16px", zIndex: 500,
            display: "flex", flexDirection: "column", gap: "4px"
          }
        },
        React.createElement(
          "div",
          {
            style: {
              display: "flex", flexDirection: "column", background: "#fff",
              border: "1px solid #d4dde5", borderRadius: "8px", overflow: "hidden",
              boxShadow: "0 2px 8px rgba(0,58,112,.16)", width: "132px"
            }
          },
          onBasemap && React.createElement(
            "div",
            { style: { display: "flex", padding: "3px", gap: "2px" } },
            ["map", "satellite"].map((k) =>
              React.createElement(
                "button",
                {
                  key: k,
                  onClick: () => onBasemap && onBasemap(k),
                  "aria-pressed": basemap === k,
                  style: {
                    flex: 1, height: "28px", border: 0, borderRadius: "5px", cursor: "pointer",
                    fontFamily: "ProximaNova, Arial, Helvetica, sans-serif", fontSize: "12px",
                    fontWeight: 500, lineHeight: 1,
                    color: basemap === k ? "#003a70" : "#7a8590",
                    background: basemap === k ? "#deecf7" : "transparent"
                  }
                },
                k === "map" ? "Map" : "Satellite"
              )
            )
          ),
          onBasemap && React.createElement("span", { style: { height: "1px", background: "#e6e6e6" } }),
          React.createElement(
            "div",
            { style: { display: "flex" } },
            React.createElement(
              "button",
              {
                style: Object.assign({}, stackBtn, { flex: 1, width: "auto" }),
                onClick: () => mapRef.current && mapRef.current.zoomIn(),
                "aria-label": "Zoom in"
              },
              "+"
            ),
            React.createElement("span", { style: { width: "1px", background: "#e6e6e6" } }),
            React.createElement(
              "button",
              {
                style: Object.assign({}, stackBtn, { flex: 1, width: "auto" }),
                onClick: () => mapRef.current && mapRef.current.zoomOut(),
                "aria-label": "Zoom out"
              },
              "\u2212"
            )
          )
        )
      ),
    status !== "ready" &&
      React.createElement(
        "div",
        {
          style: {
            position: "absolute", inset: 0, display: "grid", placeItems: "center",
            background: "#f5f5f5", textAlign: "center", padding: "24px",
            fontFamily: "ProximaNova, Arial, Helvetica, sans-serif"
          }
        },
        status === "loading"
          ? React.createElement("div", { style: { fontSize: "13px", fontWeight: 500, color: "#494949" } }, "Loading map…")
          : React.createElement(
              "div",
              { style: { maxWidth: "320px" } },
              React.createElement(
                "div",
                { style: { fontSize: "17px", fontWeight: 700, color: "#003a70" } },
                "Map unavailable"
              ),
              React.createElement(
                "p",
                { style: { fontSize: "13px", color: "#494949", lineHeight: 1.6 } },
                "The map service could not be reached. Listings on the right are unaffected, and every market layer is still readable as a table in Market snapshot."
              )
            )
      )
  );
}

module.exports = { MarketMapV3 };
