"""Gera o mapa HTML interativo (MapLibre GL): satélite com zoom alto, vista 2D
ou 3D, aparelhos coloridos pelo sinal, filtros, coordenadas (decimal, GMS e
MGRS) e exportação em CSV/KML."""

import json

TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WiFinder — __TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/mgrs@2.1.0/dist/mgrs.js"></script>
<style>
  :root { --bg: #ffffff; --soft: #f5f6f8; --fg: #14181f; --muted: #5f6877; --line: #e3e6eb;
          --accent: #1c5cab; --sel: #e6effb; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--fg); }
  #app { display: flex; height: 100%; }
  #panel { width: 340px; flex: none; display: flex; flex-direction: column; background: var(--bg);
           border-right: 1px solid var(--line); overflow: hidden; }
  #panel header { padding: 14px 16px 12px; border-bottom: 1px solid var(--line); }
  #panel header .brand { font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--accent); }
  #panel header .brand a { color: var(--muted); text-decoration: none; margin-right: 10px; letter-spacing: 0; text-transform: none; font-weight: 600; font-size: 12px; }
  #panel header .brand a:hover { color: var(--accent); }
  #panel header h1 { margin: 2px 0 10px; font-size: 18px; line-height: 1.25; overflow-wrap: anywhere; }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
  .stat { background: var(--soft); border-radius: 6px; padding: 6px 8px; min-width: 0; }
  .stat b { display: block; font-size: 15px; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .stat span { display: block; font-size: 10.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .block { padding: 10px 16px; border-bottom: 1px solid var(--line); }
  .block h4 { margin: 0 0 6px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
  #q { width: 100%; padding: 7px 10px; border: 1px solid #c5cad3; border-radius: 6px; font: inherit; }
  #q:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  label { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
  label input[type=range] { flex: 1; accent-color: var(--accent); }
  label .v { min-width: 62px; text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
  input[type=checkbox] { accent-color: var(--accent); }
  .row { display: flex; gap: 6px 12px; flex-wrap: wrap; align-items: center; }
  .row + .row { margin-top: 8px; }
  .row > span.k { color: var(--muted); min-width: 78px; }
  button, select { font: inherit; padding: 5px 10px; border: 1px solid #c5cad3; border-radius: 6px; background: var(--bg); color: var(--fg); cursor: pointer; }
  button:hover { background: var(--soft); }
  .seg { display: inline-flex; border: 1px solid #c5cad3; border-radius: 6px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; padding: 5px 12px; }
  .seg button + button { border-left: 1px solid #c5cad3; }
  .seg button.on { background: var(--accent); color: #fff; }
  #listhead { padding: 8px 16px; font-size: 11.5px; color: var(--muted); border-bottom: 1px solid var(--line); }
  #list { flex: 1; overflow-y: auto; margin: 0; padding: 0; list-style: none; }
  #list li { padding: 8px 16px; border-bottom: 1px solid #eef0f3; cursor: pointer; display: grid;
             grid-template-columns: 12px 1fr auto; gap: 1px 9px; align-items: center; }
  #list li:hover { background: var(--soft); }
  #list li.sel { background: var(--sel); }
  #list li .dot { width: 11px; height: 11px; border-radius: 50%; border: 1px solid rgba(0,0,0,.25); }
  #list li .name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #list li .meta { grid-column: 2 / 4; color: var(--muted); font-size: 11.5px; }
  #list li .rssi { color: var(--fg); font-variant-numeric: tabular-nums; font-size: 12px; }
  #mapwrap { flex: 1; position: relative; min-width: 0; }
  #map { position: absolute; inset: 0; }
  #coordbar { position: absolute; left: 50%; transform: translateX(-50%); bottom: 0; z-index: 5;
              background: rgba(255,255,255,.92); padding: 3px 12px; font: 12px ui-monospace, monospace;
              border-radius: 6px 6px 0 0; white-space: nowrap; }
  #legend { position: absolute; right: 10px; bottom: 34px; z-index: 5; background: rgba(255,255,255,.95);
            padding: 10px 12px; min-width: 200px; font-size: 12px; border-radius: 8px; box-shadow: 0 1px 5px rgba(0,0,0,.3); line-height: 1.7; }
  #legend .ramp { height: 9px; border-radius: 5px; margin: 2px 0 1px;
                  background: linear-gradient(90deg, #ffe9a8, #ffb347, #f4622a, #b3122a); }
  #legend .ends { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--muted); }
  #legend .sz { display: inline-block; border-radius: 50%; background: #f4622a; border: 1.5px solid #fff;
                box-shadow: 0 0 0 1px rgba(0,0,0,.35); vertical-align: middle; margin-right: 6px; }
  #legend .ln { display: inline-block; width: 16px; height: 3px; background: #29b6f6; vertical-align: middle; margin-right: 6px; }
  #msg { position: absolute; inset: 0; display: none; align-items: center; justify-content: center; z-index: 6;
         background: var(--soft); color: var(--muted); padding: 24px; text-align: center; }
  .maplibregl-popup-content { padding: 12px 14px; border-radius: 8px; font: 12.5px/1.45 system-ui, sans-serif; }
  .popup h3 { margin: 0 18px 4px 0; font-size: 14px; overflow-wrap: anywhere; }
  .popup table { border-collapse: collapse; }
  .popup td { padding: 1px 8px 1px 0; vertical-align: top; }
  .popup td.k { color: var(--muted); white-space: nowrap; }
  .popup code { font-family: ui-monospace, monospace; font-size: 12px; }
  .popup .copy { margin-left: 4px; padding: 0 5px; font-size: 11px; }
  .popup .nets { margin: 6px 0 2px; padding: 6px 0 0; border-top: 1px solid var(--line); }
  .popup .nets div { display: flex; justify-content: space-between; gap: 12px; }
  .popup .nets span { color: var(--muted); font-family: ui-monospace, monospace; font-size: 11.5px; }
  #toggle { display: none; position: absolute; top: 10px; left: 10px; z-index: 7; }
  @media (max-width: 760px) {
    #panel { position: absolute; z-index: 8; height: 100%; width: 88%; max-width: 340px; transform: translateX(-100%); transition: transform .2s; }
    #panel.open { transform: none; box-shadow: 0 0 20px rgba(0,0,0,.4); }
    #toggle { display: block; }
    #coordbar { font-size: 11px; }
    #legend { display: none; }
  }
</style>
</head>
<body>
<div id="app">
<aside id="panel">
  <header>
    <div class="brand"><a id="home" hidden>← Voos</a><span>WiFinder</span></div>
    <h1 id="title"></h1>
    <div class="stats" id="stats"></div>
  </header>
  <div class="block">
    <div class="row">
      <span class="k">Vista</span>
      <span class="seg" id="view"><button data-v="2d" class="on">2D</button><button data-v="3d">3D</button></span>
      <span class="seg" id="base"><button data-v="sat" class="on">Satélite</button><button data-v="ruas">Ruas</button></span>
    </div>
    <div class="row">
      <label><input type="checkbox" id="showTrack" checked>Trajetória</label>
      <label><input type="checkbox" id="showLabels" checked>Nomes</label>
      <label><input type="checkbox" id="showCircles">Raio provável de todos</label>
      <label id="wallLabel"><input type="checkbox" id="showWall">Altura do voo (3D)</label>
    </div>
  </div>
  <div class="block">
    <input id="q" placeholder="Buscar nome ou endereço (BSSID)" autocomplete="off">
    <div class="row" style="margin-top:8px">
      <label><input type="checkbox" class="st" value="boa" checked>Boa</label>
      <label><input type="checkbox" class="st" value="média" checked>Média</label>
      <label><input type="checkbox" class="st" value="fraca" checked>Fraca</label>
      <span style="color:var(--muted)">(confiança da posição)</span>
    </div>
    <label>Sinal ≥ <input type="range" id="minR" min="-100" max="-40" value="-100"><span class="v" id="minRv"></span></label>
  </div>
  <div class="block">
    <div class="row">
      <span class="k">Coordenadas</span>
      <select id="fmt"><option value="dec">Decimal</option><option value="dms">Graus/min/seg</option><option value="mgrs">MGRS</option></select>
    </div>
    <div class="row">
      <span class="k">Exportar</span>
      <button id="csv" title="Tabela dos aparelhos visíveis">CSV</button>
      <button id="kml" title="Aparelhos visíveis e trajetória, para o Google Earth">KML</button>
    </div>
  </div>
  <div id="listhead"></div>
  <ul id="list"></ul>
</aside>
<div id="mapwrap">
  <button id="toggle">☰ Lista</button>
  <div id="map"></div>
  <div id="msg"></div>
  <div id="legend"></div>
  <div id="coordbar">—</div>
</div>
</div>
<script>
const DATA = __DATA__;
const STATUS = {"boa": "boa", "média": "média", "fraca": "fraca (ouvido em poucos pontos)"};
const SIZE = {"boa": 8, "média": 6.5, "fraca": 5};
const RAMP = [[-95, [255, 233, 168]], [-85, [255, 179, 71]], [-75, [244, 98, 42]], [-65, [179, 18, 42]]];
const esc = s => String(s).replace(/[&<>"']/g, c => "&#" + c.charCodeAt(0) + ";");
const $ = id => document.getElementById(id);
const nameOf = r => r.ssid || "(rede oculta)";

function sigColor(v) {
  if (v <= RAMP[0][0]) return `rgb(${RAMP[0][1]})`;
  for (let i = 1; i < RAMP.length; i++) {
    if (v <= RAMP[i][0]) {
      const t = (v - RAMP[i - 1][0]) / (RAMP[i][0] - RAMP[i - 1][0]);
      return "rgb(" + RAMP[i - 1][1].map((a, k) => Math.round(a + t * (RAMP[i][1][k] - a))) + ")";
    }
  }
  return `rgb(${RAMP[RAMP.length - 1][1]})`;
}
const sigExpr = ["interpolate", ["linear"], ["get", "rssi"], ...RAMP.flatMap(([v, c]) => [v, `rgb(${c})`])];

// ---------------------------------------------------------------- coordenadas
function dms(v, pos, neg) {
  const h = v < 0 ? neg : pos; v = Math.abs(v);
  const d = Math.floor(v), m = Math.floor((v - d) * 60), s = ((v - d) * 60 - m) * 60;
  return `${d}°${String(m).padStart(2, "0")}'${s.toFixed(1).padStart(4, "0")}"${h}`;
}
function toMgrs(lat, lon) {
  try { return mgrs.forward([lon, lat], 5); } catch (e) { return "—"; }
}
function fmtCoord(lat, lon, f) {
  f = f || $("fmt").value;
  if (f === "dms") return dms(lat, "N", "S") + " " + dms(lon, "E", "W");
  if (f === "mgrs") return toMgrs(lat, lon);
  return lat.toFixed(6) + ", " + lon.toFixed(6);
}
function coordRows(lat, lon) {
  const c = v => `<code>${esc(v)}</code><button class="copy" data-copy="${esc(v)}" title="copiar">⧉</button>`;
  return `<tr><td class="k">Decimal</td><td>${c(lat.toFixed(6) + ", " + lon.toFixed(6))}</td></tr>`
    + `<tr><td class="k">GMS</td><td>${c(dms(lat, "N", "S") + " " + dms(lon, "E", "W"))}</td></tr>`
    + `<tr><td class="k">MGRS</td><td>${c(toMgrs(lat, lon))}</td></tr>`
    + `<tr><td class="k"></td><td><a href="https://www.google.com/maps?q=${lat},${lon}" target="_blank" rel="noopener">abrir no Google Maps</a></td></tr>`;
}
document.addEventListener("click", e => {
  const t = e.target.closest("[data-copy]");
  if (!t) return;
  const v = t.dataset.copy;
  (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).catch(() => window.prompt("Copie:", v));
});

// ------------------------------------------------------------- geometria
const M_LAT = 111320;
function ring(lat, lon, radius, n) {
  const out = [], k = M_LAT * Math.cos(lat * Math.PI / 180);
  for (let i = 0; i <= n; i++) {
    const a = 2 * Math.PI * i / n;
    out.push([lon + radius * Math.cos(a) / k, lat + radius * Math.sin(a) / M_LAT]);
  }
  return out;
}
const poly = (coords, props) => ({type: "Feature", properties: props || {}, geometry: {type: "Polygon", coordinates: [coords]}});
const point = (lat, lon, props) => ({type: "Feature", properties: props || {}, geometry: {type: "Point", coordinates: [lon, lat]}});
const fc = f => ({type: "FeatureCollection", features: f});

const items = DATA.routers.map((r, i) => ({r, i, visible: true}));
// Trechos da trajetória: p[3] = 1 marca o começo de um trecho novo (outro voo).
const trackSegs = [];
for (const p of DATA.track) {
  if (p[3] || !trackSegs.length) trackSegs.push([]);
  trackSegs[trackSegs.length - 1].push([p[1], p[0]]);
}
const maxH = Math.max(0, ...DATA.track.map(p => p[2] || 0));

function wallFeatures() {  // "cortina" da trajetória até a altura do voo
  const f = [];
  for (let i = 1; i < DATA.track.length; i++) {
    const [a1, o1, h1] = DATA.track[i - 1], [a2, o2, h2, brk] = DATA.track[i];
    const h = ((h1 || 0) + (h2 || 0)) / 2;
    if (brk || h < 1 || (a1 === a2 && o1 === o2)) continue;
    const k = M_LAT * Math.cos(a1 * Math.PI / 180);
    const dx = (o2 - o1) * k, dy = (a2 - a1) * M_LAT, len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len * 0.35 / k, ny = dx / len * 0.35 / M_LAT;
    f.push(poly([[o1 - nx, a1 - ny], [o2 - nx, a2 - ny], [o2 + nx, a2 + ny], [o1 + nx, a1 + ny], [o1 - nx, a1 - ny]], {h}));
  }
  return f;
}

// ------------------------------------------------------------------- mapa
let map, popup, selected = null, is3d = false, base = "sat";

function satMaxZoom() {
  // O satélite tem imagem até o nível 19 nas cidades e só até o 17 em área
  // remota (acima disso vem um aviso cinza). Testa no centro do voo.
  const c = DATA.center, test = z => {
    const n = 2 ** z, x = Math.floor((c[1] + 180) / 360 * n);
    const y = Math.floor((1 - Math.log(Math.tan(c[0] * Math.PI / 180) + 1 / Math.cos(c[0] * Math.PI / 180)) / Math.PI) / 2 * n);
    return fetch(`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`)
      .then(r => r.blob()).then(b => b.size > 4000);
  };
  const probe = test(19).then(ok => ok ? 19 : test(18).then(ok2 => ok2 ? 18 : 17)).catch(() => 17);
  return Promise.race([probe, new Promise(res => setTimeout(() => res(17), 4000))]);
}

function init(satZoom) {
  map = new maplibregl.Map({
    container: "map", maxZoom: 22, maxPitch: 75, attributionControl: {compact: true},
    style: {
      version: 8,
      glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
      sources: {
        sat: {type: "raster", tileSize: 256, maxzoom: satZoom, attribution: "Imagens © Esri",
              tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]},
        ruas: {type: "raster", tileSize: 256, maxzoom: 20, attribution: "© OpenStreetMap © CARTO",
               tiles: ["a", "b", "c", "d"].map(s => `https://${s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png`)},
        predios: {type: "vector", url: "https://tiles.openfreemap.org/planet"},
        track: {type: "geojson", data: {type: "Feature", properties: {}, geometry: {type: "MultiLineString", coordinates: trackSegs.filter(s => s.length > 1)}}},
        wall: {type: "geojson", data: fc(wallFeatures())},
        unc: {type: "geojson", data: fc([])},
        pts: {type: "geojson", data: fc([])},
        cols: {type: "geojson", data: fc([])},
        truth: {type: "geojson", data: fc([])},
        dev: {type: "geojson", data: fc([])},
        sel: {type: "geojson", data: fc([])},
      },
      layers: [
        {id: "bg", type: "background", paint: {"background-color": "#e9ecef"}},
        {id: "sat", type: "raster", source: "sat"},
        {id: "ruas", type: "raster", source: "ruas", layout: {visibility: "none"}},
        {id: "predios", type: "fill-extrusion", source: "predios", "source-layer": "building", minzoom: 14,
         layout: {visibility: "none"},
         paint: {"fill-extrusion-color": "#d9dde3", "fill-extrusion-opacity": 0.75,
                 "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
                 "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0]}},
        {id: "track-casing", type: "line", source: "track", layout: {"line-join": "round", "line-cap": "round"},
         paint: {"line-color": "#06324a", "line-width": 5, "line-opacity": 0.55}},
        {id: "track", type: "line", source: "track", layout: {"line-join": "round", "line-cap": "round"},
         paint: {"line-color": "#29b6f6", "line-width": 2.5}},
        {id: "wall", type: "fill-extrusion", source: "wall", layout: {visibility: "none"},
         paint: {"fill-extrusion-color": "#29b6f6", "fill-extrusion-opacity": 0.55, "fill-extrusion-height": ["get", "h"]}},
        {id: "unc-fill", type: "fill", source: "unc", paint: {"fill-color": "#ffffff", "fill-opacity": 0.12}},
        {id: "unc-line", type: "line", source: "unc", paint: {"line-color": "#ffffff", "line-width": 1.5, "line-dasharray": [3, 2]}},
        {id: "pts", type: "circle", source: "pts",
         paint: {"circle-radius": 4, "circle-color": sigExpr, "circle-stroke-color": "#10151c", "circle-stroke-width": 1}},
        {id: "cols", type: "fill-extrusion", source: "cols", layout: {visibility: "none"},
         paint: {"fill-extrusion-color": sigExpr, "fill-extrusion-opacity": 0.85, "fill-extrusion-height": ["get", "h"]}},
        {id: "truth-line", type: "line", source: "truth", filter: ["==", ["geometry-type"], "LineString"],
         paint: {"line-color": "#1baf7a", "line-width": 1.5, "line-dasharray": [2, 2]}},
        {id: "truth", type: "circle", source: "truth", filter: ["==", ["geometry-type"], "Point"],
         paint: {"circle-radius": 4.5, "circle-color": "#1baf7a", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5}},
        {id: "sel", type: "circle", source: "sel",
         paint: {"circle-radius": 14, "circle-color": "rgba(255,255,255,.25)", "circle-stroke-color": "#fff", "circle-stroke-width": 2.5}},
        {id: "dev", type: "circle", source: "dev",
         paint: {"circle-radius": ["get", "size"], "circle-color": sigExpr,
                 "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.8,
                 "circle-opacity": ["case", ["==", ["get", "status"], "fraca"], 0.8, 1]}},
        {id: "dev-label", type: "symbol", source: "dev",
         layout: {"text-field": ["get", "name"], "text-font": ["Noto Sans Bold"], "text-size": 12.5,
                  "text-anchor": "left", "text-offset": [0.95, 0], "text-max-width": 14,
                  "symbol-sort-key": ["-", 0, ["get", "rssi"]], "text-padding": 3},
         paint: {"text-color": "#ffffff", "text-halo-color": "rgba(8,12,18,.9)", "text-halo-width": 1.6}},
      ],
    },
  });
  map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), "top-right");
  map.addControl(new maplibregl.FullscreenControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl({unit: "metric", maxWidth: 140}), "bottom-left");
  popup = new maplibregl.Popup({maxWidth: "360px", className: "popup", offset: 12});

  const b = new maplibregl.LngLatBounds();
  DATA.track.forEach(p => b.extend([p[1], p[0]]));
  DATA.routers.forEach(r => b.extend([r.lon, r.lat]));
  if (!b.isEmpty()) map.fitBounds(b, {padding: 60, maxZoom: 19, animate: false});

  map.on("load", () => {
    const tf = [];
    for (const r of DATA.routers) if (r.truth) {
      tf.push(point(r.truth[0], r.truth[1], {name: nameOf(r)}));
      tf.push({type: "Feature", properties: {}, geometry: {type: "LineString", coordinates: [[r.lon, r.lat], [r.truth[1], r.truth[0]]]}});
    }
    map.getSource("truth").setData(fc(tf));
    apply();
  });
  map.on("mousemove", e => { $("coordbar").textContent = fmtCoord(e.lngLat.lat, e.lngLat.lng); });
  map.on("mouseenter", "dev", () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", "dev", () => { map.getCanvas().style.cursor = ""; });
  map.on("click", e => {
    const hit = map.queryRenderedFeatures(e.point, {layers: ["dev", "dev-label", "cols"]});
    if (hit.length) { select(hit[0].properties.i, false); return; }
    const pt = map.queryRenderedFeatures(e.point, {layers: ["pts"]});
    if (pt.length) { popup.setLngLat(e.lngLat).setHTML(`<b>${pt[0].properties.rssi} dBm</b> neste ponto`).addTo(map); return; }
    popup.setLngLat(e.lngLat).setHTML(`<h3>Ponto</h3><table>${coordRows(e.lngLat.lat, e.lngLat.lng)}</table>`).addTo(map);
  });
}

function popupHtml(r, i) {
  let h = `<h3>${esc(nameOf(r))} <span style="color:#5f6877;font-weight:400">#${i + 1}</span></h3><table>`;
  h += `<tr><td class="k">Sinal mais forte</td><td><b>${r.rssi_max} dBm</b>, canal ${r.channel}</td></tr>`;
  h += `<tr><td class="k">Posição</td><td>confiança ${esc(STATUS[r.status])}, raio provável ±${Math.round(r.radius)} m</td></tr>`;
  h += `<tr><td class="k">Ouvido</td><td>${r.samples} vezes em ${r.spots} ${r.spots === 1 ? "ponto" : "pontos"} do percurso</td></tr>`;
  if (r.error != null) h += `<tr><td class="k">Erro real</td><td>${r.error.toFixed(1)} m (simulação)</td></tr>`;
  h += coordRows(r.lat, r.lon) + "</table>";
  h += `<div class="nets"><b>${r.nets.length === 1 ? "Rede" : r.nets.length + " redes neste aparelho"}</b>`;
  for (const n of r.nets) h += `<div>${esc(n.ssid || "(rede oculta)")}<span>${esc(n.bssid)}</span></div>`;
  return h + "</div>";
}

function select(i, fly) {
  selected = i;
  const r = items[i].r;
  document.querySelectorAll("#list li").forEach(li => li.classList.toggle("sel", +li.dataset.i === i));
  const li = document.querySelector(`#list li[data-i="${i}"]`);
  if (li && !fly) li.scrollIntoView({block: "nearest"});
  drawSelection();
  popup.setLngLat([r.lon, r.lat]).setHTML(popupHtml(r, i)).addTo(map);
  if (fly) map.flyTo({center: [r.lon, r.lat], zoom: Math.max(map.getZoom(), 18.5), speed: 1.4});
  if (window.innerWidth <= 760) $("panel").classList.remove("open");
}

function drawSelection() {
  const all = $("showCircles").checked, f = [];
  for (const it of items) {
    if (!it.visible || !(all || it.i === selected)) continue;
    f.push(poly(ring(it.r.lat, it.r.lon, it.r.radius, 64)));
  }
  map.getSource("unc").setData(fc(f));
  const s = selected != null && items[selected].visible ? items[selected].r : null;
  map.getSource("sel").setData(fc(s ? [point(s.lat, s.lon)] : []));
  map.getSource("pts").setData(fc(s ? s.pts.map(p => point(p[0], p[1], {rssi: p[2]})) : []));
}

// ---------------------------------------------------------------- filtros
function apply() {
  if (!map || !map.getSource("dev")) return;
  const q = $("q").value.trim().toLowerCase();
  const st = new Set([...document.querySelectorAll(".st:checked")].map(e => e.value));
  const minR = +$("minR").value;
  $("minRv").textContent = minR <= -100 ? "todos" : minR + " dBm";
  const list = $("list"); list.innerHTML = "";
  const dev = [], cols = [];
  let n = 0, nets = 0;
  for (const it of items) {
    const r = it.r;
    it.visible = st.has(r.status) && r.rssi_max >= minR
      && (!q || r.nets.some(x => (x.ssid || "").toLowerCase().includes(q) || x.bssid.includes(q)));
    if (!it.visible) continue;
    n++; nets += r.nets.length;
    dev.push(point(r.lat, r.lon, {i: it.i, name: nameOf(r), rssi: r.rssi_max, status: r.status, size: SIZE[r.status]}));
    cols.push(poly(ring(r.lat, r.lon, 1.2, 12), {i: it.i, rssi: r.rssi_max, h: 4 + Math.max(0, r.rssi_max + 100) * 0.8}));
    const li = document.createElement("li");
    li.dataset.i = it.i;
    if (it.i === selected) li.classList.add("sel");
    const dot = document.createElement("span"); dot.className = "dot"; dot.style.background = sigColor(r.rssi_max);
    const name = document.createElement("span"); name.className = "name"; name.textContent = (it.i + 1) + ". " + nameOf(r);
    const rssi = document.createElement("span"); rssi.className = "rssi"; rssi.textContent = r.rssi_max + " dBm";
    const meta = document.createElement("span"); meta.className = "meta";
    meta.textContent = `canal ${r.channel} · ${r.nets.length > 1 ? r.nets.length + " redes · " : ""}confiança ${r.status} · ±${Math.round(r.radius)} m`;
    li.append(dot, name, rssi, meta);
    li.onclick = () => select(it.i, true);
    list.appendChild(li);
  }
  map.getSource("dev").setData(fc(dev));
  map.getSource("cols").setData(fc(cols));
  $("listhead").textContent = n === items.length ? `${n} aparelhos, do sinal mais forte ao mais fraco`
    : `${n} de ${items.length} aparelhos (${nets} redes)`;
  const vis = (id, on) => map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  const trk = $("showTrack").checked;
  vis("track", trk); vis("track-casing", trk);
  vis("dev-label", $("showLabels").checked);
  vis("cols", is3d); vis("predios", is3d);
  vis("wall", is3d && $("showWall").checked);
  vis("sat", base === "sat"); vis("ruas", base === "ruas");
  const dark = base === "sat";
  map.setPaintProperty("dev-label", "text-color", dark ? "#ffffff" : "#14181f");
  map.setPaintProperty("dev-label", "text-halo-color", dark ? "rgba(8,12,18,.9)" : "rgba(255,255,255,.95)");
  map.setPaintProperty("unc-line", "line-color", dark ? "#ffffff" : "#14181f");
  map.setPaintProperty("unc-fill", "fill-color", dark ? "#ffffff" : "#1c5cab");
  map.setPaintProperty("sel", "circle-stroke-color", dark ? "#ffffff" : "#14181f");
  if (selected != null && !items[selected].visible) { selected = null; popup.remove(); }
  drawSelection();
}
document.querySelectorAll("#panel input, #panel select").forEach(e => e.addEventListener("input", apply));
$("toggle").onclick = () => $("panel").classList.toggle("open");
function seg(id, fn) {
  $(id).querySelectorAll("button").forEach(b => b.onclick = () => {
    $(id).querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
    fn(b.dataset.v);
  });
}
seg("view", v => {
  is3d = v === "3d";
  apply();
  map.easeTo(is3d ? {pitch: 60, bearing: -20, duration: 900} : {pitch: 0, bearing: 0, duration: 700});
});
seg("base", v => { base = v; apply(); });

// --------------------------------------------------------------- cabeçalho
$("title").textContent = DATA.title;
if (DATA.home) { $("home").hidden = false; $("home").href = DATA.home; }
(function () {
  const s = DATA.summary || {}, cells = [[DATA.routers.length, "aparelhos"],
    [DATA.routers.reduce((a, r) => a + r.nets.length, 0), "redes"]];
  if (s.duracao != null) cells.push([Math.round(s.duracao / 60) + " min", "duração"]);
  if (s.distancia != null) cells.push([s.distancia >= 1000 ? (s.distancia / 1000).toFixed(1) + " km" : Math.round(s.distancia) + " m", "percurso"]);
  for (const [v, k] of cells) {
    const d = document.createElement("div"); d.className = "stat";
    const b = document.createElement("b"); b.textContent = v;
    const sp = document.createElement("span"); sp.textContent = k;
    d.append(b, sp); $("stats").appendChild(d);
  }
  // A cortina só vem ligada se o voo passou a maior parte do tempo no ar
  // (num percurso a pé a altitude do GPS é só ruído).
  const hs = DATA.track.map(p => p[2] || 0).sort((a, b) => a - b);
  if (maxH < 15) $("wallLabel").style.display = "none";
  else $("showWall").checked = hs[hs.length >> 1] >= 20;
  $("legend").innerHTML = '<b>Sinal mais forte ouvido</b><div class="ramp"></div>'
    + '<div class="ends"><span>−95 dBm (fraco)</span><span>−65 (forte)</span></div>'
    + '<div style="margin-top:6px"><b>Confiança da posição</b></div>'
    + '<span class="sz" style="width:16px;height:16px"></span>boa<br>'
    + '<span class="sz" style="width:13px;height:13px;margin-left:1.5px"></span>média<br>'
    + '<span class="sz" style="width:10px;height:10px;margin-left:3px;opacity:.8"></span>fraca<br>'
    + '<span class="ln"></span>trajetória'
    + '<div class="ends" style="margin-top:4px">Na vista 3D, coluna mais alta = sinal mais forte</div>'
    + (DATA.routers.some(r => r.truth) ? '<br><span class="sz" style="width:10px;height:10px;margin-left:3px;background:#1baf7a"></span>posição verdadeira' : '');
})();

// ------------------------------------------------------------- exportação
function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const csvCell = v => /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
$("csv").onclick = () => {
  const rows = [["#", "nome", "bssid", "redes", "canal", "lat", "lon", "mgrs", "raio_m", "confianca", "amostras", "pontos", "rssi_max"]];
  for (const it of items.filter(i => i.visible)) {
    const r = it.r;
    rows.push([it.i + 1, r.ssid, r.bssid, r.nets.map(n => (n.ssid || "(oculta)") + " " + n.bssid).join(" | "), r.channel,
               r.lat.toFixed(6), r.lon.toFixed(6), toMgrs(r.lat, r.lon), Math.round(r.radius), r.status, r.samples, r.spots, r.rssi_max]);
  }
  download("wifinder-aparelhos.csv", "﻿" + rows.map(r => r.map(csvCell).join(",")).join("\r\n"), "text/csv");
};
$("kml").onclick = () => {
  const x = s => String(s).replace(/[<>&]/g, c => ({"<": "&lt;", ">": "&gt;", "&": "&amp;"}[c]));
  const KC = {"boa": "ff2a12b3", "média": "ff2a62f4", "fraca": "ff47b3ff"};
  let k = '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>WiFinder ' + x(DATA.title) + '</name>\n';
  Object.keys(KC).forEach((s, j) => {
    k += `<Style id="s${j}"><IconStyle><color>${KC[s]}</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>\n`;
  });
  k += '<Style id="trk"><LineStyle><color>fff6b629</color><width>3</width></LineStyle></Style>\n';
  for (const it of items.filter(i => i.visible)) {
    const r = it.r;
    const d = `Sinal mais forte ${r.rssi_max} dBm, canal ${r.channel}\nConfiança ${r.status}, raio provável ±${Math.round(r.radius)} m\n`
      + `Ouvido ${r.samples} vezes em ${r.spots} pontos\nMGRS ${toMgrs(r.lat, r.lon)}\n` + r.nets.map(n => (n.ssid || "(oculta)") + " " + n.bssid).join("\n");
    k += `<Placemark><name>${x(nameOf(r))}</name><description>${x(d)}</description><styleUrl>#s${Object.keys(KC).indexOf(r.status)}</styleUrl><Point><coordinates>${r.lon},${r.lat},0</coordinates></Point></Placemark>\n`;
  }
  if (DATA.track.length && $("showTrack").checked) {
    trackSegs.filter(s => s.length > 1).forEach((seg, j) => {
      k += `<Placemark><name>Trajetória${trackSegs.length > 1 ? " " + (j + 1) : ""}</name><styleUrl>#trk</styleUrl><LineString><tessellate>1</tessellate><coordinates>${seg.map(p => p[0] + "," + p[1] + ",0").join(" ")}</coordinates></LineString></Placemark>\n`;
    });
  }
  download("wifinder.kml", k + "</Document></kml>", "application/vnd.google-earth.kml+xml");
};

// ------------------------------------------------------------------ início
if (!window.maplibregl) {
  $("msg").style.display = "flex";
  $("msg").textContent = "Não foi possível carregar o mapa. Ele precisa de internet para o fundo e para a biblioteca.";
} else {
  satMaxZoom().then(init);
}
</script>
</body>
</html>
"""


def write(path, routers, track, title="", summary=None, home=None):
    """Grava o mapa. track: [(lat, lon, alt[, t])]; summary: flight_summary();
    home: endereço da tela inicial, para o link de voltar."""
    alts = sorted(p[2] for p in track if len(p) > 2 and p[2] is not None)
    ground = alts[int(0.05 * len(alts))] if alts else 0.0
    lats = [p[0] for p in track] + [r["lat"] for r in routers]
    lons = [p[1] for p in track] + [r["lon"] for r in routers]
    data = {
        "title": title or "Voo",
        "home": home,
        "summary": summary or {},
        "routers": routers,
        "center": [sum(lats) / len(lats), sum(lons) / len(lons)] if lats else [0, 0],
        # Altura sobre o ponto mais baixo do voo, para a vista 3D.
        "track": [[p[0], p[1], round(max(0.0, p[2] - ground), 1) if len(p) > 2 and p[2] is not None else 0,
                   1 if i and len(p) > 3 and not 0 <= p[3] - track[i - 1][3] <= 30 else 0]
                  for i, p in enumerate(track)],
    }
    # SSIDs são texto arbitrário vindo do ar: não podem fechar a tag <script>.
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    html = TEMPLATE.replace("__TITLE__", (title or "Voo").replace("<", "").replace("&", ""))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html.replace("__DATA__", blob))
