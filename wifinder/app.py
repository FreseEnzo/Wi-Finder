"""Tela inicial do WiFinder: um servidor local que abre no navegador.

Mostra se o ESP32 está na USB, baixa os voos com um clique, lista os voos já
guardados e abre o mapa ou o relatório de um voo ou de vários juntos. Só
atende o próprio computador (127.0.0.1).
"""

import json
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, esp32
from .library import Library

MAX_UPLOAD = 16 * 1024 * 1024


def find_port():
    """Porta serial USB que parece ser a placa: (porta, descrição) ou None.
    Só lista as portas; não abre nenhuma (abrir reinicia o ESP32)."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    usb = [p for p in list_ports.comports() if p.vid is not None]
    # CP210x, CH340, FTDI e a USB nativa da Espressif primeiro.
    usb.sort(key=lambda p: (p.vid not in (0x10C4, 0x1A86, 0x0403, 0x303A), p.device))
    if not usb:
        return None
    name = usb[0].description or ""
    half = name.split(" - ")
    if len(half) == 2 and half[0] == half[1]:  # o Linux repete o nome: "CP2102 ... - CP2102 ..."
        name = half[0]
    return usb[0].device, name


class App:
    def __init__(self, root):
        self.lib = Library(root)
        self.lock = threading.Lock()
        self.job = dict(running=False, file="", done=0, total=0, results=[], error=None, finished=0)

    # ------------------------------------------------------------- estado

    def state(self):
        port = find_port()
        with self.lock:
            job = dict(self.job, results=list(self.job["results"]))
        return dict(version=__version__, folder=str(self.lib.root.resolve()),
                    device=dict(port=port[0], name=port[1]) if port else None,
                    job=job, flights=self.lib.flights())

    # ----------------------------------------------------------- download

    def start_pull(self, remove=False):
        port = find_port()
        if not port:
            return "Nenhuma placa na USB."
        with self.lock:
            if self.job["running"]:
                return "Já existe um download em andamento."
            self.job = dict(running=True, file="conectando", done=0, total=0, results=[], error=None, finished=0)
        threading.Thread(target=self._pull, args=(port[0], remove), daemon=True).start()
        return None

    def _set(self, **kw):
        with self.lock:
            self.job.update(kw)

    def _pull(self, port, remove):
        board = None
        try:
            board = esp32.Board(port)
            files = board.ls()
            self._set(total=sum(size for _, size in files))
            base = 0
            for name, size in files:
                self._set(file=name.lstrip("/"))
                data = board.dump(name, progress=lambda n, b=base: self._set(done=b + n))
                base += size
                fid, status = self.lib.add_log(name, data)
                with self.lock:
                    self.job["done"] = base
                    self.job["results"].append(dict(name=name.lstrip("/"), id=fid, status=status))
                if remove:
                    board.rm(name)
            board.done(len(files))
        except Exception as e:  # porta ocupada, cabo solto, placa sem resposta...
            self._set(error=_explain(e))
        finally:
            if board is not None:
                try:
                    board.close()
                except Exception:
                    pass
            self._set(running=False, file="", finished=time.time())

    # ------------------------------------------------------------- saídas

    def _title(self, ids):
        return self.lib.title(ids[0]) if len(ids) == 1 else f"{len(ids)} voos juntos"

    def map_html(self, ids):
        from . import map as map_

        routers, track, summary = self.lib.load(ids)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mapa.html"
            map_.write(out, routers, track, title=self._title(ids), summary=summary, home="/")
            return out.read_bytes()

    def report_pdf(self, ids):
        from . import report

        routers, track, summary = self.lib.load(ids)
        if not routers:
            raise ValueError("Este voo não tem redes com posição de GPS.")
        source = ", ".join(self.lib.title(i) for i in ids[:6]) + (" ..." if len(ids) > 6 else "")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "relatorio.pdf"
            report.write(out, routers, track, summary["amostras"], title=self._title(ids), source=source,
                         cache=Path.home() / ".cache" / "wifinder-tiles")
            return out.read_bytes()

    def report_md(self, ids):
        from . import report

        routers, track, summary = self.lib.load(ids)
        if not routers:
            raise ValueError("Este voo não tem redes com posição de GPS.")
        source = ", ".join(self.lib.title(i) for i in ids[:6]) + (" ..." if len(ids) > 6 else "")
        return report.markdown(routers, track, summary["amostras"], title=self._title(ids), source=source)


def _explain(e):
    text = str(e)
    if "ermission" in text:
        return "Sem permissão para abrir a porta serial. No Linux: sudo usermod -aG dialout $USER e entre de novo na sessão."
    if "busy" in text.lower() or "ocupad" in text.lower():
        return "A porta serial está ocupada. Feche o monitor serial ou outro programa que esteja usando a placa."
    if isinstance(e, TimeoutError):
        return f"A placa parou de responder ({text}). Confira o cabo e tente de novo."
    if isinstance(e, ImportError):
        return "Falta a biblioteca pyserial: pip install pyserial"
    return text or e.__class__.__name__


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    app = None  # preenchido em serve()

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _ids(self, query):
        ids = [i for i in query.get("ids", [""])[0].split(",") if i]
        known = set(self.app.lib.ids())
        if not ids or any(i not in known for i in ids):
            raise KeyError("voo não encontrado")
        return ids

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == "/":
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif url.path == "/api/state":
                self._send(200, self.app.state())
            elif url.path == "/mapa":
                self._send(200, self.app.map_html(self._ids(query)), "text/html; charset=utf-8")
            elif url.path in ("/relatorio.pdf", "/relatorio.md"):
                ids = self._ids(query)
                ext = url.path.rsplit(".", 1)[1]
                name = (ids[0] if len(ids) == 1 else f"{len(ids)}-voos") + "-relatorio." + ext
                # ?baixar=1 salva o arquivo; sem ele o PDF abre no navegador.
                how = "attachment" if query.get("baixar") == ["1"] else "inline"
                if ext == "pdf":
                    body, ctype = self.app.report_pdf(ids), "application/pdf"
                else:
                    body, ctype = self.app.report_md(ids), "text/markdown; charset=utf-8"
                self._send(200, body, ctype, [("Content-Disposition", f'{how}; filename="{name}"')])
            else:
                self._send(404, "Não encontrado.", "text/plain; charset=utf-8")
        except KeyError:
            self._send(404, "Voo não encontrado.", "text/plain; charset=utf-8")
        except Exception as e:
            self._send(500, f"Não deu certo: {e}", "text/plain; charset=utf-8")

    def do_POST(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        # Cabeçalho próprio: uma página de outro site não consegue mandá-lo.
        if self.headers.get("X-WiFinder") != "1":
            return self._send(403, dict(error="pedido recusado"))
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._send(413, dict(error="arquivo grande demais"))
        body = self.rfile.read(length) if length else b""
        try:
            if url.path == "/api/pull":
                err = self.app.start_pull(remove=query.get("rm", ["0"])[0] == "1")
                self._send(409 if err else 200, dict(error=err))
            elif url.path == "/api/import":
                fid, status = self.app.lib.add_log(query.get("name", ["voo.log"])[0], body)
                self._send(200, dict(id=fid, status=status))
            elif url.path == "/api/rename":
                data = json.loads(body)
                self.app.lib.rename(data["id"], str(data["title"]))
                self._send(200, dict(error=None))
            elif url.path == "/api/delete":
                self.app.lib.delete(json.loads(body)["id"])
                self._send(200, dict(error=None))
            elif url.path == "/api/quit":
                self._send(200, dict(error=None))
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send(404, dict(error="não encontrado"))
        except KeyError:
            self._send(404, dict(error="voo não encontrado"))
        except Exception as e:
            self._send(500, dict(error=str(e)))


def default_root():
    """Pasta dos voos: `voos` na pasta atual; no executável, ao lado dele."""
    import sys

    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent / "voos")
    return "voos"


def _already_open(url):
    import urllib.request

    try:
        with urllib.request.urlopen(url + "api/state", timeout=2) as r:
            return "version" in json.loads(r.read())
    except Exception:
        return False


def serve(root=None, port=8737, open_browser=True):
    url = f"http://127.0.0.1:{port}/"
    app = App(root or default_root())
    handler = type("H", (Handler,), {"app": app})
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        if _already_open(url):  # segundo clique no ícone: só mostra a tela que já existe
            print(f"O WiFinder já está aberto em {url}")
            if open_browser:
                webbrowser.open(url)
            return
        raise SystemExit(f"A porta {port} já está em uso por outro programa. Use --port com outro número.")
    print(f"WiFinder {__version__} em {url}\nVoos guardados em {app.lib.root.resolve()}\nCtrl+C para fechar.")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


PAGE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WiFinder</title>
<style>
  :root { --bg: #f5f6f8; --card: #ffffff; --fg: #14181f; --muted: #5f6877; --line: #e3e6eb;
          --accent: #1c5cab; --accent-fg: #ffffff; --ok: #0b7a2e; --bad: #b3261e; --track: #29b6f6; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1120px; margin: 0 auto; padding: 28px 20px 60px; }
  header.top { display: flex; align-items: baseline; gap: 12px; margin-bottom: 20px; }
  header.top h1 { margin: 0; font-size: 26px; letter-spacing: -.01em; }
  header.top span { color: var(--muted); font-size: 13px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; }
  button { font: inherit; padding: 8px 14px; border: 1px solid #c5cad3; border-radius: 8px; background: var(--card); color: var(--fg); cursor: pointer; }
  button:hover:not(:disabled) { background: var(--bg); }
  button:disabled { opacity: .5; cursor: default; }
  button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); font-weight: 600; }
  button.primary:hover:not(:disabled) { background: #184f95; }
  button.quiet { border-color: transparent; background: transparent; color: var(--muted); padding: 6px 8px; }
  button.quiet:hover:not(:disabled) { background: var(--bg); color: var(--fg); }
  a.btn { display: inline-block; text-decoration: none; padding: 8px 14px; border: 1px solid #c5cad3; border-radius: 8px; color: var(--fg); }
  a.btn:hover { background: var(--bg); }
  a.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); font-weight: 600; }

  #device { padding: 20px 22px; display: grid; grid-template-columns: auto 1fr auto; gap: 6px 16px; align-items: center; }
  #device .led { width: 14px; height: 14px; border-radius: 50%; background: #b9bfc9; }
  #device.on .led { background: var(--ok); box-shadow: 0 0 0 4px rgba(11,122,46,.15); }
  #device.wait .led { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .35; } }
  #device h2 { margin: 0; font-size: 17px; }
  #device p { margin: 0; color: var(--muted); }
  #device .actions { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
  #device label { color: var(--muted); font-size: 12.5px; display: flex; gap: 6px; align-items: center; }
  #progress { grid-column: 1 / 4; display: none; margin-top: 10px; }
  #progress .bar { height: 8px; background: var(--line); border-radius: 4px; overflow: hidden; }
  #progress .bar i { display: block; height: 100%; width: 0; background: var(--accent); transition: width .25s; }
  #progress .txt { margin-top: 6px; color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
  #result { grid-column: 1 / 4; display: none; margin-top: 10px; padding: 10px 12px; border-radius: 8px; background: var(--bg); }
  #result.err { background: #fdecea; color: var(--bad); }

  .bar2 { display: flex; align-items: center; gap: 10px; margin: 30px 0 12px; flex-wrap: wrap; }
  .bar2 h2 { margin: 0; font-size: 18px; flex: 1; }
  .bar2 .sel { color: var(--muted); }
  #flights { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
  .flight { padding: 14px 16px 12px; display: grid; grid-template-columns: 1fr 92px; gap: 4px 12px; position: relative; }
  .flight.picked { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
  .flight .head { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .flight .head input { width: 16px; height: 16px; accent-color: var(--accent); flex: none; }
  .flight h3 { margin: 0; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .flight .when { color: var(--muted); font-size: 12.5px; }
  .flight svg { grid-row: 1 / 3; grid-column: 2; width: 92px; height: 60px; background: var(--bg); border-radius: 8px; }
  .flight .head { align-self: end; }
  .flight .when { align-self: start; }
  .flight .nums { grid-column: 1 / 3; display: flex; gap: 18px; margin: 8px 0 2px; flex-wrap: wrap; }
  .flight .nums div b { display: block; font-size: 16px; font-variant-numeric: tabular-nums; }
  .flight .nums div span { color: var(--muted); font-size: 11.5px; }
  .flight .acts { grid-column: 1 / 3; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; padding-top: 10px; border-top: 1px solid var(--line); }
  .flight .acts a.btn, .flight .acts button { white-space: nowrap; padding: 7px 11px; }
  .flight .acts button.quiet { padding: 6px 7px; font-size: 13px; }
  .flight .acts .sp { flex: 1; }
  .flight .note { grid-column: 1 / 3; color: var(--muted); font-size: 12.5px; }
  #empty { padding: 36px 20px; text-align: center; color: var(--muted); }
  footer { margin-top: 26px; color: var(--muted); font-size: 12.5px; overflow-wrap: anywhere; display: flex; gap: 12px; align-items: center; }
  footer span { flex: 1; }
  @media (max-width: 640px) {
    #device { grid-template-columns: auto 1fr; }
    #device .actions { grid-column: 1 / 3; align-items: stretch; }
    #progress, #result { grid-column: 1 / 3; }
  }
</style>
</head>
<body>
<main>
  <header class="top"><h1>WiFinder</h1><span id="ver"></span></header>

  <section class="card wait" id="device">
    <span class="led"></span>
    <div><h2 id="devTitle">Procurando a placa...</h2><p id="devText"></p></div>
    <div class="actions">
      <button class="primary" id="pull" disabled>Baixar voos da placa</button>
      <label><input type="checkbox" id="rm">apagar da placa depois de baixar</label>
    </div>
    <div id="progress"><div class="bar"><i></i></div><div class="txt"></div></div>
    <div id="result"></div>
  </section>

  <div class="bar2">
    <h2 id="count">Voos</h2>
    <span class="sel" id="selText"></span>
    <button id="openSel" class="primary" style="display:none">Mapa dos selecionados</button>
    <button id="pdfSel" style="display:none" title="Relatório dos selecionados em PDF">Baixar PDF</button>
    <button id="mdSel" style="display:none" title="Relatório dos selecionados em Markdown">Baixar Markdown</button>
    <button id="importBtn">Importar arquivos .log</button>
    <input type="file" id="file" accept=".log,.txt" multiple hidden>
  </div>
  <div id="flights"></div>
  <div id="empty" class="card" style="display:none">Nenhum voo guardado ainda. Conecte a placa na USB e clique em “Baixar voos da placa”.</div>
  <footer><span id="foot"></span><button id="quit" class="quiet">Encerrar o WiFinder</button></footer>
</main>
<script>
const $ = id => document.getElementById(id);
const picked = new Set();
let lastFinished = 0, lastKey = "", busy = false;

const post = (url, body, raw) => fetch(url, {method: "POST", headers: {"X-WiFinder": "1"},
  body: raw ? body : body ? JSON.stringify(body) : null}).then(r => r.json());

function fmtDur(s) { return s == null ? "—" : s < 3600 ? Math.max(1, Math.round(s / 60)) + " min" : Math.floor(s / 3600) + " h " + String(Math.round(s % 3600 / 60)).padStart(2, "0"); }
function fmtDist(m) { return m == null ? "—" : m >= 1000 ? (m / 1000).toFixed(1).replace(".", ",") + " km" : Math.round(m) + " m"; }
function fmtWhen(t) {
  if (t == null) return "sem GPS";
  const d = new Date(t * 1000);
  return d.toLocaleDateString("pt-BR", {day: "2-digit", month: "short", year: "numeric"}) + ", " + d.toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"});
}
function el(tag, props, ...kids) {
  const e = Object.assign(document.createElement(tag), props || {});
  for (const k of kids) e.append(k);
  return e;
}
function preview(pts) {
  const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 92 60");
  if (pts.length > 1) {
    const lat0 = pts.reduce((a, p) => a + p[0], 0) / pts.length, k = Math.cos(lat0 * Math.PI / 180);
    const xs = pts.map(p => p[1] * k), ys = pts.map(p => -p[0]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const s = Math.min(76 / Math.max(x1 - x0, 1e-9), 46 / Math.max(y1 - y0, 1e-9));
    const ox = 46 - (x0 + x1) / 2 * s, oy = 30 - (y0 + y1) / 2 * s;
    const line = document.createElementNS(NS, "polyline");
    line.setAttribute("points", xs.map((x, i) => (x * s + ox).toFixed(1) + "," + (ys[i] * s + oy).toFixed(1)).join(" "));
    line.setAttribute("fill", "none"); line.setAttribute("stroke", "#1c5cab"); line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-linejoin", "round"); line.setAttribute("stroke-linecap", "round");
    svg.append(line);
  }
  return svg;
}
function num(v, label) { return el("div", null, el("b", {textContent: v}), el("span", {textContent: label})); }

function renderFlights(flights) {
  const key = JSON.stringify(flights.map(f => [f.id, f.title, f.size]));
  if (key === lastKey) return;
  lastKey = key;
  const ids = new Set(flights.map(f => f.id));
  for (const id of [...picked]) if (!ids.has(id)) picked.delete(id);
  const box = $("flights"); box.innerHTML = "";
  for (const f of flights) {
    const mapped = f.fixes > 0 && f.devices > 0;
    const cb = el("input", {type: "checkbox", checked: picked.has(f.id), disabled: !mapped, title: "Selecionar para abrir junto com outros"});
    const card = el("article", {className: "card flight" + (picked.has(f.id) ? " picked" : "")});
    cb.onchange = () => { cb.checked ? picked.add(f.id) : picked.delete(f.id); card.classList.toggle("picked", cb.checked); renderSel(); };
    card.append(el("div", {className: "head"}, cb, el("h3", {textContent: f.title, title: f.id})));
    card.append(preview(f.preview || []));
    card.append(el("div", {className: "when", textContent: fmtWhen(f.start)}));
    const nums = el("div", {className: "nums"});
    if (mapped) nums.append(num(f.devices, "aparelhos"), num(f.nets, "redes"), num(fmtDur(f.duration), "duração"), num(fmtDist(f.distance), "percurso"));
    else nums.append(num(f.nets, "redes ouvidas"), num(f.heard, "amostras"));
    card.append(nums);
    if (!mapped) card.append(el("div", {className: "note", textContent: f.fixes ? "Nenhuma rede ouvida com posição de GPS." : "O GPS não pegou posição neste voo, então não há mapa."}));
    const acts = el("div", {className: "acts"});
    if (mapped) {
      acts.append(el("a", {className: "btn primary", href: "/mapa?ids=" + encodeURIComponent(f.id), textContent: "Abrir mapa"}));
      acts.append(el("a", {className: "btn", href: "/relatorio.pdf?ids=" + encodeURIComponent(f.id), target: "_blank", title: "Abrir o relatório em PDF no navegador", textContent: "PDF"}));
      acts.append(el("a", {className: "btn", href: "/relatorio.pdf?baixar=1&ids=" + encodeURIComponent(f.id), title: "Baixar o relatório em PDF", textContent: "↓ PDF"}));
      acts.append(el("a", {className: "btn", href: "/relatorio.md?baixar=1&ids=" + encodeURIComponent(f.id), title: "Baixar o relatório em Markdown (texto, sem o mapa)", textContent: "↓ Markdown"}));
    }
    acts.append(el("span", {className: "sp"}));
    const ren = el("button", {className: "quiet", textContent: "Renomear"});
    ren.onclick = () => {
      const t = prompt("Nome do voo:", f.title);
      if (t != null && t.trim()) post("/api/rename", {id: f.id, title: t}).then(refresh);
    };
    const del = el("button", {className: "quiet", textContent: "Excluir"});
    del.onclick = () => {
      if (confirm(`Excluir "${f.title}" do computador? O arquivo ${f.id}.log será apagado.`)) post("/api/delete", {id: f.id}).then(refresh);
    };
    acts.append(ren, del);
    card.append(acts);
    box.append(card);
  }
  $("empty").style.display = flights.length ? "none" : "";
  $("count").textContent = flights.length ? `Voos (${flights.length})` : "Voos";
  renderSel();
}
function renderSel() {
  const n = picked.size;
  $("selText").textContent = n ? `${n} selecionado${n > 1 ? "s" : ""}` : "";
  $("openSel").style.display = $("pdfSel").style.display = $("mdSel").style.display = n > 1 ? "" : "none";
}
$("openSel").onclick = () => { location.href = "/mapa?ids=" + [...picked].map(encodeURIComponent).join(","); };
const selIds = () => [...picked].map(encodeURIComponent).join(",");
$("pdfSel").onclick = () => { location.href = "/relatorio.pdf?baixar=1&ids=" + selIds(); };
$("mdSel").onclick = () => { location.href = "/relatorio.md?baixar=1&ids=" + selIds(); };

const STATUS = {novo: "novo", atualizado: "atualizado", igual: "já estava guardado", vazio: "vazio, ignorado"};
function renderDevice(s) {
  const d = s.device, j = s.job, box = $("device");
  box.classList.toggle("on", !!d); box.classList.toggle("wait", !d);
  $("devTitle").textContent = j.running ? "Baixando os voos..." : d ? "Placa conectada" : "Conecte o ESP32 na USB";
  $("devText").textContent = d ? `${d.name || "porta serial"} em ${d.port}` : "A placa aparece aqui sozinha assim que for ligada no computador.";
  $("pull").disabled = !d || j.running || busy;
  $("rm").disabled = j.running;
  const pr = $("progress");
  pr.style.display = j.running ? "block" : "none";
  if (j.running) {
    const pct = j.total ? Math.min(100, 100 * j.done / j.total) : 0;
    pr.querySelector("i").style.width = pct + "%";
    pr.querySelector(".txt").textContent = j.total ? `${j.file}  ·  ${(j.done / 1024).toFixed(0)} de ${(j.total / 1024).toFixed(0)} KB` : "Conectando na placa (ela reinicia ao abrir a porta)...";
  }
  if (j.finished && j.finished !== lastFinished) {
    lastFinished = j.finished; lastKey = "";
    const r = $("result");
    r.style.display = "block"; r.className = j.error ? "err" : "";
    if (j.error) r.textContent = "O download não terminou: " + j.error;
    else {
      const n = k => j.results.filter(x => x.status === k).length;
      const parts = [];
      if (n("novo")) parts.push(n("novo") + " novo" + (n("novo") > 1 ? "s" : ""));
      if (n("atualizado")) parts.push(n("atualizado") + " atualizado" + (n("atualizado") > 1 ? "s" : ""));
      if (n("igual")) parts.push(n("igual") + " já guardado" + (n("igual") > 1 ? "s" : ""));
      if (n("vazio")) parts.push(n("vazio") + " vazio" + (n("vazio") > 1 ? "s" : "") + " (ignorado" + (n("vazio") > 1 ? "s" : "") + ")");
      r.textContent = j.results.length ? "Download concluído: " + parts.join(", ") + "." : "A placa não tinha nenhum voo gravado.";
    }
  }
}

function refresh() {
  return fetch("/api/state").then(r => r.json()).then(s => {
    $("ver").textContent = "versão " + s.version;
    $("foot").textContent = "Os voos ficam guardados em " + s.folder;
    renderDevice(s);
    renderFlights(s.flights);
    return s;
  }).catch(() => {
    $("devTitle").textContent = "O WiFinder foi fechado";
    $("devText").textContent = "Abra o programa de novo para continuar.";
    $("device").classList.remove("on"); $("pull").disabled = true;
  });
}
$("pull").onclick = () => {
  busy = true; $("pull").disabled = true; $("result").style.display = "none";
  post("/api/pull?rm=" + ($("rm").checked ? 1 : 0)).then(r => {
    busy = false;
    if (r.error) { const b = $("result"); b.style.display = "block"; b.className = "err"; b.textContent = r.error; }
    refresh();
  });
};
$("rm").onchange = () => {
  if ($("rm").checked && !confirm("Depois de baixar, os voos serão apagados da placa. Eles continuam guardados neste computador. Continuar?")) $("rm").checked = false;
};
$("importBtn").onclick = () => $("file").click();
$("file").onchange = async () => {
  const out = [];
  for (const f of $("file").files) out.push(await post("/api/import?name=" + encodeURIComponent(f.name), await f.arrayBuffer(), true));
  $("file").value = "";
  const b = $("result"); b.style.display = "block"; b.className = "";
  b.textContent = "Importação: " + out.map(r => STATUS[r.status] || r.error || "erro").join(", ") + ".";
  lastKey = ""; refresh();
};
$("quit").onclick = () => {
  if (confirm("Encerrar o WiFinder? Os voos continuam guardados; para voltar é só abrir o programa de novo.")) post("/api/quit").then(refresh);
};
refresh();
setInterval(refresh, 1500);
</script>
</body>
</html>
"""
